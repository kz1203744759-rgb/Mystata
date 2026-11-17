"""Regression tests for Stata and MCP-inspector numeric metadata."""
import unittest

from did_engine import validate_fixed_effects
from event_study_engine import validate_event_study
from mediation_engine import validate_mediation
from numeric_types import is_numeric_type
from statistics_engine import validate_statistics


class NumericTypeTest(unittest.TestCase):
    def setUp(self):
        self.dataset={'variables':[{'name':name,'type':kind} for name,kind in [
            ('y','int16'),('x','float64'),('control','float32'),('firm','int32'),
            ('year','float32'),('treated','int8'),('policy','int64'),('mediator','float64'),('text','str12')]]}
        self.spec={'outcome':'y','explanatory_variables':['x'],'controls':['control'],
                   'fixed_effects':[{'variables':['firm']},{'variables':['year']}],
                   'se_type':'cluster','cluster':'firm'}

    def test_actual_inspector_types_are_numeric_but_strings_are_not(self):
        for name in ('byte','int','long','float','double','int8','int16','int32','int64','uint8','float16','float32','float64'):
            with self.subTest(name=name):self.assertTrue(is_numeric_type(name))
        for name in ('str12','string','object','int16extra','float64text','',None):
            with self.subTest(name=name):self.assertFalse(is_numeric_type(name))

    def test_fixed_effects_and_statistics_accept_inspector_types(self):
        self.assertEqual(validate_fixed_effects(self.spec,self.dataset)['outcome'],'y')
        self.assertEqual(validate_statistics({'variables':['y','x'],'kinds':['descriptive','correlation']},self.dataset)['variables'],['y','x'])
        with self.assertRaises(ValueError):validate_fixed_effects({**self.spec,'outcome':'text'},self.dataset)
        with self.assertRaises(ValueError):validate_statistics({'variables':['text'],'kinds':['descriptive']},self.dataset)

    def test_event_study_and_mediation_accept_inspector_types(self):
        event={'outcome':'y','unit':'firm','year':'year','treated':'treated','cohort':'policy',
               'min_period':-2,'max_period':1,'reference_period':-1,'controls':['control'],
               'fixed_effects':self.spec['fixed_effects'],'se_type':'cluster','cluster':'firm'}
        self.assertEqual(validate_event_study(event,self.dataset)['year'],'year')
        mediation={'method':'jiang','outcome':'y','exposure':'x','mediators':['mediator'],
                   'controls':['control'],'fixed_effects':self.spec['fixed_effects'],'se_type':'cluster','cluster':'firm'}
        self.assertEqual(validate_mediation(mediation,self.dataset)['mediators'],['mediator'])
