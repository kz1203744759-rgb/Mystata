// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {App} from '../main';

afterEach(()=>{cleanup();vi.restoreAllMocks()});
function setup(){
  Element.prototype.scrollIntoView=vi.fn();
  const dataset={filename:'data.dta',format:'dta',size:200,observations:2,variables:[],preview:[]};
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    const data=url==='/api/status'?{provider:'deepseek'}:
      url==='/api/workspace'?{dataset,loaded:true,raw_files:[],messages:[{role:'user',content:'之前的提问'},{role:'assistant',content:'之前的回复'}],events:[],artifacts:[]}:
      url==='/api/chat/clear'?{cleared:true}:null;
    if(!data)throw new Error(url);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
  render(<App/>);return fetcher;
}
it('clears conversation but retains the dataset and draft',async()=>{
  vi.spyOn(window,'confirm').mockReturnValue(true);const fetcher=setup();
  await screen.findByText('之前的提问');
  const input=screen.getByPlaceholderText('描述你的研究问题或下一步分析…');
  fireEvent.change(input,{target:{value:'尚未发送的内容'}});
  fireEvent.click(screen.getByRole('button',{name:'清空对话'}));
  await waitFor(()=>expect(screen.queryByText('之前的提问')).toBeNull());
  expect(screen.queryByText('之前的回复')).toBeNull();
  expect(screen.getAllByText('data.dta').length).toBeGreaterThan(0);
  expect(input.value).toBe('尚未发送的内容');
  expect(fetcher.mock.calls.some(([url])=>url==='/api/chat/clear')).toBe(true);
});
it('does not clear if confirmation is cancelled',async()=>{
  vi.spyOn(window,'confirm').mockReturnValue(false);const fetcher=setup();
  await screen.findByText('之前的提问');
  fireEvent.click(screen.getByRole('button',{name:'清空对话'}));
  expect(screen.getByText('之前的提问')).toBeTruthy();
  expect(fetcher.mock.calls.some(([url])=>url==='/api/chat/clear')).toBe(false);
});
