import itertools
import pprint
import spacy
nlp=spacy.load('en_core_web_sm')

# region question parsing
def fix_question(text:str):
    if text.endswith('.'):
        text=text[:-1]
    if not text.endswith('?'):
        text=text+'?'
    return text[0].upper()+text[1:]

def parse_question(text):
    """
    breaks down a natural-language query into a hierarchical structure
    :return: list of questions (list of queries (list of terms))
    """
    doc=nlp(fix_question(text))

    ret=[]
    for sent in doc.sents:
        ret.extend(parse_sent(sent))
    return ret

def parse_sent(sent):
    return [parse_span(sent)]

def parse_span(span):
    return parse_children(span.root)

def parse_children(root,skip_root=False):
    ret=[]

    # which tokens to append,prepend and ignore
    deps=[
            # children tokens to ignore
            [
                'case',
                'punct',
                'det',
                'auxpass',
                # do not ignore advmod
            ],
            # children tokens to be prepended (to the ROOT)
            [
                'nsubj',
                'poss',
                'acl',
                'advcl',
                'relcl',
                'compound',
                'attr',
            ],
            # children tokens to be prepended but the children themselves omitted (grandchildren only)
            [
                'prep',
                'agent'
                # 'advmod',
            ],
            # appended
            [
                'pobj',
                'amod',
                'nsubjpass',
                'pcomp',
                'acomp',
                'oprd',
                'appos',
            ],
            #appending skip
            [
                # 'prep',
            ],
        ]

    # before root
    for child in root.children:
        if child.dep_ in deps[0]:
            continue
        elif child.dep_ in deps[2]:
            ret.extend(parse_children(child,skip_root=True))
        elif child.dep_ in deps[1]:
            ret.extend(parse_children(child))
        # special case
        elif child.dep_=='dobj':
            ret.extend(parse_children(child,skip_root=child.tag_=='WDT'))

    if not skip_root:
        if root.pos_!='VERB' and root.pos_!='ADP':
            if not root.dep_ in deps[0]:
                ret.append(root)

    # after root
    for child in root.children:
        if child.dep_ in deps[0]:
            continue
        elif child.dep_ in deps[4]:
            ret.extend(parse_children(child,skip_root=True))
        elif child.dep_ in deps[3]:
            ret.extend(parse_children(child))

    return ret
# endregion

# region keyword grouping + ordering
def groupings(query):
    """
    every way of splitting up the query into groups
    :return: generator
    """
    # see documentation for more info

    for split_config in itertools.product([0,1],repeat=len(query)-1): # get binary pattern
        obuf=[]
        buf=[]
        for i in range(len(split_config)):
            buf.append(query[i])
            if split_config[i]: # if there is a 'comma' after the entry
                #flush buf to obuf
                obuf.append(buf)
                buf=[]
        buf.append(query[-1]) # last item will never 'have a comma' after it
        obuf.append(buf) # flush buf to obuf
        yield obuf # flush obuf to ret

def query_perms(query):
    """
    useful permutations of groupings of the parsed terms - for searching
    :return: generator
    """
    for com in groupings(query): # get every grouping of the entries. e.g: [abc],[ab,c],[a,bc],...
        for permutation in itertools.permutations(com): # get permutations (possible orders) of the terms in grouping
            yield permutation
#endregion

def search(question):
    """
    relevant URLs for pages (that exist), given the question
    :return: [(confidence, data, source),...]
    """

    for query in parse_question(question):
        for group in query_perms(query):
            print(str(group))


if __name__=='__main__':
    print(search("the biggest animal of Europe"))
    # todo list:
    # Where was Obama born?