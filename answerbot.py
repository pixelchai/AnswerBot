import builtins as __builtin__

import itertools
import sys

import wikipedia
import pprint
from spacy import load
nlp= load('en_core_web_sm')

VERBOSITY=3
INDENT=0

# region logging
# noinspection PyShadowingBuiltins
def grouping_str(grouping):
    ret=''
    for i in range(len(grouping)):
        ret+=' '.join([str(x) for x in grouping[i]])
        if i<len(grouping)-1:
            ret+='>'
    return ret

def print(*args,**kwargs):
    # custom kwargs
    # NB: deleting them after so they don't get passed to internal print function
    if 'level' in kwargs:
        if VERBOSITY < kwargs['level']:
            return
        del kwargs['level']
    indt=INDENT
    if 'indent' in kwargs:
        indt=kwargs['indent']
        del kwargs['indent']
    if indt>0:
        __builtin__.print('\t'*indt,end='')
    return __builtin__.print(*args,**kwargs)

def indent(n=1,level=None):
    global INDENT
    if level is not None:
        if VERBOSITY<level:
            return
    INDENT+=n

def unindent(n=1,level=None):
    global INDENT
    if level is not None:
        if VERBOSITY<level:
            return
    INDENT-=n
# endregion

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
    print('Parsed: '+str(ret),level=1)
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
        yield obuf

def query_variations(query):
    """
    useful permutations of groupings of the parsed terms - for searching
    :return: generator
    """
    print("Generate variations: ",level=3)
    indent(level=3)
    for com in groupings(query): # get every grouping of the entries. e.g: [abc],[ab,c],[a,bc],...
        print(com,level=3)
        indent(level=3)
        for permutation in itertools.permutations(com): # get permutations (possible orders) of the terms in grouping
            print(grouping_str(permutation), level=3)
            yield permutation
        unindent(level=3)
    unindent(level=3)
    if VERBOSITY==2:print("Generated variations")
#endregion

def search_pages(variations, thresh=0.2):
    """
    find candidate pages to be analysed
    :return: sorted: [(confidence, id),...]
    """
    search_strings=set(' '.join(str(word) for word in variation[0]) for variation in variations) # set = remove duplicates (minimise networking)

    print('Searching for candidates:',level=1)
    indent(level=1)
    ret=[]
    for search_string in search_strings:

        print('\"'+search_string+"\"...",level=1,end='')
        sys.stdout.flush()

        count=0
        for candidate in search_wiki(search_string):
            if candidate[0]>=thresh: # confidence >= threshold
                ret.append(candidate)
                count+=1

        print('['+str(count)+"]",level=1,indent=0)

    def deduplicate():
        seen=set()
        for candidate in ret: # shadowing ok
            if not candidate[1] in seen:
                seen.add(candidate[1])
                yield candidate

    ret.sort(key=lambda x:x[0],reverse=True)

    unindent(level=1)
    return list(deduplicate()) # removed duplicate titles (keep one with highest confidence score)

def search(question):
    """
    :return: [(confidence, data, (title, WikipediaPage)),...]
    """
    for query in parse_question(question):
        print('Query: '+str(query),level=1)
        indent(level=1)

        wikipedia_pages=[] # [(confidence, WikipediaPage, content doc)...]
        variations=list(query_variations(query))

        candidates=search_pages(variations) # sorted: [(confidence, id),...]

        print('Downloading pages: ',level=1)
        indent(level=1)

        for candidate in candidates:
            print(candidate if VERBOSITY>=2 else "\""+str(candidate[1])+"\"",level=1)

            wikipedia_page=wikipedia.page(candidate[1])
            wikipedia_pages.append((candidate[0],wikipedia_page,nlp(wikipedia_page.content)))

        wikipedia_pages.sort(key=lambda x:x[0], reverse=True) # sort wikipedia pages by confidence
        unindent(level=1)

        print('Analysing: ',level=1)
        indent(level=1)
        for variation in variations:
            print(variation,level=3)
            indent(level=3)

            pages=[] # [(confidence, WikipediaPage, content doc)...]
            for page in wikipedia_pages:
                # pages.append(((add_relevancy_weighting(variation, page[2]) + page[0]) / 2.0, *page[1:])) # score now avg(relevancy,confidence)
                pages.append(add_relevancy_weighting(variation,page))
            pages.sort(key=lambda x: x[0], reverse=True)  # sort pages by confidence

            print("Ranking: ",level=3)
            indent(level=3)
            for page in pages:
                print(page[:-1]+('<doc>',),level=3)
            unindent(level=3)

            print("Analysing pages: ",level=2)
            indent(level=2)
            for page in pages:
                print("page",level=2)
            # todo extract data from pages
            unindent(level=2)

            unindent(level=3)
        unindent(level=1)

# def search_data(variation, wikipedia_pages):
#     pages


def add_relevancy_weighting(grouping, page):
    """
    calculate the relevancy of the page to the grouping
    :return: relevancy
    """
    score=0.0
    count=0.0
    for group in grouping:
        group_str = ' '.join([str(x) for x in group])
        score+=page[2].similarity(nlp(group_str))
        count+=1
    title_score=nlp(page[1].title).similarity(nlp(' '.join([str(x) for x in grouping[0]])))
    return (score/count + title_score,*page[1:])
    # return (score/count + page[0],*page[1:])

def search_wiki(search_string,limit=1):
    """
    try find pages relating to the group
    :return: generator: [(confidence, id),...]
    """
    doc1=nlp(search_string)
    for title in wikipedia.search(search_string,results=limit):
        yield (doc1.similarity(nlp(title)),title)


if __name__=='__main__':
    pprint.pprint(search('the biggest animal of Europe'))
