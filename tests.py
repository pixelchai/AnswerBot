import unittest
from answerbot import AnswerBot

def strip_parsed(parsed):
    ret=[]
    for query in parsed:
        buf=[]
        for token in query:
            buf.append(str(token))
        ret.append(buf)
    return ret

class QuestionParsing(unittest.TestCase):
    def assertParsed(self, bot, query, other):
        self.assertEqual(strip_parsed(bot.parse_question(query)), other)

    def test_a_basic(self):
        bot=AnswerBot(debug=False)
        self.assertParsed(bot,"Obama's age",[['Obama','age']])
        self.assertParsed(bot,"Obama's dad's age",[['Obama','dad','age']])

        self.assertParsed(bot,"the biggest animal",[['animal','biggest']])
        self.assertParsed(bot,"the biggest animal in Europe",[['Europe','animal','biggest']])
        self.assertParsed(bot,"the biggest animal of Europe",[['Europe','animal','biggest']])
        self.assertParsed(bot,"the biggest animal from Europe",[['Europe','animal','biggest']])
        self.assertParsed(bot,"the biggest animal ever seen in Europe",[['Europe','animal','biggest']])
        self.assertParsed(bot,"Europe's biggest animal",[['Europe','animal','biggest']])

        self.assertParsed(bot,"what food is made by bees?",[["bees","food"]])

        self.assertParsed(bot,"name the school that Harry Potter attended.",[["Harry","Potter","school"]])

        self.assertParsed(bot,"Which country is home to the Kangaroo",[["Kangaroo","home","country"]])
        self.assertParsed(bot,"kangaroo's home country",[["Kangaroo","home","country"]])

        self.assertParsed(bot,"Which country sent an Armada to attack Britain in 1588",[["Armada","Britain","1588","country"]])
        self.assertParsed(bot,"In the nursery rhyme, who sat on a wall before having a great fall?",[["nursery","wall","fall","great","who","rhyme"]])

        self.assertParsed(bot,"From what tree do acorns come?",[["tree","acorns"]])

        self.assertParsed(bot,"Which river flows through London?",[["London","river"]])

        #slightly questionable:
        self.assertParsed(bot,"How many colours are in a rainbow?",[["rainbow","colours","many"]])
        self.assertParsed(bot,"What is the name of the bear in The Jungle Book?",[["What","bear","Jungle","Book","name"]])


        #fails:
        #

        #questionable:
        #What sweet food is made by bees using nectar from flowers
        #Saint Patrick is the Patron Saint of which country
        #what is the top colour in a rainbow --> includes "what" - spacy error
        #Where in Scotland is there supposedly a lake monster called Nessie?
        #What is the name of the policeman in the pre-school children’ television series Balamory?

        #v questionable:
        #Which big country is closest to New Zealand
        #Who created the children’s book character Tracy Beaker?


if __name__=='__main__':
    unittest.main(verbosity=2)