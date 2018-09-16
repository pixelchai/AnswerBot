import builtins as __builtin__

import itertools
from typing import Dict, Any, List, Tuple

import jsonpickle
import json
import sys

import wikipedia
import pprint
from spacy import load
# nlp= load('en_core_web_sm')
nlp=load('en_core_web_lg')

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

    ret.sort(key=lambda x:x[0],reverse=True)

    unindent(level=1)
    return list(deduplicate(ret)) # removed duplicate titles (keep one with highest confidence score)

def deduplicate(ret):
    seen=set()
    for candidate in ret: # shadowing ok
        if not candidate[1] in seen:
            seen.add(candidate[1])
            yield candidate

def download_wikipedia_pages(candidates):
    """
    :return: [(confidence, WikipediaPage, content doc)...]
    """
    wikipedia_pages=[]
    print('Downloading pages: ', level=1)
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

def rank_pages(variation,input_pages):
    print("Ranking: ", level=3)
    indent(level=3)
    pages = []  # [(confidence, WikipediaPage, content doc)...]
    for page in input_pages:
        # pages.append(((add_relevancy_weighting(variation, page[2]) + page[0]) / 2.0, *page[1:])) # score now avg(relevancy,confidence)
        pages.append(add_relevancy_weighting(variation, page))
    pages.sort(key=lambda x: x[0], reverse=True)  # sort pages by confidence

    for page in pages:
        print(page[:-1] + ('<doc>',), level=3)
    unindent(level=3)
    return pages

def search(question):
    """
    :return: [(confidence, data, WikipediaPage),...]
    """
    ret:Dict[str, List[Tuple]]={}
    for query in parse_question(question):
        print('Query: '+str(query),level=1)
        indent(level=1)

        variations=list(query_variations(query))
        candidates = search_pages(variations) # sorted: [(confidence, id),...]
        wikipedia_pages = download_wikipedia_pages(candidates) # [(confidence, WikipediaPage, content doc)...]

        print('Analysing: ',level=1)
        indent(level=1)
        for variation in variations:
            print(variation,level=3)
            indent(level=3)

            pages=rank_pages(variation,wikipedia_pages)

            print("Analysing pages: ",level=2)
            indent(level=2)
            for page in pages:
                a=[(0.0,x) for x in page[2].sents]
                x=search_data(variation,a) # skip first grouping - that decided the page itself
                # x.sort(key=lambda x:x[0],reverse=True)
                for y in x:
                    # ret.append((y[0],*y[1:]))
                    newl=ret.get(page[1].title,[])
                    newl.append((y[0],*y[1:]))
                    ret[page[1].title]=newl
            unindent(level=2)

            unindent(level=3)
        unindent(level=1)

    # sort and remove duplicates
    for k, v in ret.items():
        ret[k]=list(deduplicate(sorted(v,key=lambda x:x[0],reverse=True)))

    return ret

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

def search_wiki(search_string,limit=1):
    """
    try find pages relating to the group
    :return: generator: [(confidence, id),...]
    """
    doc1=nlp(search_string)
    for title in wikipedia.search(search_string,results=limit):
        yield (doc1.similarity(nlp(title)),title)

def search_data(variation, spans,limit=10):
    """
    :return: [(confidence, span)...]
    """
    ret = []
    group = variation[0]
    group_nlp = nlp(' '.join(str(x) for x in group))

    for span in spans:
        # span = (confidence,span)
        # sim = span[1].similarity(group_nlp)
        sim=similarity(span[1],group_nlp)
        # print(sim)
        ret.append((sim, span[1]))
    # only consider top (limit)
    ret.sort(key=lambda x:x[0],reverse=True)
    ret=ret[:limit]
    if len(variation)>2:
        return search_data(variation[1:],ret)
    else:
        return ret
    # return ret

def similarity(doc,group_nlp):
    return doc.similarity(group_nlp)

