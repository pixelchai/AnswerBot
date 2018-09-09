from python_log_indenter import IndentedLoggerAdapter
import logging
import spacy
nlp=spacy.load('en')

class AnswerBot:
    def __init__(self,debug=True):
        #logging setup
        logger=logging.getLogger(__name__)

        formatter=logging.Formatter('[%(asctime)s][%(levelname)s] %(message)s', datefmt='%H:%M')
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        self.log=IndentedLoggerAdapter(logger)
        self.log.setLevel(logging.DEBUG if debug else logging.WARNING)

    @staticmethod
    def fix_question(text:str):
        if text.endswith('.'):
            text=text[:-1]
        if not text.endswith('?'):
            text=text+'?'
        return text[0].upper()+text[1:]

    def parse_question(self,text):
        """
        breaks down a natural-language query into a hierarchical structure
        :return: queries:[parts:[token]]
        """
        doc=nlp(self.fix_question(text))
        self.log.debug(str(doc.print_tree()))
        self.log.info("parsing question: "+str(doc))
        self.log.add()

        ret=[]
        for sent in doc.sents:
            ret.extend(self.parse_sent(sent))
        self.log.sub()
        self.log.info(str(ret))
        return ret

    def parse_sent(self, sent):
        #todo implement more query splitting here (e.g 'and')
        self.log.info("parsing sent: "+str(sent))
        return [self.parse_span(sent)]

    def parse_span(self,span):
        self.log.info("parsing span: "+str(span))
        self.log.add()
        ret = self.parse_children(span.root)
        self.log.sub()
        self.log.info("<<"+str(ret))
        return ret

    def parse_children(self,root,skip_root=False):
        self.log.info("parsing: "+str(root))
        self.log.add()

        ret=[]

        if root.lemma_=='be':
            pass
        else:
            # todo dependencies left to consider:
            # acl, advcl, advmod, appos, aux, cc, ccomp, clf, compound, conj, cop, csubj, dep, discourse
            # dislocated, expl, fixed, flat, goeswith, iobj, list, mark, nmod, nsubj, nummod, obj, obl
            # orphan, parataxis, reparandum, vocative, xcomp

            # agent, attr, auxpass, complm, cop, csubjpass, dobj, hmod, hyph, infmod, intj, meta, neg
            # nn, npadvmod, nsubjpass, num, number, oprd, partmod, pcmp, possesive, preconjj
            # prt, quantmod, rcmod

            ignore_deps=['case','punct','det'] # E.gs: 's, ?, the

            # before root
            for child in root.children:
                if child.dep_ in ignore_deps:
                    continue
                elif child.dep_=='prep':
                    ret.extend(self.parse_children(child,skip_root=True))
                elif child.dep_=='poss':
                    ret.extend(self.parse_children(child))

            if not skip_root:
                ret.append(root)

            # after root
            for child in root.children:
                if child.dep_ in ignore_deps:
                    continue
                elif child.dep_=='pobj':
                    ret.extend(self.parse_children(child))
                elif child.dep_=='amod':
                    ret.extend(self.parse_children(child))

        self.log.sub()
        self.log.info("<<"+str(ret))
        return ret

if __name__=='__main__':
    AnswerBot().parse_question("the biggest animal in the world")