import builtins as __builtin__
import itertools
import string
from typing import Dict, List, Tuple
import json
import sys
import wikipedia
import click
# from spacy import load
# nlp=load('en_core_web_lg')

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

def similarity(span,group_nlp):
    ret = span.similarity(group_nlp)
    score=0.0
    count=0.0
    for keyword in parse_span(span):
        score+=group_nlp.similarity(keyword)
        count+=1
    if count>0:
        ret+=(score/count)/2.0
    return ret
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

#region user interface
class ResultUI:
    """
    provides a console user-interface for browsing a search result
    """

    def __init__(self,result,top_n=3,width=100):
        self.result=result
        self.top_n=top_n
        self.width=width

    def ordered_items(self):
        """
        get list of ranked (ordered) dictionary key-value pairs
        """
        return [(x,self.result[x]) for x in
                sorted(self.result.keys(),key=lambda x:self.average_top(self.result[x]),reverse=True)]

    def average_top(self,item, num=None):
        if num is None:
            num=self.top_n
        score=0.0
        for i in range(min(num,len(item))):
            score+=item[i][0]
        return score/num

    def basic_print(self):
        for key, value in self.ordered_items():
            print(key)
            indent()
            for item in value:
                print(str(item[0]) + ': ' + json.dumps(str(item[1]))[:100])
            unindent()

    def print_sep(self,edge=False,div=True):
        if not edge:
            print('|-----'+ ('|' if div else '-') + '-' * (self.width - 7 - 1) + '|')
        else:
            print('+-----'+('+' if div else '-') + '-' * (self.width - 7 - 1) + '+')

    def print_entry(self,text,entryno):
        print('|   ' + string.ascii_lowercase[entryno] + ' |  '
              + text.replace('\n','\\n').replace('\r','\\r').ljust(self.width - 2 - 9)[:self.width - 2 - 9] + ' |')

    def show_value(self,value):
        click.clear()
        print(value)
        input('<press enter to continue>')

    def show_key(self,key):
        items=self.result.get(key,[])

        if len(items)<=0:
            print("no items, sorry")
            input('<press enter to continue>')
            return

        while True:
            click.clear()

            # top bar
            self.print_sep(edge=True,div=False)
            print('| '+key.ljust(self.width-2-2)[:self.width-2-2]+' |')

            # values
            # separator
            self.print_sep(div=False)
            entryno = 0
            for entry in items:
                text = entry[1]
                self.print_entry(text, entryno)
                entryno += 1

            # bottom bar
            self.print_sep(edge=True)

            while True:
                try:
                    com=input('select: ').strip()
                    if len(com) > 1: raise ValueError
                    if com.isalpha():
                        index=(string.ascii_lowercase.index(com))
                        self.show_value(self.result[key][index][1])
                    elif com=='':
                        return
                    else:
                        raise ValueError
                except ValueError:
                    continue
                break

    @staticmethod
    def input_sel(error_handle=True):
        """
        get user input + parse
        :return: [int,int,...]
        """
        while True:
            try:
                com=input('select: ').strip()
                bufs=[]
                pointer=0
                prev_alpha=False
                for c in com:
                    if c.isalpha() ^ prev_alpha: # xor # if change from numerical to alpha or vice versa
                        prev_alpha=c.isalpha()
                        pointer+=1 # move to next buffer

                    for i in range(max(pointer+1-len(bufs),0)): # resize bufs as needed
                        bufs.append('')

                    bufs[pointer]+=c

                # convert to indexes
                ret=[]
                for buf in bufs:
                    if buf.isalpha():
                        if len(buf)>1: raise ValueError
                        ret.append(string.ascii_lowercase.index(buf)) # allow raise ValueError
                    elif buf.isnumeric():
                        ret.append(int(buf)-1)
                    elif buf=='':
                        ret.append(None)
                    else:
                        raise ValueError
                return ret
            except ValueError:
                if not error_handle: raise

    def show(self):
        #NB: max 99 results before deform

        ordered_items=self.ordered_items()

        if len(ordered_items)<=0:
            print("no items, sorry")
            input('<press enter to continue>')
            return

        while True:
            click.clear()

            # top bar
            self.print_sep(edge=True)
            keyno=1
            for key,value in ordered_items:
                if keyno>1:
                    # above key separator
                    self.print_sep()
                # key
                print('| '+str(keyno).rjust(2)+'  | '+key.ljust(self.width-2-8)[:self.width-2-8]+' |')

                # values
                if len(value)>0:
                    # separator
                    self.print_sep()
                    entryno=0
                    for entry in value:
                        text=entry[1]
                        if entryno>2: text='<more>'
                        self.print_entry(text,entryno)
                        # entry
                        if entryno>2: break
                        entryno+=1

                keyno+=1
            # bottom bar
            self.print_sep(edge=True)

            while True:
                com = self.input_sel()
                if len(com)<=0:
                    return
                else:
                    try:
                        if len(com)<=1:
                            self.show_key([pair[0] for pair in ordered_items][com[0]])
                        else:
                            self.show_value(ordered_items[com[0]][1][com[1]][1])
                    except (IndexError, TypeError):
                        continue
                    break
#endreigon

if __name__=='__main__':
    while True:
        click.clear()
        # ResultUI(search(input('>>'))).show()
        test1={
            'test':[
                (0.3,'lel')
            ]
        }
        test2 = {
        }

        test3={
            'aimer':[
                (0.9,"At the age of 15,\n\r she lost her voice due to over-usage of her vocal chords and was forced to undergo silence therapy for treatment, however that did not stop her as after she recovered, she acquired her distinctive husky voice."),
                (0.8,"Short sentence."),
                (0.7,'Aimer teamed up with the "Agehasprings" group, which has worked with, produced, or provided music for various artists, including Yuki, Mika Nakashima, Flumpool, Superfly, Yuzu, and Genki Rockets'),
                (0.69,'In 2011, her musical career began in earnest.'),
                (0.68,'In May 2011, they released the concept album Your favorite things. It covered numerous popular works, including works in various genre such as jazz and country western music.')
            ],
            'Mica': [
                (0.9,
                 "Mica is a song by Danish band Mew."),
                (0.8, "Another short sentence."),
            ],
            'Emptica':[]
        }

        # print(ResultUI.input_sel())
        ResultUI(test3).show()
