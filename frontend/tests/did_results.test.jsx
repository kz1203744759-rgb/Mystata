// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import DidResults from '../components/DidResults';
afterEach(cleanup);
it('shows the real DID coefficient, sample, fixed effects and copy icon',()=>{
  const report={dataset:'test.dta',outcome:'y',entity_fe:'id',time_fe:'year',se_type:'cluster',cluster:'id',n:100,r2:.4,clusters:20,coefficients:[{variable:'did',coefficient:2.1,se:.2,p:.001,omitted:false}]};
  render(<DidResults events={[{did_report:report,error:false}]}/>);
  expect(screen.getByText('2.100***')).toBeTruthy();
  expect(screen.getByText('(0.200)')).toBeTruthy();
  expect(screen.getByText('聚类：id')).toBeTruthy();
  expect(screen.getByRole('button',{name:'复制到 Word'})).toBeTruthy();
});
it('shows interaction fixed effects in the result table',()=>{
  const report={dataset:'test.dta',outcome:'y',fixed_effects:[['firm'],['industry','year']],se_type:'cluster',cluster:'firm',n:100,r2:.4,clusters:20,coefficients:[{variable:'did',coefficient:2.1,se:.2,p:.001,omitted:false}]};
  render(<DidResults events={[{fixed_effects_report:report,error:false}]}/>);
  expect(screen.getByText('firm + industry × year')).toBeTruthy();
  expect(screen.getByText('固定效应回归 · y')).toBeTruthy();
});
