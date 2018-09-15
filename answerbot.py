import itertools
from typing import List

import wikipedia
import pprint
import spacy
nlp=spacy.load('en_core_web_sm')
VERBOSITY=3

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
    if VERBOSITY>=1: print('Parsed: '+str(ret))
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

# def search(question):
#     """
#     relevant URLs for pages (that exist), given the question
#     NOTE: Every
#     :return: [(confidence, (data, data_broad, content), (url, title)),...]
#     """
#
#     for query in parse_question(question):
#         for group in query_perms(query):
#             print(str(group))

def search_pages(perms,thresh=0.2):
    """
    find candidate pages to be analysed
    :return: sorted: [(confidence, id),...]
    """
    search_strings=set(' '.join(str(word) for word in perm[0]) for perm in perms) # remove duplicates (minimise networking)
    ret=[]
    for search_string in search_strings:
        for candidate in search_wiki(search_string):
            if candidate[0]>=thresh: # confidence >= threshold
                ret.append(candidate)

    def deduplicate():
        seen=set()
        for candidate in ret:
            if not candidate[1] in seen:
                seen.add(candidate[1])
                yield candidate

    ret.sort(key=lambda x:x[0],reverse=True)
    return list(deduplicate()) # removed duplicate titles (keep one with highest confidence score)

#todo
# def get_pages(titles):
#     """
#     get Wikipedia pages from page titles
#     :return: list of WikipediaPage objects
#     """
#     for title titles:
#         yield wikipedia.page()

def search_wiki(search_string,limit=1):
    """
    try find pages relating to the group
    :return: generator: [(confidence, id),...]
    """
    doc1=nlp(search_string)
    for title in wikipedia.search(search_string,results=limit):
        yield (doc1.similarity(nlp(title)),title)


if __name__=='__main__':
    for query in parse_question("the biggest animal of Europe"):
        a=search_pages(query_perms(query))
        pprint.pprint(a)
    # print(search_wiki("the biggest animal of Europe"))
