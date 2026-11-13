// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, test, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import StatisticsWorkbench, {clipboardContent, descriptiveWordContent, tableModel} from '../components/StatisticsWorkbench';

afterEach(cleanup);
const report={dataset:'test.dta',variables:['X','Y'],descriptive:[{variable:'X',n:5,mean:3,sd:1,median:3,min:1,max:5}],correlation:[[{r:1,p:null,n:5},{r:.8,p:.03,n:4}],[{r:.8,p:.03,n:4},{r:1,p:null,n:4}]]};

test('renders statistical table with significance and safe Word markup',()=>{
  const table=tableModel(report,'correlation');
  expect(table.rows[1][1]).toBe('0.800**');
  const payload=clipboardContent({...table,title:'A < B'});
  expect(payload.html).toContain('A &lt; B');
  expect(payload.html).toContain('<table');
  expect(payload.plain).toContain('0.800**');
});

test('copies the descriptive table in the exact six-column Song small-five grid format',()=>{
  const source={descriptive:[{variable:'inno_leader',n:99,mean:3.717,median:3.892,sd:2.636,min:0,max:8.76},
    {variable:'x<script>',n:55,mean:-.32,median:1,sd:2,min:-3,max:4}]};
  const {html,plain}=descriptiveWordContent(source);
  const host=document.createElement('div');host.innerHTML=html;
  const rows=[...host.querySelectorAll('tr')].map(tr=>[...tr.querySelectorAll('td')]);
  expect(rows).toHaveLength(3);
  expect(rows[0].map(cell=>cell.textContent)).toEqual(['变量','均值','中位数','标准差','最小值','最大值']);
  expect(rows[1].map(cell=>cell.textContent)).toEqual(['inno_leader','3.717','3.892','2.636','0.000','8.760']);
  expect(rows[2][0].textContent).toBe('x<script>');
  expect(host.querySelector('script')).toBeNull();
  expect(html).toContain('font-size:9pt');
  expect(html).toContain('mso-fareast-font-family:SimSun');
  expect(rows[0][0].style.borderTop).toContain('1.5pt');
  expect(rows[1][0].style.borderRight).toContain('0.5pt');
  expect(rows[2][0].style.borderBottom).toContain('1.5pt');
  expect(rows[1][0].querySelector('span').style.fontStyle).toBe('italic');
  expect(rows[1][0].style.textAlign).toBe('center');
  expect(plain.split('\n')[0]).toBe('变量\t均值\t中位数\t标准差\t最小值\t最大值');
  expect(plain).not.toContain('样本量');
  expect(plain).not.toContain('描述性统计');
});

test('shows completed statistics with copy icons and no variable selection form',()=>{
  render(<StatisticsWorkbench events={[{statistics_report:report,error:false}]}/>);
  expect(screen.getByText('描述性统计')).toBeTruthy();
  expect(screen.getByText('Pearson 相关性检验')).toBeTruthy();
  expect(screen.getAllByRole('button',{name:'复制到 Word'})).toHaveLength(2);
  expect(screen.queryByRole('button',{name:'运行统计分析'})).toBeNull();
  expect(screen.queryByText('选择统计变量')).toBeNull();
});

test('copies rich text table for Word',async()=>{
  const write=vi.fn().mockResolvedValue();
  Object.defineProperty(navigator,'clipboard',{value:{write},configurable:true});
  vi.stubGlobal('ClipboardItem',class {constructor(items){this.items=items}});
  render(<StatisticsWorkbench dataset={null} events={[{statistics_report:report,error:false}]} onRun={()=>{}} busy={false}/>);
  fireEvent.click(screen.getAllByRole('button',{name:'复制到 Word'})[0]);
  await waitFor(()=>expect(write).toHaveBeenCalledOnce());
  expect(screen.getAllByRole('status')[0].textContent).toContain('已复制表格');
  vi.unstubAllGlobals();
});
