import spacy
nlp=spacy.load('en')

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
        :return: queries:[parts:[(word,type)]]
        """
        doc=nlp(self.fix_question(text))
        for sent in doc.sents:
            print(sent)

        for entity in doc.ents:
            print(entity)

if __name__=='__main__':
    AnswerBot().parse_question('how old is Barrack Obama')