// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import MediationResults,{mediationTable,mediationWord} from '../components/MediationResults';
afterEach(cleanup);
const report={method:'fitted_two_stage',outcome:'y',exposure:'x',mediators:['m'],controls:['z'],fixed_effects:[['firm'],['year']],se_type:'cluster',cluster:'firm',dataset:'a.dta',models:[{outcome:'m',n:150,r2:.4,coefficients:[{variable:'x',coefficient:.7,se:.1,p:.001}]},{outcome:'y',n:145,r2:.5,coefficients:[{variable:'m_hat',coefficient:1.4,se:.3,p:.02}]}]};
it('renders two stages and honestly reports unadjusted second-stage inference',()=>{
  const t=mediationTable(report);expect(t.rows[0]).toEqual(['x','0.7000***','—']);expect(t.rows[2]).toEqual(['m_hat','—','1.4000**']);
  expect(t.note).toContain('未校正第一阶段');expect(mediationWord(report).html).toContain('font-size:9pt');
  render(<MediationResults events={[{mediation_report:report}]}/>);
  expect(screen.getByText('拟合值两阶段机制回归')).toBeTruthy();expect(screen.getByRole('button',{name:'复制中介结果到 Word'})).toBeTruthy();expect(screen.getByText(/未校正第一阶段/)).toBeTruthy();
});
