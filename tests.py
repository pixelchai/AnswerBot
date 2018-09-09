import unittest
from answerbot import AnswerBot

class QuestionParsing(unittest.TestCase):
    def test_a_basic(self):
        bot=AnswerBot()
        self.assertEqual(bot.parse_question("Obama's age"),
                         [
                             [('Obama',1),
                              ('age',0)]
                         ])

if __name__=='__main__':
    unittest.main(verbosity=2)