import builtins as __builtin__
import itertools
from typing import Dict, List, Tuple
import json
import sys
import wikipedia
from spacy import load
nlp=load('en_core_web_lg')

VERBOSITY=3
INDENT=0

#region utils
def tup_deduplicate(ret):
    """
    remove duplicates in a list of tuples by their second entries
    """
    seen=set()
    for tup in ret:
        if not tup[1] in seen:
            seen.add(tup[1])
            yield tup
#endregion

#region logging
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

def print_search_result(result):
    for key,value in result.items():
        print(key)
        indent()
        for item in value:
            print(str(item[0])+': '+json.dumps(str(item[1]))[:100])
        unindent()

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
#endregion

#region question parsing
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
#endregion

#region variations generation
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
        buf.append(query[-1]) # last item will never 'have a comma' after it so append at the end
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

#region searching
#region weighting
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

def rank_pages(grouping, input_pages):
    """
    rank pages by relevancy to grouping
    :return: sorted: [(confidence, WikipediaPage, content doc)...]
    """
    print("Ranking: ", level=3)
    indent(level=3)

    pages = []
    for page in input_pages:
        pages.append(add_relevancy_weighting(grouping, page))
    pages.sort(key=lambda x: x[0], reverse=True)  # sort pages by confidence

    for page in pages:
        print(page[:-1] + ('<doc>',), level=3)
    unindent(level=3)
    return pages

def similarity(doc,group_nlp):
    return doc.similarity(group_nlp)
#endregion

def search_wiki(search_string,limit=1):
    """
    try find pages relating to the search_string
    :return: generator: [(confidence, id),...]
    """
    doc1=nlp(search_string)
    for title in wikipedia.search(search_string,results=limit):
        yield (doc1.similarity(nlp(title)),title)

def search_candidates(variations, thresh=0.2, limit=1):
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
        for candidate in search_wiki(search_string,limit=limit):
            if candidate[0]>=thresh: # confidence >= threshold
                ret.append(candidate)
                count+=1

        print('['+str(count)+"]",level=1,indent=0)

    ret.sort(key=lambda x:x[0],reverse=True)

    unindent(level=1)
    return list(tup_deduplicate(ret)) # removed duplicate titles (keep one with highest confidence score)

def download_candidates(candidates):
    """
    evaluate [(confidence,id)...] list to [(confidence, WikipediaPage, Document)...]
    :return: sorted: [(confidence, WikipediaPage, Document)...]
    """
    wikipedia_pages=[]
    print('Downloading candidates: ', level=1)
    indent(level=1)

    for candidate in candidates:
        print(candidate if VERBOSITY >= 2 else "\"" + str(candidate[1]) + "\"", level=1)

        try:
            wikipedia_page = wikipedia.page(candidate[1])
            wikipedia_pages.append((candidate[0], wikipedia_page, nlp(wikipedia_page.content)))
        except wikipedia.exceptions.DisambiguationError:
            pass

    wikipedia_pages.sort(key=lambda x: x[0], reverse=True)  # sort wikipedia pages by confidence
    unindent(level=1)
    return wikipedia_pages

def search_data(grouping, spans, limit=10):
    """
    :param grouping:
    :param limit: the num of top posts to consider
    :param spans: [(confidence, span)...]
    :return: sorted: [(confidence, span)...]
    """
    ret = []
    group = grouping[0]
    group_nlp = nlp(' '.join(str(x) for x in group))

    for span in spans:
        ret.append((similarity(span[1],group_nlp), span[1]))

    ret.sort(key=lambda x:x[0],reverse=True) # sort by confidence
    ret=ret[:limit] # only consider top (limit)

    if len(grouping)>2:
        return search_data(grouping[1:], ret, limit=limit) # search through ret again, but next group
    else:
        return ret

def search(question, page_thresh=0.2, page_search_limit=1, per_page_limit=10):
    """
    :param question:
    :param page_thresh: the minimum relevancy of a page for it to be considered
    :param page_search_limit: num of candidates limit for each candidate search query
    :param per_page_limit: the number of top sentences to be kept per page
    :return: {page_title:[(confidence, data, WikipediaPage),...]}
    """
    ret:Dict[str, List[Tuple]]={}
    for query in parse_question(question):
        print('Query: '+str(query),level=1)
        indent(level=1)

        variations=list(query_variations(query))
        candidates = search_candidates(variations, thresh=page_thresh, limit=page_search_limit) # sorted: [(confidence, id),...]
        wikipedia_pages = download_candidates(candidates) # [(confidence, WikipediaPage, content doc)...]

        print('Analysing: ',level=1,end='' if VERBOSITY==1 else '\n')
        sys.stdout.flush()
        indent(level=1)

        for variation in variations:
            print(variation,level=3)
            indent(level=3)

            pages=rank_pages(variation,wikipedia_pages)

            print("Analysing pages: ",level=2,end='')
            sys.stdout.flush()

            indent(level=2)
            for page in pages:
                # page: (confidence, WikipediaPage, content doc)
                for data in search_data(variation, [(0.0,x) for x in page[2].sents], limit=per_page_limit): # spans start with a score of 0.0
                    dict_key=page[1].title # ret's keys are page titles
                    newl=ret.get(dict_key,[])
                    newl.append((data[0],data[1],page)) # (confidence, data, WikipediaPage)
                    ret[dict_key]=newl

                print('.',level=2,indent=0,end='')
                sys.stdout.flush()
            if VERBOSITY == 1:
                print('.',indent=0,end='')
                sys.stdout.flush()
            print('[OK]',indent=0,level=2)
            unindent(level=2) # /analysing pages

            unindent(level=3) # /variation
        unindent(level=1) # /analysing
        if VERBOSITY==1:
            print('[OK]',indent=0)
        unindent(level=1) # /query

    # sort and remove duplicates
    for k, v in ret.items():
        ret[k]=list(tup_deduplicate(sorted(v, key=lambda x:x[0], reverse=True)))

    return ret
#endregion

if __name__=='__main__':
    print_search_result(search("the biggest animal in Europe"))