if __name__=='__main__':
    # print(parse_question('The African bush elephant (Loxodonta africana), of the order Proboscidea, is the largest living land animal.)'))

    result=(search('the largest living land animal'))
    # result.sort(key=lambda x:x[0],reverse=True)
    # for res in result:
    #     print(res)
    for key,value in result.items():
        print(key)
        indent()
        for item in value:
            print(str(item[0])+': '+json.dumps(str(item[1]))[:100],end=':')
            print(json.dumps(str(item[1]))[:50],indent=0)
        unindent()
    # pprint.pprint(result)
    # print(jsonpickle.dumps(result))
    # variation=(['animal'],['biggest'],['Europe'])
    # doc = nlp("The largest organisms found on Earth can be determined according to various aspects of an organism's size, such as: mass, volume, area, length, height, or even genome size. Some organisms group together to form a superorganism (such as ants or bees), but such are not classed as single large organisms. The Great Barrier Reef is the world's largest structure composed of living entities, stretching 2,000 km (1,200 mi), but contains many organisms of many types of species.\r\nThis article lists the largest species for various types of organisms, and mostly considers extant species. The organism sizes listed are frequently considered \"outsized\" and are not in the normal size range for the respective group.\r\nIf considered singular entities, the largest organisms are clonal colonies which can spread over large areas. Pando, a clonal colony of the quaking aspen tree, is widely considered to be the largest such organism by mass. Even if such colonies are excluded, trees retain their dominance of this listing, with the giant sequoia being the most massive tree. In 2006 a huge clonal colony of Posidonia oceanica was discovered south of the island of Ibiza. At 8 kilometres (5 mi) across, and estimated at around 100,000 years old, it may be one of the largest and oldest clonal colonies on Earth.Among animals, the largest species are all marine mammals, specifically whales. The blue whale is believed to be the largest animal to have ever lived. The largest land animal classification is also dominated by mammals, with the African bush elephant being the most massive of these.\r\n\r\n\r\n== Plants ==\r\n\r\nThe largest single-stem tree by wood volume and mass is the giant sequoia (Sequoiadendron giganteum), native to Sierra Nevada and California; it typically grows to a height of 70\u201385 m (230\u2013280 ft) and 5\u20137 m (16\u201323 ft) in diameter.\r\nMultiple-stem trees such as banyan can be enormous. Thimmamma Marrimanu in India spreads over 1.0 ha (2.5 acres).\r\nThe largest organism in the world, according to mass, is the aspen tree whose colonies of clones can grow up to five miles long. The largest such colony is Pando, in the Fishlake National Forest in Utah.\r\nAnother form of flowering plant that rivals Pando as the largest organism on earth in breadth, if not mass, is the giant marine plant, Posidonia oceanica, discovered in the Mediterranean near the Balearic Islands, Spain. Its length is about 8 km (5 mi). It may also be the oldest living organism in the world, with an estimated age of 100,000 years.\r\n\r\n\r\n=== Green algae ===\r\nGreen algae are photosynthetic unicellular and multicellular protists that are related to land plants. The thallus of the unicellular mermaid's wineglass, Acetabularia, can grow to several inches (perhaps 0.1 to 0.2 m) in length. The fronds of the similarly unicellular, and invasive Caulerpa taxifolia can grow up to a foot (0.3 m) long.\r\n\r\n\r\n== Animals ==\r\nA member of the order Cetacea, the blue whale (Balaenoptera musculus), is thought to be the largest animal ever to have lived. The maximum recorded weight was 190 metric tonnes for a specimen measuring 27.6 metres (91 ft), whereas longer ones, up to 33.6 metres (110 ft), have been recorded but not weighed.The African bush elephant (Loxodonta africana), of the order Proboscidea, is the largest living land animal. A native of various open habitats in sub-Saharan Africa, this elephant is commonly born weighing about 100 kilograms (220 lb). The largest elephant ever recorded was shot in Angola in 1974. It was a male measuring 10.67 metres (35.0 ft) from trunk to tail and 4.17 metres (13.7 ft) lying on its side in a projected line from the highest point of the shoulder to the base of the forefoot, indicating a standing shoulder height of 3.96 metres (13.0 ft). This male had an computed weight of 12.25 tonnes.\r\nTable of heaviest living animalsThe heaviest living animals are all cetaceans, and thus also the largest living mammals. Since no scale can accommodate the whole body of a large whale, most whales have been weighed by parts.\r\n\r\n \r\nTable of heaviest terrestrial animalsThe following is a list of the heaviest wild land animals, which are all mammals. The African elephant is now listed as two species, the African bush elephant and the African forest elephant, as they are now generally considered to be two separate species.\r\n\r\n\r\n=== Tunicates (Tunicata) ===\r\nThe largest tunicates are Synoicum pulmonaria, found at depths of 20 and 40 metres (66 and 131 ft), and are up to 14 centimetres (6 in) in diameter. It is also present in the northwestern Atlantic Ocean, around the coasts of Greenland and Newfoundland, but is less common here than in the east, and occurs only at depths between 10 and 13 metres (33 and 43 ft).\r\nEntergonas (Enterogona)The largest entergonas Synoicum pulmonaria it is usually found at depths between about 20 and 40 metres (66 and 131 ft) and can grow to over a metre (yard) in length. It is also present in the northwestern Atlantic Ocean, around the coasts of Greenland and Newfoundland, but is less common here than in the east, and occurs only at depths between 10 and 13 metres (33 and 43 ft).Pleurogonas (Pleurogona)The largest pleurogonas: Pyura pachydermatina . In colour it is off-white or a garish shade of reddish-purple. The stalk is two thirds to three quarters the length of the whole animal which helps distinguish it from certain invasive tunicates not native to New Zealand such as Styela clava and Pyura stolonifera. It is one of the largest species of tunicates and can grow to over a metre (yard) in length.Aspiraculates (Aspiraculata)The largest aspiraculates: Oligotrema large and surrounded by six large lobes; the cloacal syphon is small. They live exclusively in deep water and range in size from less than one inch (2 cm) to 2.4 inches (6 cm).\r\n\r\n\r\n=== Thaliacea ===\r\n\r\nThe largest thaliacean: Pyrosoma atlanticum is cylindrical and can grow up to 60 cm (2 ft) long and 4\u20136 cm wide. The constituent zooids form a rigid tube, which may be pale pink, yellowish, or bluish. One end of the tube is narrower and is closed, while the other is open and has a strong diaphragm. The outer surface or test is gelatinised and dimpled with backward-pointing, blunt processes. The individual zooids are up to 8.5 mm (0.3 in) long and have a broad, rounded branchial sac with gill slits. Along the side of the branchial sac runs the endostyle, which produces mucus filters. Water is moved through the gill slits into the centre of the cylinder by cilia pulsating rhythmically. Plankton and other food particles are caught in mucus filters in the processes as the colony is propelled through the water. P. atlanticum is bioluminescent and can generate a brilliant blue-green light when stimulated.Doliolida (Doliolida)The largest doliolida: Doliolida  The doliolid body is small, typically 1\u20132 cm long, and barrel-shaped; it features two wide siphons, one at the front and the other at the back end, and eight or nine circular muscle strands reminiscent of barrel bands. Like all tunicates, they are filter feeders. They are free-floating; the same forced flow of water through their bodies with which they gather plankton is used for propulsion - not unlike a tiny ramjet engine. Doliolids are capable of quick movement. They have a complicated lifecycle consisting of sexual and asexual generations. They are nearly exclusively tropical animals, although a few species can be found as far to the north as northern California.Salps (Salpida)The largest salps: Cyclosalpa bakeri15cm (6ins) long. There are openings at the anterior and posterior ends of the cylinder which can be opened or closed as needed. The bodies have seven transverse bands of muscle interspersed by white, translucent patches. A stolon grows from near the endostyle (an elongated glandular structure producing mucus for trapping food particles). The stolon is a ribbon-like organ on which a batch of aggregate forms of the animal are produced by budding. The aggregate is the second, colonial form of the salp and is also gelatinous, transparent and flabby. It takes the shape of a radial whorl of individuals up to about 20cm (4in) in diameter. It is formed of approximately 12 zooids linked side by side in a shape that resembles a crown. are largest thetyses: Thetys vagina Individuals can reach up to 30 cm (12 in) long.Larvaceans  (Larvacea)The largest larvaceans: Appendicularia 1 cm (0.39 in) in body length (excluding the tail).\r\n\r\n\r\n=== Cephalochordate (Leptocardii) ===\r\nThe largest lancelets: European lancelet (Branchiostoma lanceolatum) \"primitive fish\". It can grow up to 6 cm (2.5 in) long.\r\n\r\n\r\n=== Vertebrates ===\r\n\r\n\r\n==== Mammals (Mammalia) ====\r\n\r\nThe blue whale is the largest mammal.\r\nThe largest land mammal extant today is the African bush elephant. The largest extinct land mammal known was once considered to be Paraceratherium orgosensis, a rhinoceros relative thought to have stood up to 4.8 m (15.7 ft) tall, measured over 7.4 m (24.3 ft) long and may have weighed about 17 tonnes. More recent estimates suggest that Paraceratherium was surpassed by the proboscidean Palaeoloxodon namadicus at about 22 tonnes.\r\n\r\n\r\n==== Stem-mammals (Synapsida) ====\r\n\r\nThe Permian era Cotylorhynchus, from what is now the southern United States, probably was the largest of all synapsids (most of which became extinct 250 million years ago), at 6 m (20 ft) and 2 tonnes. The largest carnivorous synapsid was Anteosaurus from what is now South Africa during Middle Permian era. Anteosaurus was 5\u20136 m (16\u201320 ft) long, and weighed about 500\u2013600 kg (1,100\u20131,300 lb).\r\nPelycosauriaThe largest pelycosaur was the pre-mentioned Cotylorhynchus, and the largest predatory pelycosaurus was Dimetrodon grandis from what is now North America, with a length of 3.1 m (10 ft) and weight of 250 kg (550 lb).TherapsidaMoschops was the largest non-mammalian therapsid, with a weight of 700 to 1,000 kg (1,500 to 2,200 lb), and a length of about 5 m (16 ft). The largest carnivorous therapsid was the aforementioned Anteosaurus.\r\n\r\n\r\n==== Reptiles (Reptilia) ====\r\n\r\nThe largest living reptile, a representative of the order Crocodilia, is the saltwater crocodile (Crocodylus porosus) of Southern Asia and Australia, with adult males being typically 3.9\u20135.5 m (13\u201318 ft) long. The largest confirmed saltwater crocodile on record was 6.32 m (20.7 ft) long, and weighed about 1,360 kg (3,000 lb). Unconfirmed reports of much larger crocodiles exist, but examinations of incomplete remains have never suggested a length greater than 7 m (23 ft). Also, a living specimen estimated at 7 m (23 ft) and 2,000 kg (4,400 lb) has been accepted by the Guinness Book of World Records. However, due to the difficulty of trapping and measuring a very large living crocodile, the accuracy of these dimensions has yet to be verified. A specimen named Lolong caught alive in the Philippines in 2011 (died February 2013) was found to have measured 6.17 m (20.2 ft) in length.The Komodo dragon (Varanus komodoensis), also known as the \"Komodo monitor\", is a large species of lizard found in the Indonesian islands of Komodo, Rinca, Flores, Gili Motang, and Padar. A member of the monitor lizard family (Varanidae), it is the largest living species of lizard, growing to a maximum length of 3 metres (9.8 feet) in rare cases and weighing up to approximately 70 kilograms (150 pounds).\r\n\r\nTable of heaviest living reptilesThe following is a list of the heaviest living reptile species ranked by average weight, which is dominated by the crocodilians. Unlike mammals, birds, or fish, the mass of large reptiles is frequently poorly documented and many are subject to conjecture and estimation.\r\n\r\n\r\n==== Dinosaurs (Dinosauria) ====\r\n\r\nNow extinct, except for birds, which are theropods.Sauropods (Sauropoda)\r\nThe largest dinosaurs, and the largest animals to ever live on land, were the plant-eating, long-necked Sauropoda. The tallest and heaviest sauropod known from a complete skeleton is a specimen of an immature Giraffatitan discovered in Tanzania between 1907 and 1912, now mounted in the Museum f\u00FCr Naturkunde of Berlin. It is 12 m (39 ft) tall and weighed 23.3\u201339.5 tonnes. The longest is a 25 m (82 ft) long specimen of Diplodocus discovered in Wyoming, and mounted in Pittsburgh's Carnegie Natural History Museum in 1907. A Patagotitan specimen found in Argentina in 2014 is estimated to have been 40 m (130 ft) long and 20 m (66 ft) tall, with a weight of 77 tonnes.\r\nThere were larger sauropods, but they are known only from a few bones. The current record-holders include Argentinosaurus, which may have weighed 73 tonnes; Supersaurus which might have reached 34 m (112 ft) in length and Sauroposeidon which might have been 18 m (59 ft) tall. Two other such sauropods include Bruhathkayosaurus and Amphicoelias fragillimus. Both are known only from fragments. Bruhathkayosaurus might have been between 40\u201344 m (131\u2013144 ft) in length and 175\u2013220 tonnes in weight according to some estimates. A. fragillimus might have been approximately 58 m long and 122.4 metric tons in weight.\r\nTheropods (Theropoda)\r\nThe largest theropod known from a nearly complete skeleton is the biggest and most complete Tyrannosaurus rex specimen, nicknamed \"Sue\", which was discovered in South Dakota in 1990 and now mounted in the Field Museum of Chicago at a total length of 12.3 m (40 ft). Body mass estimates have reached over 9,500 kg, though other figures, such as Hartman\u2019s 2013 estimate of 8,400 kg, have been lower.\r\nAnother giant theropod is the semi-aquatic Spinosaurus aegyptiacus from the mid-Cretaceous of North Africa. Size estimates have been fluctuating far more over the years, with length estimates ranging from 12.6 to 18 m and mass estimates from 7 to 20.9 t. Recent findings favour a length exceeding 15 m  and a body mass of 7.5 tons.\r\nOther contenders known from partial skeletons include Giganotosaurus carolinii (est. 12.2\u201313.2 m and 6-13.8 tonnes) and Carcharodontosaurus saharicus (est. 12-13.3 m and 6.2-15.1 tonnes).\r\nThe largest extant theropod is the Ostrich (see birds, below).\r\nArmored dinosaurs (Thyreophora)The largest thyreophorans were Ankylosaurus and Stegosaurus, from the Late Cretaceous and Late Jurassic periods (respectively) of what is now North America, both measuring up to 9 m (30 ft) in length and estimated to weigh up to 6 tonnes.Ornithopods (Ornithopoda)The largest ornithopods, were the hadrosaurids Shantungosaurus, a late Cretaceous dinosaur found in the Shandong Peninsula of China, and Magnapaulia from the late Cretaceous of North America. Both species are known from fragmentary remains but are estimated to have reached over 15 m (49 ft) in length and were likely the heaviest non-sauropod dinosaurs, estimated at over 23 tonnes.Ceratopsians (Ceratopsia)The largest ceratopsians were Triceratops and its ancestor Eotriceratops from the late Cretaceous of North America. Both estimated to have reached about 9 m (30 ft) in length and weighed 12 tonnes.\r\n\r\n\r\n==== Birds (Aves) ====\r\n\r\nThe largest living bird, a member of the Struthioniformes, is the common ostrich (Struthio camelus), from the plains of Africa and Arabia. A large male ostrich can reach a height of 2.8 m (9.2 ft) and weigh over 156 kg (344 lb). A mass of 200 kg (440 lb) has been cited for the common ostrich but no wild ostriches of this weight have been verified. Eggs laid by the ostrich can weigh 1.4 kg (3.1 lb) and are the largest eggs in the world today.\r\n\r\nThe largest bird in the fossil record may be the extinct elephant birds (Aepyornis) of Madagascar, which were related to the ostrich. They exceeded 3 m (9.8 ft) in height and 500 kg (1,100 lb). The last of the elephant birds became extinct about 300 years ago. Of almost exactly the same upper proportions as the largest elephant birds was Dromornis stirtoni of Australia, part of a 26,000-year-old group called mihirungs of the family Dromornithidae. The largest carnivorous bird was Brontornis, an extinct flightless bird from South America which reached a weight of 350 to 400 kg (770 to 880 lb) and a height of about 2.8 m (9 ft 2 in). The tallest carnivorous bird was Kelenken, which could reach 3 to 3.2 meters in height and 220 to 250 kilograms. The tallest bird ever was the giant moa (Dinornis maximus), part of the moa family of New Zealand that went extinct around 1500 AD. This particular species of moa stood up to 3.7 m (12 ft) tall, but weighed about half as much as a large elephant bird or mihirung due to its comparatively slender frame.The heaviest bird ever capable of flight was Argentavis magnificens, the largest member of the now extinct family Teratornithidae, found in Miocene-aged fossil beds of Argentina, with a wingspan up to 5.5 m (18 ft), a length of up to 1.25 m (4.1 ft), a height on the ground of up to 1.75 m (5.7 ft) and a body weight of at least 71 kg (157 lb). Pelagornis sandersi is thought to have had an even larger wingspan of about 6.1\u20137.4 m (20\u201324 ft), but is only about 22\u201340 kg (49\u201388 lb), half the mass of the former.\r\n=== Table of heaviest living bird species ===The following is a list of the heaviest living bird species based on maximum reported or reliable mass, but average weight is also given for comparison. These species are almost all flightless, which allows for these particular birds to have denser bones and heavier bodies. Flightless birds comprise less than 2% of all living bird species. \r\n\r\n\r\n==== Amphibians (Amphibia) ====\r\n\r\nThe largest living amphibian is the Chinese giant salamander (Andrias davidianus). The maximum size of this nearly human-sized river-dweller is 64 kg (141 lb) and almost 1.83 m (6.0 ft). Before amniotes became the dominant tetrapods, several giant amphibian proto-tetrapods existed and were certainly the dominant animals in their ecosystems. The largest known was the crocodile-like Prionosuchus, which reached a length of 9 m (30 ft).\r\nFrogs (Anura)The largest member of the largest order of amphibians is the African Goliath frog (Conraua goliath). The maximum size this species is verified to attain is a weight of 3.8 kg (8.4 lb) and a snout-to-vent length of 39 cm (15 in). The largest of the toads, the cane toad (Rhinella marina), is also the second largest member of the frog order. This infamous, often invasive species can grow to maximum mass of 2.65 kg (5.8 lb) and measure a maximum of 33 cm (13 in) from snout-to-vent. Rivaling the previous two species, the African bullfrog (Pyxicephalus adspersus) can range up to a weight of 2 kg (4.4 lb) and 25.5 cm (10.0 in) from snout to vent. Another large frog is the largest frog in North America, the American bullfrog, which can reach weights of up to 0.8 kg (1.8 lb) and snout-to-vent-length (SVL) of 20 cm (7.9 in). However, the toad Beelzebufo ampinga, found in fossil from the Cretaceous era in what is now Madagascar, could grow to be 41 cm (16 in) long and weigh up to 4.5 kg (9.9 lb), making it the largest frog ever known. The largest tree frog is the Australasian white-lipped tree frog (Litoria infrafrenata), the females of which can reach a length of 14 cm (5.5 in) from snout to vent and can weigh up to 115 g (4.1 oz). The family Leptodactylidae, one of the most diverse anuran families, also has some very large members. The largest is the Surinam horned frog (Ceratophrys cornuta), which can reach 20 cm (7.9 in) in length from snout to vent and weigh up to 0.48 kg (1.1 lb). While not quite as large as Ceratophrys cornuta, Leptodactylus pentadactylus is often heavier; it can reach 18.5 cm (7.3 in) long and weigh 0.60 kilograms (1.3 pounds). The largest dendrobatid is the Colombian golden poison frog (Phyllobates terribilis), which can attain a length of 6 cm (2.4 in) and nearly 28.3 g (1.00 oz). Most frogs are classified under the suborder Neobatrachia, although nearly 200 species are part of the Mesobatrachia suborder, or ancient frogs. The largest of these are the little-known Brachytarsophrys or Karin Hills frogs, of South Asia, which can grow to a maximum snout-to-vent length of 17 cm (6.7 in) and a maximum weight of 0.54 kg (1.2 lb).\r\nCaecilians (Gymnophiona)The largest of the worm-like caecilians is the Colombian Thompson's caecilian (Caecilia thompsoni), which reaches a length of 1.5 m (4.9 ft), a width of about 4.6 cm (1.8 in) and can weigh up to about 1 kg (2.2 lb).Salamanders (Urodela)Besides the previously mentioned Chinese giant salamander, the closely related Japanese giant salamander (Andrias japonicus) is also sometimes cited as the largest living amphibian, but salamanders of a greater size than 1.53 m (5.0 ft) and 36 kg (79 lb) have never been verified for this species. Another giant of the amphibian world is the North American Hellbender (Cryptobranchus alleganiensis), which can measure up to 0.76 m (2.5 ft). The largest of the newts is the Iberian ribbed newt (Pleurodeles waltl), which can grow up to 30 cm (12 in) in length.\r\n\r\n\r\n==== Fish ====\r\n\r\n\r\n=== Invertebrates ===\r\n\r\n\r\n==== Sponges (Porifera) ====\r\n\r\nThe largest known species of sea sponge is the giant barrel sponge, Xestospongia muta. These massively built sponges can reach 2.4 m (8 ft) in height and can be of about the same number of feet across at the thickest part of the \"body\". Some of these creatures have been estimated to be over 2,400 years of age.\r\nCalcareous sponges (Calcarea)The largest known of these small, inconspicuous sponges is probably the species Pericharax heteroraphis, attaining a height of 30 cm (0.98 ft). Most calcareous sponges do not exceed 10 cm (3.9 in) tall.Hexactinellid sponges (Hexactinellida)A relatively common species, Rhabdocalyptus dawsoni, can reach a height of 1 m (3.3 ft) once they are of a very old age. This is the maximum size recorded for a hexactinellid sponge.\r\n\r\n\r\n==== Cnidarians (Cnidaria) ====\r\n\r\nThe lion's mane jellyfish (Cyanea capillata) is the largest cnidaria species, of the class Scyphozoa. The largest known specimen of this giant, found washed up on the shore of Massachusetts Bay in 1870, had a bell diameter of 2.5 m (8.2 ft), a weight of 150 kg (330 lb). The tentacles of this specimens were as long as 37 m (121 ft) and were projected to have a tentacular spread of about 75 m (246 ft) making it one of the longest extant animals.\r\nCorals and sea-anemones (Anthozoa)The largest individual species are the sea-anemones of the genus Discoma, which can attain a mouth disc diameter of 60 cm (2.0 ft). Longer, but much less massive overall, are the anemones of the genus Ceriantharia, at up to 2 m (6.6 ft) tall. Communities of coral can be truly massive, a single colony of the genus Porites can be over 10 m (33 ft), but the actual individual organisms are quite small.Lion's mane jellyfishThe largest known species of jellyfish is the \"lion's mane jellyfish\". The largest of its kind was found in 1870 in Massachusetts Bay with a recorded bell size of 2.3 metres (7 feet 7 inches) and a tentacle length of 37 metres (121 feet).Hydrozoans (Hydrozoa)The colonial siphonophore Praya dubia can attain lengths of 40\u201350 m (130\u2013160 ft). The Portuguese man o' war's (Physalia physalis) tentacles can attain a length of up to 50 m (160 ft).\r\n\r\n\r\n==== Flatworms (Platyhelminthes) ====\r\nMonogenean flatworms (Monogenea)The largest known members of this group of very small parasites are among the genus of capsalids, Listrocephalos, reaching a length of 2 cm (0.79 in).Flukes (Trematoda)The largest known species of fluke is Fasciolopsis buski, which most often attacks humans and livestock. One of these flukes can be up to 7.5 cm (3.0 in) long and 2 cm (0.79 in) thick.Tapeworms (Cestoda)The largest known species of tapeworm is the whale tapeworm, Polygonoporus giganticus, which can grow to over 30 m (98 ft).\r\n\r\n\r\n==== Roundworms (Nematoda) ====\r\nThe largest roundworm, Placentonema gigantissima, is a parasite found in the placentas of sperm whales which can reach up to 9 m (30 ft) in length.\r\n\r\n\r\n==== Segmented worms (Annelida) ====\r\nThe largest of the segmented worms (commonly called earthworms) is the African giant earthworm (Microchaetus rappi). Although it averages about 1.36 m (4.5 ft) in length, this huge worm can reach a length of as much as 6.7 m (22 ft) and can weigh over 1.5 kg (3.3 lb). Only the giant Gippsland earthworm, Megascolides australis, and a few giant polychaetes, including the notorious Eunice aphroditois, reach nearly comparable sizes, reaching 4 and 3.6 m (13 and 12 ft), respectively.\r\n\r\n\r\n==== Echinoderms (Echinodermata) ====\r\n\r\nThe largest species of echinoderm in terms of bulk is probably the starfish species Thromidia gigas, of the class Asteroidea, which reaches a weight of over 6 kg (13 lb), but it might be beaten by some giant sea cucumbers such as Thelenota anax. However, at a maximum span of 63 cm (25 in), Thromidia gigas is quite a bit shorter than some other echinoderms. The longest echinoderm known is the conspicuous sea cucumber Synapta maculata, with a slender body that can extend up to 3 m (9.8 ft). In comparison, the biggest sea star is the brisingid sea star Midgardia xandaros, reaching a span of 1.4 m (4.6 ft), despite being quite slender. Evasterias echinosoma is another giant echinoderm and can measure up to 1 m (3.3 ft) across and weigh 5.1 kg (11 lb).\r\nCrinoids (Crinoidea)The largest species of crinoid is the unstalked feather-star Heliometra glacialis, reaching a total width of 78 cm (31 in) and an individual arm length of 35 cm (14 in). A width of 91.4 cm (36.0 in) was claimed for one unstalked feather-star but is not confirmed. The genus Metacrinus has a stalk span of 61 cm (24 in) but, due to its bulk and multiple arms, it is heavier than Heliometra. In the past, crinoids grew much larger, and stalk lengths up to 40 m (130 ft) have been found in the fossil record.Sea urchins and allies (Echinoidea)The largest sea urchin is the species Sperosoma giganteum from the deep northwest Pacific Ocean, which can reach a shell width of about 30 cm (12 in). Another deep sea species Hygrosoma hoplacantha is only slightly smaller. The largest species found along the North America coast is the Pacific red sea urchin (Mesocentrotus franciscanus) where the shell can reach 19 cm (7.5 in). If the spines enter into count, the biggest species may be a Diadematidae like Diadema setosum, with a test up to 10 cm (3.9 in) only, but its spines can reach up to 30 cm (12 in) in length.Sea cucumbers (Holothuroidea)The bulkiest species of sea cucumber are Stichopus variegatus and Thelenota anax, weighing several pounds, being about 21 cm (8.3 in) in diameter, and reaching a length of 1 m (3.3 ft) when fully extended. Synapta maculata can reach an extended length of 3 m (9.8 ft), but is extremely slender (3-5cm) and weigh much less than Stichopodids.Brittle stars (Ophiuroidea)The largest known specimen of brittle star is the basket star Astrotoma agassizii. This species can grow to have a span of 1 m (3.3 ft). Sometimes, Gorgonocephalus stimpsoni is considered the largest but the maximum this species is can measure 70 cm (28 in) and a disk diameter of about 14.3 cm (5.6 in). Outside from euryalids, the biggest ophiurid brittle star may be Ophiopsammus maculata (6-7 inches).Sea stars (Asteroidea)The heaviest sea star is Thromidia gigas from the Indo-Pacific, which can surpass 6 kg (13 lb) in weight, but only has a diameter of about 65 cm (2.13 ft). Despite its relatively small disk and weight, the long slender arms of Midgardia xandaros from the Gulf of California makes it the sea star with the largest diameter at about 1.4 m (4.5 ft). Mithrodia clavigera may also become wider than 1 m (39 in) in some cases, with stout arms.\r\n\r\n\r\n==== Ribbon worms (Nemertea) ====\r\nThe largest nemertean is the bootlace worm, Lineus longissimus. A specimen found washed ashore on a beach in St. Andrews, Scotland in 1864 was recorded at a length of 55 m (180 ft).\r\n\r\n\r\n==== Mollusks (Mollusca) ====\r\n\r\nBoth the largest mollusks and the largest of all invertebrates (in terms of mass) are the largest squids. The colossal squid (Mesonychoteuthis hamiltoni) is projected to be the largest invertebrate. Current estimates put its maximum size at 12 to 14 m (39 to 46 ft) long and 750 kg (1,650 lb), based on analysis of smaller specimens. In 2007, authorities in New Zealand announced the capture of the largest known colossal squid specimen. It was initially thought to be 10 m (33 ft) and 450 kg (990 lb). It was later measured at 4.2 m (14 ft) long and 495 kg (1,091 lb) in weight. The mantle was 2.5 m (8.2 ft) long when measured.\r\nThe giant squid (Architeuthis dux) was previously thought to be the largest squid, and while it is less massive and has a smaller mantle than the colossal squid, it may exceed the colossal squid in overall length including tentacles. One giant squid specimen that washed ashore in 1878 in Newfoundland reportedly measured 18 m (59 ft) in total length (from the tip of the mantle to the end of the long tentacles), head and body length 6.1 m (20 ft), 4.6 m (15 ft) in diameter at the thickest part of mantle, and weighed about 900 kg (2,000 lb). This specimen is still often cited as the largest invertebrate that has ever been examined. However, no animals approaching this size have been scientifically documented and, according to giant squid expert Steve O'Shea, such lengths were likely achieved by greatly stretching the two tentacles like elastic bands.\r\nAplacophorans (Aplacophora)The largest known of these worm-like, shell-less mollusks are represented in the genus Epimenia, which can reach 30 cm (12 in) long. Most aplacophorans are less than 5 cm (2.0 in) long.Chitons (Polyplacophora)The largest of the chitons is the gumboot chiton, Cryptochiton stelleri, which can reach a length of 33 cm (13 in) and weigh over 2 kg (4.4 lb).\r\nBivalves (Bivalvia)The largest of the bivalve mollusks is the giant clam, Tridacna gigas. Although even larger sizes have been reported for this passive animal, the top verified size was for a specimen from the Great Barrier Reef. This creature weighed 270 kg (600 lb), had an axial length of 1.14 m (3.7 ft) and depth of 0.75 m (2.5 ft). The largest bivalve ever was Platyceramus platinus, a Cretaceous giant that reached an axial length of up to 3 m (nearly 10 ft).Gastropods (Gastropoda)The \"largest\" of this most diverse and successful mollusk class of slugs and snails can be defined in various ways.\r\nThe living gastropod species that has the largest (longest) shell is Syrinx aruanus with a maximum shell length of 0.91 m (3.0 ft), a weight of 18 kg (40 lb) and a width of 96 cm (38 in). Another giant species is Melo amphora, which in a 1974 specimen from West Australia, measured 0.71 m (2.3 ft) long, had a maximum girth of 0.97 m (3.2 ft) and weighed 16 kg (35 lb).\r\nThe largest shell-less gastropod is the giant black sea hare (Aplysia vaccaria) at 0.99 m (3.2 ft) in length and almost 14 kg (31 lb) in weight.\r\nThe largest of the land snails is the giant African snail (Achatina achatina) at up to 1 kg (2.2 lb) and 35 cm (14 in) long.Cephalopods (Cephalopoda)(See Cephalopod size.) While generally much smaller than the giant Architeuthis and Mesonychoteuthis, the largest of the octopuses, the giant Pacific octopus (Enteroctopus dofleini), can grow to be very large. The largest confirmed weight of a giant octopus is 74 kg (163 lb), with a 7 m (23 ft) arm span (with the tentacles fully extended) and a head-to-tentacle-tip length of 3.9 m (13 ft). Specimens have been reported up to 125 kg (276 lb) but are unverified.\r\n\r\n\r\n==== Velvet worms (Onychophora) ====\r\nSol\u00F3rzano's velvet worm (Peripatus solorzanoi) is the largest velvet worm known. An adult female was recorded to have a body length of 22 cm (approximately 8.7 in).\r\n\r\n\r\n==== Arthropods (Arthropoda) ====\r\n\r\nThe largest arthropod known to have existed is the eurypterid (sea scorpion) Jaekelopterus, reaching up to 2.5 m (8.2 ft) in body length, followed by the millipede relative Arthropleura at around 2.1 m (6.9 ft) in length. Among living arthropods, the Japanese spider crab (Macrocheira kaempferi) is the largest in overall size, the record specimen, caught in 1921, had an extended arm span of 3.8 m (12 ft) and weighed about 19 kg (42 lb). The heaviest is the American lobster (Homarus americanus), the largest verified specimen, caught in 1977 off of Nova Scotia weighed 20 kg (44 lb) and its body length was 1.1 m (3.6 ft). The largest land arthropod and the largest land invertebrate is the coconut crab (Birgus latro), up to 40 cm (1.3 ft) long and weighing up to 4 kg (8.8 lb) on average. Its legs may span 1 m (3.3 ft).\r\n\r\n\r\n===== Arachnids (Arachnida) =====\r\nBoth spiders and scorpions include contenders for the largest arachnids.\r\nSpiders (Araneae)The largest species of arachnid by length is probably the giant huntsman spider (Heteropoda maxima) of Laos, which in 2008 replaced the Goliath birdeater (Theraphosa blondi) of northern South America as the largest known spider by leg-span. However the most massive arachnids, of comparable dimensions and possibly even greater mass, are the Chaco golden knee, Grammostola pulchripes, and the Brazilian salmon pink, Lasiodora parahybana. The huntsman spider may span up to 29 cm (11 in) across the legs, while in the New World \"tarantulas\" like Theraphosa can range up to 26 cm (10 in). In Grammostola, Theraphosa and Lasiodora, the weight is projected to be up to at least 150 g (5.3 oz) and body length is up to 10 cm (3.9 in).Scorpions (Scorpiones)The largest of the scorpions is the species Heterometrus swammerdami of the Indian subcontinent, which have a maximum length of 29.2 cm (11.5 in) and weigh around 60 g (2.1 oz). Another extremely large scorpion is the African emperor scorpion (Pandinus imperator), which can weigh 57 g (2.0 oz) but is not known to exceed a length of 23 cm (9.1 in). However, they were dwarfed by Pulmonoscorpius kirktonensis, a giant extinct species of scorpion from Scotland, at an estimated length of 0.7 m (2.3 ft) and weight of 15 kg (33 lb), and the aquatic Brontoscorpio, at up to 1 m (3.3 ft) and a similar weight.Pseudoscorpions (Pseudoscorpiones)The largest pseudoscorpion is Garypus titanius, from Ascension island, which can be 12 mm (0.47 in) long.\r\n\r\n\r\n===== Crustaceans (Crustacea) =====\r\nThe largest crustaceans are crab Tasmanian giant crab (''Pseudocarcinus gigas) 13 kilograms (29 lb) and a carapace width of up to 46 centimetres (18 in). It is the only species in the genus Pseudocarcinus. Males reach more than twice the size of females. It has a white shell with claws that are splashed in red. The females' shells change colour when they are producing eggs. Lysiosquillina maculata At a length of up to 40 cm, L. maculata is the largest mantis shrimp in the world. L. maculata may be distinguished from its congener L. sulcata by the greater number of teeth on the last segment of its raptorial claw, and by the colouration of the uropodal endopod, the distal half of which is dark in L. maculata but not in L. sulcata. There is a small artisanal fishery for this species. are largest shrimps  Tasmanian giant freshwater crayfish (Astacopsis gouldi)  5 kilograms (11 lb) in weight and over 80 centimetres (31 in) long have been known in the past, but now, even individuals over 2 kilograms (4.4 lb) are rare. The species is only found in Tasmanian rivers flowing north into the Bass Strait below 400 metres (1,300 ft) above sea level, and is listed as an endangered species on the IUCN Red List.Branchiopods (Branchiopoda)The largest of these primarily freshwater crustaceans is probably Branchinecta gigas, which can reach a length 10 cm (3.9 in).Barnacles and allies (Maxillopoda)The largest species is a copepod (Pennella balaenopterae), known exclusively as a parasite from the backs of fin whales (Balaenoptera physalus). The maximum size attained is 32 cm (about 13 in). The largest of the barnacles is the giant acorn barnacle, Balanus nubilis, reaching 7 cm (2.8 in) in diameter and 12.7 cm (5.0 in) high.Ostracods (Ostracoda)The largest living representative of these small and little-known but numerous crustaceans is the species Gigantocypris australis females of which reaching a maximum length of 3 cm (1.2 in).Amphipods, isopods, and allies (Peracarida)\r\nThe largest species is the giant isopod (Bathynomus pergiganteus), which can reach a length of 45 cm (18 inches) and a weight of 1.7 kg (3.7 lb).Remipedes (Remipedia)The largest of these cave-dwelling crustaceans is the species Godzillius robustus, at up to 4.5 cm (1.8 in).\r\n\r\n\r\n===== Horseshoe crabs (Merostomata) =====\r\nThe four modern horseshoe crabs are of roughly the same sizes, with females measuring up to 60 cm (2.0 ft) in length and 5 kg (11 lb) in weight.\r\n\r\n\r\n===== Sea spiders (Pycnogonida) =====\r\nThe largest of the sea spiders is the deep-sea species Colossendeis colossea, attaining a leg span of nearly 60 cm (2.0 ft).\r\n\r\n\r\n===== Trilobites (Trilobita) =====\r\nSome of these extinct marine arthropods exceeded 60 cm (24 in) in length. A nearly complete specimen of Isotelus rex from Manitoba attained a length over 70 cm (28 in), and an Ogyginus forteyi from Portugal was almost as long. Fragments of trilobites suggest even larger record sizes. An isolated pygidium of Hungioides bohemicus implies that the full animal was 90 cm (35 in) long.\r\n\r\n\r\n===== Myriapods (Myriapoda) =====\r\nCentipedes (Chilopoda)\r\nThe biggest of the centipedes is Scolopendra gigantea of the neotropics, reaching a length of 33 cm (13 in).Millipedes (Diplopoda)Two species of millipede both reach a very large size: Archispirostreptus gigas of East Africa and Scaphistostreptus seychellarum, endemic to the Seychelles islands. Both of these species can slightly exceed a length of 28 cm (11 in) and measure over 2 cm (0.79 in) in diameter. The largest ever known was the Arthropleura, a gigantic prehistoric specimen that reached nearly 6.2 feet.\r\n\r\n\r\n===== Insects (Insecta) =====\r\n\r\nInsects, a class of Arthropoda, are easily the most numerous class of organisms, with over one million identified species, and probably many undescribed species. The heaviest insect is almost certainly a species of beetle, which incidentally is the most species-rich order of organisms. Although heavyweight giant wetas (Deinacrida heteracantha) are known, the elephant beetles of Central and South America, (Megasoma elephas) and (M. actaeon), the Titan beetle (Titanus giganteus) of the neotropical rainforests or the Goliath beetles, (Goliathus goliatus) and (G. regius), of Africa's rainforests are thought to reach a higher weight. The most frequently crowned are the Goliath beetles, the top known size of which is at least 100 g (3.5 oz) and 11.5 cm (4.5 in). The elephant beetles and titan beetle can reach greater lengths than the Goliath, at up to 13.1 and 15.2 cm (5.2 and 6.0 in), respectively, but this is in part thanks to their rather large horns. The Goliath beetle's wingspan can range up to 25 cm (9.8 in).Some moths and butterflies have much larger areas than the heaviest beetles, but weigh a fraction as much.\r\nThe longest insects are the stick insects, see below.\r\nRepresentatives of the extinct dragonfly-like order Protodonata such as the Carboniferous Meganeura monyi of what is now France and the Permian Meganeuropsis permiana of what is now North America are the largest insect species yet known to have existed. These creatures had a wingspan of some 75 cm (30 in) and a mass of over 1 pound (450 g), making them about the size of a crow.\r\nCockroaches and termites (Blattodea)\r\nThe largest cockroach is the Australian giant burrowing cockroach (Macropanesthia rhinoceros). This species can attain a length of 8.3 cm (3.3 in) and a weight of 36 g (1.3 oz). The giant cockroach (Blaberus giganteus) of the neotropics reaches comparable lengths although is not as massive as the burrowing species. The termites, traditionally classified in their own order (Isoptera), have recently been re-considered to belong in Blattodea. The largest of the termites is the African species Macrotermes bellicosus. The queen of this species can attain a length of 14 cm (5.5 in) and breadth of 5.5 cm (2.2 in) across the abdomen; other adults, on the other hand, are about a third of the size.Beetles (Coleoptera)The beetles are the largest order of organisms on earth, with about 400,000 species so far identified. The most massive species are the Goliathus, Megasoma and Titanus beetles already mentioned. Another fairly large species is the Hercules beetle (Dynastes hercules) of the neotropic rainforests with a maximum overall length of at least 19 cm (7.5 in) including the extremely long pronotal horn. The weight in this species does not exceed 16.5 g (0.58 oz). The longest overall beetle is a species of longhorn beetle, Batocera wallacei, from New Guinea, which can attain a length of 26.6 cm (10.5 in), about 19 cm (7.5 in) of which is comprised by the long antennae.Earwigs (Dermaptera)The largest of the earwigs is the Saint Helena giant earwig (Labidura herculeana), endemic to the island of its name, which is up to 8 cm (3.1 in) in length.True flies (Diptera)\r\nThe largest species of this order, which includes the common housefly, is the neotropical species Gauromydas heros, which can reach a length of 6 cm (2 3\u20448 in) and a wingspan of 10 cm (3.9 in). Species of crane fly, the largest of which is Holorusia brobdignagius, can attain a length of 23 cm (9.1 in) but are extremely slender and much lighter in weight than Gauromydas.Mayflies (Ephemeroptera)The largest mayflies are members of the genus Proboscidoplocia from Madagascar. These insects can reach a length of 7 cm (2.8 in).True bugs (Hemiptera)\r\nThe largest species of this diverse order is usually listed as the giant water bug in the genus Lethocerus, with L. maximus from the Neotropics being the absolutely largest. They can surpass 12 cm (4.7 in) in length, with some suggesting that the maximum size is 15 cm (5.9 in). It is more slender and less heavy than most other insects of this size (principally the huge beetles). The largest cicada is Megapomponia imperatoria, which has a head-body length of about 7 cm (2.8 in) and a wingspan of 18\u201320 cm (7\u20138 in). The cicadas of the genus Tacua can also grow to comparably large sizes. The largest type of aphid is the giant oak aphid (Stomaphis quercus), which can reach an overall length of 2 cm (0.79 in). The biggest species of leafhopper is Ledromorpha planirostris, which can reach a length of 2.8 cm (1.1 in).\r\nAnts and allies (Hymenoptera)The largest of the ants, and the heaviest species of the order, are the females of the African Dorylus helvolus, reaching a length of 5.1 cm (2.0 in) and a weight of 8.5 g (0.30 oz). The ant that averages the largest for the mean size within the whole colony is a ponerine ant, Dinoponera gigantea, from South America, averaging up to 3.3 cm (1.3 in) from the mandibles to the end of abdomen. Workers of the bulldog ant (Myrmecia brevinoda) of Australia are up to 3.7 cm (1.5 in) in total length, although much of this is from their extremely large mandibles. The largest of the bee species, also in the order Hymenoptera, is Megachile pluto of Indonesia, the females of which can be 3.8 cm (1.5 in) long, with a 6.3 cm (2.5 in) wingspan. Nearly as large, the carpenter bees can range up to 2.53 cm (1.00 in). The largest wasp is probably the so-called tarantula hawk species Pepsis pulszkyi of South America, at up to 6.8 cm (2.7 in) long and 11.6 cm (4.6 in) wingspan, although many other Pepsis approach a similar size. The giant scarab-hunting wasp Megascolia procer may rival the largest tarantula hawks in weight and wingspan, though its body is not as long.Moths and allies (Lepidoptera)\r\nThe Hercules moth (Coscinocera hercules), in the family Saturniidae, is endemic to New Guinea and northern Australia, and its wings have the largest documented surface area (300 square centimeters) of any living insect, and a maximum wingspan which is confirmed to 28 cm (11 in) while unconfirmed specimens have spanned up to 35.5 cm (14.0 in). The largest species overall is often claimed to be either the Queen Alexandra's birdwing (Ornithoptera alexandrae), a butterfly from Papua New Guinea, or the Atlas moth (Attacus atlas), a moth from Southeast Asia. Both of these species can reach a length of 8 cm (3.1 in), a wingspan of 28 cm (11 in) and a weight of 12 g (0.42 oz). One Atlas moth allegedly had a wingspan of 30 cm (12 in) but this measurement was not verified. The larvae in the previous species can weigh up to 58 and 54 g (2.0 and 1.9 oz), respectively. However, there are no reported measurements of surface area that would exceed the Hercules moth, and the white witch (Thysania agrippina) of Central and South America, has the largest recorded wingspan of the order, and indeed of any living insect, though the white witch is exceeded in surface area by the Hercules moth. The verified record-sized Thysania spanned 30.8 cm (12.1 in) across the wings, although specimens have been reported to 36 cm (14 in). The heaviest mature moths have been cited in the giant carpenter moth (Xyleutes boisduvali) of Australia, which has weighed up to 20 g (0.71 oz) although the species does not surpass 25.5 cm (10.0 in) in wingspan.Mantises (Mantodea)The largest species of this order is Toxodera denticulata from Java, which has been measured up to 20 cm (7.9 in) in overall length. However, an undescribed species from the Cameroon jungle is allegedly much larger than any other mantis and may rival the larger stick insects for the longest living insect. Among widespread mantis species, the largest is the Chinese mantis (Tenodera aridifolia). The females of this species can attain a length of up to 10.6 cm (4.2 in).Alderflies and allies (Megaloptera)This relatively small insect order includes some rather large species, many of which are noticeable for their elongated, imposing mandibles. The dobsonflies reach the greatest sizes of the order and can range up to 12.5 cm (4.9 in) in length.Net-winged insects (Neuroptera)\r\nThese flying insects reach their largest size in Palparellus voeltzkowi, which can have a wingspan over 16 cm (6.3 in). The largest lacewing is the \"blue eyes lacewing\" (Nymphes myrmeleonides) of Australia, which can measure up to 4 cm (1.6 in) in length and span 11 cm (4.3 in) across the wings. Some forms of this ancient order could grow extremely large during the Jurassic Era and may have ranked among the largest insects ever.Dragonflies (Odonata)The largest living species of dragonfly is Megaloprepus caerulatus of the neotropics, attaining a size of as much as 19 cm (7.5 in) across the wings and a body length of over 12 cm (4.7 in). Spanning up to 17.6 cm (6.9 in) and measuring up to 11.8 cm (4.6 in) long, Tetracanthagyna plagiata of Southeast Asia is bulkier and heavier than Megaloprepus at up to 7 g (0.25 oz). The largest species of dragonfly ever is the extinct aforementioned Meganeura, although it is not certain to be included in the modern dragonfly order.Grasshoppers and allies (Orthoptera)\r\nThe largest of this widespread, varied complex of insects are the giant wetas of New Zealand, which is now split among 12 species. The largest of these is the Little Barrier Island giant weta (Deinacrida heteracantha), the largest specimen was weighed at 71.3 g (2.52 oz), one of the largest insects weights ever known. These heavyweight insects can be over 9 cm (3.5 in) long. The largest grasshopper species is often considered to be the Australian giant grasshopper (Valanga irregularis), which ranges up to 9 cm (3.5 in) in length. The American eastern lubber grasshopper (Romalea guttata) can allegedly range up to 10 cm (3.9 in) in length. However, the greatest grasshopper sizes known, to 12 cm (4.7 in), have been cited in the South American giant grasshopper (Tropidacris violaceus). The longest members of this order (although much lighter than the giant wetas) is the katydid Macrolyristes corporalis of Southeast Asia which can range up to 21.5 cm (8.5 in) with its long legs extended and can have a wingspan of 20 cm (7.9 in).Stick insects (Phasmatodea)The longest known stick insect, and indeed the longest insect ever known, is Phobaeticus chani of the Bornean rainforests, with one specimen held in the Natural History Museum in London measuring 56.7 cm (22.3 in) in total length. This measurement is, however, with the front legs fully extended. The body alone still measures 35.7 cm (14.1 in). The species with the second longest body is Phobaeticus kirbyi, also of Borneo, which measures up to 32.8 cm (12.9 in), while the overall length (from the hind to the front legs) is up to 54.6 cm (21.5 in). The second longest insect in terms of total length is Phobaeticus serratipes of Malaysia and Singapore, measuring up to 55.5 cm (21.9 in). Another extremely long stick insect is Pharnacia maxima, which measured 51 cm (20 in) with its legs extended. The spiny stick insect (Heteropteryx dilatata) of Malaysia does not reach the extreme lengths of its cousins, the body reaching up to 16 cm (6.3 in) long, but it is much bulkier. The largest Heteropteryx weighed about 65 g (2.3 oz) and was 3.5 cm (1.4 in) wide across the thickest part of the body.Lice (Phthiraptera)These insects, which live parasitically on other animals, are as a rule quite small. The largest known species is the hog louse, Haematopinus suis, a sucking louse that lives on large livestock like pigs and cattle. It can range up to 6 mm (0.24 in) in length.Stoneflies (Plecoptera)\r\nThe largest species of stonefly is Pteronarcys californica of western North America, a species favored by fishermen as lures. This species can attain a length of 5 cm (2.0 in) and a wingspan of over 9.5 cm (3.7 in).Booklice (Psocoptera)The largest of this order of very small insects are the barklice of the genus Psocus, the top size of which is about 1 cm.Fleas (Siphonaptera)The largest species of flea is Hystrichopsylla schefferi. This parasite is known exclusively from the fur of the mountain beaver (Aplodontia rufa) and can reach a length of 1.2 cm (0.47 in).Silverfishes and allies (Thysanura)These strange-looking insects, known to feed on human household objects, can range up to 4.3 cm (1.7 in) in length. A 350 million year old form was known to grow quite large, at up to 6 cm (2.4 in).Thrips (Thysanoptera)Members of the genus Phasmothrips are the largest kinds of thrips. The maximum size these species attain is approximately 1.3 cm (0.51 in) in length.Caddisflies (Trichoptera)The largest of the small, moth-like caddisflies is Eubasilissa maclachlani. This species can range up to 7 cm (2.8 in) across the wings.\r\n\r\n\r\n== Fungi ==\r\n\r\nThe largest living fungus may be a honey fungus of the species Armillaria ostoyae.\r\nA mushroom of this type in the Malheur National Forest in the Blue Mountains of eastern Oregon, U.S. was found to be the largest fungal colony in the world, spanning 8.9 km2 (2,200 acres) of area. This organism is estimated to be 2,400 years old. The fungus was written about in the April 2003 issue of the Canadian Journal of Forest Research. While an accurate estimate has not been made, the total weight of the colony may be as much as 605 tons. If this colony is considered a single organism, then it is the largest known organism in the world by area, and rivals the aspen grove \"Pando\" as the known organism with the highest living biomass. It is not known, however, whether it is a single organism with all parts of the mycelium connected.In Armillaria ostoyae, each individual mushroom (the fruiting body, similar to a flower on a plant) has only a 5 cm (2.0 in) stipe, and a pileus up to 12.5 cm (4.9 in) across. There are many other fungi which produce a larger individual size mushroom. The largest known fruiting body of a fungus is a specimen of Phellinus ellipsoideus (formerly Fomitiporia ellipsoidea) found on Hainan Island. The fruiting body masses up to 500 kg (1,100 lb).Until P. ellipsoideus replaced it, the largest individual fruit body came from Rigidoporus ulmarius. R. ulmarius can grow up to 284 kg (626 lb), 1.66 m (5.4 ft) tall, 1.46 m (4.8 ft) across, and has a circumference of up to 4.9 m (16 ft).\r\n\r\n\r\n== Protists ==\r\n\r\n(Note: the group Protista is not used in current taxonomy.)\r\n\r\n\r\n=== Amoebozoans (Amoebozoa) ===\r\nAmong the organisms that are not multicellular, the largest are the slime moulds, such as Physarum polycephalum, some of which can reach a diameter over 30 cm (12 in). These organisms are unicellular, but they are multinucleate.\r\n\r\n\r\n=== Euglenozoans (Euglenozoa) ===\r\nSome euglenophytes, such as certain species of Euglena, reach lengths of 400 \u03BCm.\r\n\r\n\r\n=== Rhizarians (Rhizaria) ===\r\nThe largest species traditionally considered protozoa are giant amoeboids like foraminiferans. One such species, the xenophyophore Syringammina fragilissima, can attain a size of 20 cm (7.9 in).\r\n\r\n\r\n=== Alveolates (Alveolata) ===\r\nThe largest ciliates, such as Spirostomum, can attain a length over 4 mm (0.16 in).\r\n\r\n\r\n=== Stramenopiles (Stramenopila) ===\r\nThe largest stramenopiles are giant kelp from the northwestern Pacific. The floating stem of Macrocystis pyrifera can grow to a height of over 45 m (148 ft).\r\nMacrocystis also qualifies as the largest brown alga, the largest chromist, and the largest protist generally.\r\n\r\n\r\n== Bacteria ==\r\n\r\nThe largest known species of bacterium is Thiomargarita namibiensis, which grows to 0.75 mm (0.030 in) in diameter, making it visible to the naked eye and a thousand times the size of more typical bacteria.\r\n\r\nCyanobacteriaOne of the largest \"blue green algae\" is Lyngbya, whose filamentous cells can be 50 \u03BCm wide.\r\n\r\n\r\n== Viruses ==\r\n\r\nThe largest virus on record so far is the Pithovirus sibericum with the length of 1.5 micrometres, comparable to the typical size of a bacterium and large enough to be seen in light microscopes. It was discovered in March 2014 in a soil sample collected from a riverbank in Siberia. Prior to this discovery, the largest virus was the peculiar virus genus Pandoravirus, which have a size of approximately 1 micrometer and whose genome contains 1,900,000 to 2,500,000 base pairs of DNA.Both these viruses infect amoebas specifically.\r\n\r\n\r\n== See also ==\r\n\r\n\r\n== References ==\r\n\r\n\r\n== External links ==\r\n10 of the largest living things on the planet Melissa Breyer. TreeHugger April 28, 2015")
    #
    # print(search_data(variation,[(0.0,x) for x in doc.sents]))