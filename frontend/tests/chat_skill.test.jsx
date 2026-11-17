// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {App} from '../main';
import {TextEncoder,TextDecoder} from 'node:util';
globalThis.TextDecoder=TextDecoder;

afterEach(()=>{cleanup();vi.restoreAllMocks()});
it('rolls back the chosen DTA file and refreshes its displayed metadata',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const old={id:'a',filename:'sample.dta',format:'dta',size:100,observations:2,variables:[{name:'id'}]};
  const restored={...old,variables:[{name:'id'},{name:'name'}]};
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,text:async()=>JSON.stringify({provider:'deepseek'})};
    if(url==='/api/workspace')return {ok:true,text:async()=>JSON.stringify({dataset:null,loaded:false,raw_files:[old],messages:[],events:[],artifacts:[]})};
    if(url==='/api/dta/undo')return {ok:true,text:async()=>JSON.stringify({dataset:null,loaded:false,raw_files:[restored],research_variables:{},event:{tool:'undo_dta_change',label:'回滚 DTA 删列',output:'已回滚 sample.dta',error:false}})};
    throw new Error(url);
  });
  render(<App/>);
  fireEvent.click(await screen.findByRole('button',{name:'回滚 sample.dta'}));
  await screen.findByText('已回滚 sample.dta');
  const call=fetcher.mock.calls.find(([url])=>url==='/api/dta/undo');
  expect(JSON.parse(call[1].body)).toEqual({target:'raw',file_id:'a'});
});
it('sends a multi-file merge request to the agent while opening the ETL panel',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async (url)=>{
    let data;
    if(url==='/api/status')data={api_key_set:true,model:'test',provider:'deepseek',stata_found:true};
    else if(url==='/api/workspace')data={dataset:null,loaded:false,raw_files:[],messages:[],events:[],artifacts:[]};
    else if(url==='/api/chat/stream'){
      const data={answer:'我会先检查数据。',events:[],artifacts:[],dataset:null,loaded:false};
      const bytes=new TextEncoder().encode(JSON.stringify({type:'done',result:data})+'\n');let delivered=false;
      return {ok:true,status:200,body:{getReader:()=>({read:async()=>delivered?{done:true}:(delivered=true,{value:bytes,done:false}),releaseLock:()=>{}})}};
    }
    else throw new Error(`unexpected request ${url}`);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
  render(<App/>);
  await waitFor(()=>expect(fetcher).toHaveBeenCalledWith('/api/status',{}));
  const input=screen.getByPlaceholderText('描述你的研究问题或下一步分析…');
  fireEvent.change(input,{target:{value:'请检查并合并多文件数据'}});
  fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByText('我会先检查数据。');
  expect(fetcher.mock.calls.some(([url])=>url==='/api/chat/stream')).toBe(true);
  expect(fetcher.mock.calls.some(([url])=>url==='/api/etl/open')).toBe(false);
});

it('shows streamed text before completion and retains elapsed time on the answer',async()=>{
  Element.prototype.scrollIntoView=vi.fn();let release;
  const gate=new Promise(resolve=>{release=resolve});
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,text:async()=>JSON.stringify({provider:'deepseek'})};
    if(url==='/api/workspace')return {ok:true,text:async()=>JSON.stringify({dataset:null,loaded:false,raw_files:[],messages:[],events:[],artifacts:[]})};
    if(url==='/api/chat/stream'){
      let step=0;const encoder=new TextEncoder();
      return {ok:true,body:{getReader:()=>({read:async()=>{step++;if(step===1)return {value:encoder.encode('{"type":"delta","text":"正在分析"}\n'),done:false};if(step===2){await gate;return {value:encoder.encode(JSON.stringify({type:'done',result:{answer:'分析完成',events:[],artifacts:[]}})+'\n'),done:false}}return {done:true}},releaseLock:()=>{}})}};
    }
    throw new Error(url);
  });
  render(<App/>);const input=screen.getByPlaceholderText('描述你的研究问题或下一步分析…');
  fireEvent.change(input,{target:{value:'请分析'}});fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByText('正在分析');expect(screen.getByRole('timer').textContent).toContain('运行中');
  release();await screen.findByText('分析完成');expect(screen.getByText(/耗时 00:/)).toBeTruthy();
});

it('opens the mounted dataset when the agent finishes automatic merge',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const dataset={filename:'整合结果.dta',format:'dta',size:100,observations:1,variables:[{name:'id',type:'long',label:''}],preview:[[1]]};
  const result={answer:'合并完成',events:[{tool:'preview_merge',plan:{file_ids:['a','b']},preview:{ok:true},output:'check'},{tool:'etl',error:false,output:'ok'}],artifacts:[],dataset,loaded:true};
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,text:async()=>JSON.stringify({provider:'deepseek'})};
    if(url==='/api/workspace')return {ok:true,text:async()=>JSON.stringify({dataset:null,loaded:false,raw_files:[],messages:[],events:[],artifacts:[]})};
    if(url==='/api/chat/stream'){let sent=false;const bytes=new TextEncoder().encode(JSON.stringify({type:'done',result})+'\n');return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{value:bytes,done:false}),releaseLock:()=>{}})}}}
    throw new Error(url);
  });
  render(<App/>);const input=screen.getByPlaceholderText('描述你的研究问题或下一步分析…');
  fireEvent.change(input,{target:{value:'合并数据'}});fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByText('合并完成');
  expect(screen.getByText('1 OBS')).toBeTruthy();
});

it('opens the shared results area after a chat statistics request',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const dataset={filename:'base.dta',format:'dta',size:100,observations:5,variables:[{name:'roe',type:'float',label:''}],preview:[[1]]};
  const report={dataset:'base.dta',variables:['roe'],descriptive:[{variable:'roe',n:5,mean:3,sd:1,median:3,min:1,max:5}]};
  const result={answer:'统计完成。结果可在右侧统计分析中复制到 Word。',events:[{tool:'descriptive_correlation',error:false,output:'ok',statistics_report:report}],artifacts:[],dataset,loaded:true};
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,text:async()=>JSON.stringify({provider:'deepseek'})};
    if(url==='/api/workspace')return {ok:true,text:async()=>JSON.stringify({dataset,loaded:true,raw_files:[],messages:[],events:[],artifacts:[]})};
    if(url==='/api/chat/stream'){let sent=false;const bytes=new TextEncoder().encode(JSON.stringify({type:'done',result})+'\n');return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{value:bytes,done:false}),releaseLock:()=>{}})}}}
    throw new Error(url);
  });
  render(<App/>);const input=screen.getByPlaceholderText('描述你的研究问题或下一步分析…');
  fireEvent.change(input,{target:{value:'对 roe 做描述性统计'}});fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByText('描述性统计');
  expect(screen.getByRole('button',{name:'复制到 Word'})).toBeTruthy();
  expect(screen.getByRole('button',{name:'分析结果'}).className).toContain('selected');
  expect(screen.queryByRole('button',{name:'数据调整'})).toBeNull();
  expect(screen.queryByRole('button',{name:'统计分析'})).toBeNull();
  expect(screen.getByText(/右侧分析结果中复制/)).toBeTruthy();
});
