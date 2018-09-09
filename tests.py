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

if __name__=='__main__':
    unittest.main(verbosity=2)