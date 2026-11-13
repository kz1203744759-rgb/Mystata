import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from winsor_engine import validate_winsor, prepare_agent_winsor, compile_winsor


class WinsorEngineTest(unittest.TestCase):
    def setUp(self):
        self.dataset = {'variables': [{'name': n} for n in ['id', 'year', 'ROE', 'Pay', 'ROE_w']]}
        self.args = {'variables': ['roe', 'pay'], 'excluded_variables': [], 'cut_kind': 'symmetric',
                     'p1': 5, 'p2': 0, 'mode': 'replace', 'suffix': '', 'scope': 'all'}

    def test_structured_cutoffs_and_canonical_names(self):
        for kind, first, second, expected in [('symmetric', 5, 0, (5, 95)),
                ('percentiles', 1, 99, (1, 99)), ('lower_tail', 5, 0, (5, 100)),
                ('upper_tail', 5, 0, (0, 95))]:
            with self.subTest(kind=kind):
                spec = prepare_agent_winsor({**self.args, 'cut_kind': kind, 'p1': first, 'p2': second}, self.dataset)
                self.assertEqual((spec['lower'], spec['upper']), expected)
                self.assertEqual(spec['variables'], ['ROE', 'Pay'])
                self.assertEqual(spec['mode'], 'replace')

    def test_checks_structure_and_conflicts(self):
        for changed in ({'variables': []}, {'variables': ['id']}, {'variables': ['missing']},
                        {'cut_kind': 'unspecified'}, {'cut_kind': 'symmetric', 'p1': 50},
                        {'cut_kind': 'symmetric', 'p1': 0}, {'mode': 'unspecified'},
                        {'scope': 'grouped'}, {'excluded_variables': ['PAY']}):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                prepare_agent_winsor({**self.args, **changed}, self.dataset)
        with self.assertRaises(ValueError):
            prepare_agent_winsor({**self.args, 'variables': ['ROE'], 'mode': 'new', 'suffix': '_w'}, self.dataset)

    def test_readable_code_preserves_actual_parameters(self):
        spec = prepare_agent_winsor(self.args, self.dataset)
        code = compile_winsor(spec, 'old', 'new', Path('out.dta'))
        self.assertIn('winsor2 ROE Pay, cuts(5 95) replace', code)
        readable = compile_winsor(spec, 'old', 'new', Path('out.dta'), readable=True)
        self.assertIn('winsor2 ROE Pay, cuts(5 95) replace', readable)

    def test_ui_validation_unchanged(self):
        spec = {'variables': ['Pay'], 'lower': 1, 'upper': 99, 'mode': 'new', 'suffix': '_w'}
        self.assertEqual(validate_winsor(spec, self.dataset)['suffix'], '_w')
        with self.assertRaises(ValueError):
            validate_winsor({**spec, 'lower': 0, 'upper': 100}, self.dataset)
