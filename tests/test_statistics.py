import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from statistics_engine import validate_statistics, compile_statistics, parse_statistics


class StatisticsTest(unittest.TestCase):
    def setUp(self):
        self.dataset={'filename':'data.dta','variables':[{'name':'X','type':'float','label':'指标 X'},{'name':'y','type':'double'},{'name':'text','type':'str8'}]}
    def test_validate_numeric_variables_and_method(self):
        self.assertEqual(validate_statistics({'variables':['x','y'],'kinds':['descriptive','correlation']},self.dataset)['variables'],['X','y'])
        for spec in ({'variables':['X'],'kinds':['correlation']},{'variables':['text'],'kinds':['descriptive']},
                     {'variables':['X','x'],'kinds':['descriptive']},{'variables':['X;drop'],'kinds':['descriptive']},
                     {'variables':['X'],'kinds':['spearman']}):
            with self.subTest(spec=spec),self.assertRaises(ValueError):validate_statistics(spec,self.dataset)
    def test_result_parsing_including_missing_and_pairwise(self):
        spec=validate_statistics({'variables':['X','y'],'kinds':['descriptive','correlation']},self.dataset)
        result=parse_statistics('D|1|5|3|1.5|3|1|5\nD|2|3|2|0|2|2|2\nC|1|2|3|.|.\n',spec,self.dataset)
        self.assertEqual(result['descriptive'][0]['median'],3)
        self.assertIsNone(result['correlation'][1][0]['r'])
        self.assertIsNone(result['correlation'][1][1]['r'])
        self.assertEqual(result['correlation'][0][1]['n'],3)
        self.assertIn("quietly summarize `variable', detail",compile_statistics(spec,Path('result.txt')))
        with self.assertRaises(ValueError):parse_statistics('D|1|5|3|1.5|3|1|5\n',spec,self.dataset)
