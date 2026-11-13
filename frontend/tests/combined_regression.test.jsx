// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import CombinedRegression,{combinedTable,combinedWordContent} from '../components/CombinedRegression';
afterEach(cleanup);
const report=(n,controls,fixed)=>({dataset:'a.dta',outcome:'TFP',explanatory_variables:['chainleader'],controls,fixed_effects:fixed,se_type:'cluster',cluster:'city',n,r2:.8916,coefficients:[{variable:'chainleader',coefficient:.043734,se:.018501,p:.01877,omitted:false}]});
const reports=[report(100,[],[['firm'],['year']]),report(90,['size'],[['firm'],['year']]),report(80,['size','gdp'],[['firm'],['industry','year']]),report(70,['gdp'],[['province','year']])];
it('combines four actual model results without inventing control group membership',()=>{
  const table=combinedTable(reports,[0,1,2,3],[],[{name:'企业控制变量',variables:['size']},{name:'城市控制变量',variables:['gdp']}]);
  expect(table.rows[0].cells).toEqual(['chainleader','0.0437**','0.0437**','0.0437**','0.0437**']);
  expect(table.rows[1].cells[1]).toBe('(0.0185)');
  expect(table.rows.find(r=>r.cells[0]==='企业控制变量').cells).toEqual(['企业控制变量','否','是','是','否']);
  expect(table.rows.find(r=>r.cells[0]==='year 固定效应').cells).toEqual(['year 固定效应','是','是','否','否']);
  const html=combinedWordContent(table).html;
  expect(html).toContain('colspan="4"');expect(html).toContain('font-size:9pt');expect(html).toContain('<sup>**</sup>');
});
it('shows a user requested table and allows manual selection',()=>{
  const events=reports.map(r=>({fixed_effects_report:r}));
  events.push({combined_regression:{model_numbers:[1,2,3,4],variables:[],control_groups:[]}});
  render(<CombinedRegression events={events}/>);
  expect(screen.getByText('合并回归表')).toBeTruthy();
  expect(screen.getByRole('button',{name:'复制合并回归表到 Word'})).toBeTruthy();
  expect(screen.getByText('观测数')).toBeTruthy();
  fireEvent.click(screen.getByLabelText('模型 4 · TFP · N=70'));
  fireEvent.click(screen.getByText('生成合并表'));
  expect(screen.queryByText('70')).toBeNull();
});
