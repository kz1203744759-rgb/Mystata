// @vitest-environment jsdom
import React, {useState} from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import ResearchVariables from '../components/ResearchVariables';
import RawFilesPool from '../components/RawFilesPool';
import {App} from '../main';

afterEach(cleanup);
const dataset={variables:[{name:'roe',label:'收益率'},{name:'pay',label:'薪酬'},{name:'iv',label:'工具'}]};

it('supports adding and removing multiple variables for each research role',async()=>{
  const save=vi.fn();
  function Harness(){
    const [roles,setRoles]=useState({});
    async function change(role,variables){save(role,variables);setRoles(old=>({...old,[role]:variables}))}
    return <ResearchVariables dataset={dataset} roles={roles} onChange={change} busy={false}/>;
  }
  render(<Harness/>);
  for(const name of ['添加X变量','添加Y变量','添加中介变量','添加调节变量','添加工具变量'])expect(screen.getByLabelText(name)).toBeTruthy();
  fireEvent.change(screen.getByLabelText('添加X变量'),{target:{value:'roe'}});
  await screen.findByRole('button',{name:'移除X变量 roe'});
  fireEvent.change(screen.getByLabelText('添加X变量'),{target:{value:'pay'}});
  await screen.findByRole('button',{name:'移除X变量 pay'});
  expect(save).toHaveBeenLastCalledWith('x',['roe','pay']);
  fireEvent.click(screen.getByRole('button',{name:'移除X变量 roe'}));
  await waitFor(()=>expect(save).toHaveBeenLastCalledWith('x',['pay']));
});

it('disables research selection until a dataset is loaded',()=>{
  render(<ResearchVariables dataset={null} roles={{}} onChange={()=>{}} busy={false}/>);
  expect(screen.getByLabelText('添加X变量').disabled).toBe(true);
});

it('shows saved model only for the current dataset version',()=>{
  const model={dataset_revision:'rev-1',status:'completed',spec:{outcome:'pay',explanatory_variables:['roe']}};
  const {rerender}=render(<ResearchVariables dataset={dataset} roles={{}} onChange={()=>{}} datasetRevision="rev-1" confirmedModel={model} busy={false}/>);
  expect(screen.getByText(/最近固定效应设定：Y = pay/)).toBeTruthy();
  rerender(<ResearchVariables dataset={dataset} roles={{}} onChange={()=>{}} datasetRevision="rev-2" confirmedModel={model} busy={false}/>);
  expect(screen.queryByText(/最近固定效应设定/)).toBeNull();
});

it('shows automatic suggestions without assigning them until clicked',async()=>{
  const change=vi.fn().mockResolvedValue();
  const suggest=vi.fn().mockResolvedValue({suggestions:{controls:[{name:'pay',reason:'常见财务指标'}]}});
  render(<ResearchVariables dataset={dataset} roles={{}} onChange={change} onSuggest={suggest} datasetRevision="rev" busy={false}/>);
  await screen.findByRole('button',{name:/pay 常见财务指标/});
  expect(screen.getByLabelText('添加控制变量')).toBeTruthy();
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:/pay 常见财务指标/}));
  await waitFor(()=>expect(change).toHaveBeenCalledWith('controls',['pay']));
});

it('collapses the raw pool without removing files or preventing reopening',()=>{
  const file={id:'a',filename:'a.dta',size:100,observations:2,variables:[]};
  function Harness(){const [collapsed,setCollapsed]=useState(true);return <RawFilesPool files={[file]} selected={['a']} onSelect={()=>{}} onUpload={()=>{}} onActivate={()=>{}} onOpen={()=>{}} collapsed={collapsed} onToggle={()=>setCollapsed(v=>!v)} busy={false}/>}
  render(<Harness/>);
  expect(screen.getByRole('button',{name:/原始文件池/}).getAttribute('aria-expanded')).toBe('false');
  expect(screen.getByText('a.dta').closest('[hidden]')).not.toBeNull();
  fireEvent.click(screen.getByRole('button',{name:/原始文件池/}));
  expect(screen.getByText('a.dta')).toBeTruthy();
  expect(screen.getByText('a.dta').closest('[hidden]')).toBeNull();
  expect(screen.getByRole('button',{name:/原始文件池/}).getAttribute('aria-expanded')).toBe('true');
});

it('saves choices against the currently mounted dataset',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const mounted={filename:'data.dta',format:'dta',size:100,observations:2,variables:dataset.variables.map(v=>({...v,type:'float'})),preview:[]};
  const files=[{id:'a',filename:'data.dta',size:100,observations:2,variables:[]}];
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async (url,options)=>{
    let data;
    if(url==='/api/status')data={provider:'deepseek',model:'fake',stata_found:true};
    else if(url==='/api/workspace')data={dataset:mounted,loaded:true,raw_files:files,messages:[],events:[],artifacts:[],research_variables:{},dataset_revision:'rev-a'};
    else if(url==='/api/research-variables')data={dataset_revision:'rev-a',research_variables:{x:['roe']}};
    else throw new Error('unexpected request '+url);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
  try{
    render(<App/>);
    await screen.findByLabelText('添加X变量');
    await waitFor(()=>expect(screen.getByRole('button',{name:/原始文件池/}).getAttribute('aria-expanded')).toBe('false'));
    fireEvent.change(screen.getByLabelText('添加X变量'),{target:{value:'roe'}});
    await screen.findByRole('button',{name:'移除X变量 roe'});
    const call=fetcher.mock.calls.find(([url])=>url==='/api/research-variables');
    expect(JSON.parse(call[1].body)).toEqual({dataset_revision:'rev-a',role:'x',variables:['roe']});
  }finally{fetcher.mockRestore()}
});
