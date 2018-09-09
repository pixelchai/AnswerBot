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

        #fails:
        #What sweet food is made by bees using nectar from flowers


if __name__=='__main__':
    unittest.main(verbosity=2)