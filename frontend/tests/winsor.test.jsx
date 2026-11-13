// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import WinsorWorkbench from '../components/WinsorWorkbench';

afterEach(()=>cleanup());
const dataset={variables:[{name:'id',type:'long'},{name:'year',type:'float'},{name:'ROE',type:'float'},{name:'Pay',type:'float'},{name:'SOE',type:'byte'}]};
it('requires user selection of variables, cutoffs and output mode',async()=>{
  const run=vi.fn().mockResolvedValue({report:{lower:1,upper:99,observations:100,changed:[{source:'ROE',target:'ROE_w',rows:2}]}});
  render(<WinsorWorkbench dataset={dataset} onRun={run} busy={false}/>);
  expect(screen.getByLabelText(/id/).disabled).toBe(true);
  expect(screen.getByLabelText('下分位点（%）').value).toBe('');
  expect(screen.getByLabelText('上分位点（%）').value).toBe('');
  fireEvent.click(screen.getByRole('button',{name:'运行缩尾并更新主分析集'}));
  expect(screen.getByRole('alert').textContent).toContain('选择需要缩尾');
  fireEvent.click(screen.getByLabelText(/ROE/));
  fireEvent.change(screen.getByLabelText('下分位点（%）'),{target:{value:'1'}});
  fireEvent.change(screen.getByLabelText('上分位点（%）'),{target:{value:'99'}});
  fireEvent.click(screen.getByLabelText('生成新变量，保留原变量'));
  fireEvent.click(screen.getByRole('button',{name:'运行缩尾并更新主分析集'}));
  await waitFor(()=>expect(run).toHaveBeenCalledWith({variables:['ROE'],lower:1,upper:99,mode:'new',suffix:'_w'}));
  expect(screen.getByText('缩尾完成')).toBeTruthy();
  expect(screen.getByLabelText('下分位点（%）').value).toBe('');
  expect(screen.getByLabelText('上分位点（%）').value).toBe('');
  expect(screen.getByLabelText('生成新变量，保留原变量').checked).toBe(false);
});
