// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import EventStudyResults,{eventPlot,latexFormula} from '../components/EventStudyResults';
afterEach(cleanup);
const report={outcome:'TFP',min_period:-2,max_period:1,reference_period:-1,controls:['x'],pre_p:.22,n:200,points:[{period:-2,coefficient:-.1,lower:-.2,upper:0},{period:-1,coefficient:0,lower:null,upper:null,reference:true},{period:0,coefficient:.1,lower:0,upper:.2},{period:1,coefficient:.2,lower:.1,upper:.3}]};
it('plots real coefficients and draws confidence intervals except on reference period',()=>{
  const svg=eventPlot(report);expect(svg).toContain('stroke-dasharray');expect((svg.match(/<circle/g)||[]).length).toBe(4);
  expect(latexFormula(report)).toContain('k\\ne -1');expect(latexFormula(report)).toContain('\\gamma');
  render(<EventStudyResults events={[{event_study_report:report}]}/>);
  expect(screen.getByText(/政策前系数联合检验/)).toBeTruthy();expect(screen.getByRole('button',{name:'下载平行趋势图'})).toBeTruthy();expect(screen.getByRole('button',{name:'复制平行趋势公式'})).toBeTruthy();
});
