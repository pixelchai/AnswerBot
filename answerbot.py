from python_log_indenter import IndentedLoggerAdapter
import logging
import spacy
nlp=spacy.load('en')
log=IndentedLoggerAdapter(logging.getLogger(__name__))
logging.basicConfig(level=logging.DEBUG,format='[%(asctime)s][%(levelname)s] %(message)s',datefmt='%H:%M')

class AnswerBot:
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
        log.debug(str(doc.print_tree()))
        log.info("parsing question: "+str(doc))

        ret=[]
        for sent in doc.sents:
            ret.extend(self.parse_sent(sent))
        return ret

    def parse_sent(self, sent):
        #todo implement more query splitting here (e.g 'and')
        return [self.parse_span(sent)]

    def parse_span(self,span):
        return self.parse_children(span.root)

    def parse_children(self,root):
        ret=[]
        for child in root.children:
            if child.dep_=='poss':
                ret.append(root)
                ret.extend(self.parse_children(child))
        return ret

if __name__=='__main__':
    log.info(str(AnswerBot().parse_question("Obama's age")))