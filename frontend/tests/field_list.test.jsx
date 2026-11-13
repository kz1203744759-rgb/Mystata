// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {App} from '../main';

afterEach(()=>{cleanup();vi.restoreAllMocks()});
it('checks selected field formats directly without a model key',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const file={id:'a',filename:'ROE.dta',size:100,observations:2,variables:[]};
  const report={files:[{file_id:'a',file:'ROE.dta',observations:2,column_count:1,offset:0,next_offset:null,
    columns:[{name:'id',storage_type:'long',display_format:'%10.0g',label:''}]}],note:'只读检查'};
  const event={tool:'profile_columns',label:'字段与格式检查',output:JSON.stringify(report),error:false};
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    let data;
    if(url==='/api/status')data={api_key_set:false,model:'',provider:'deepseek',stata_found:true};
    else if(url==='/api/workspace')data={dataset:null,loaded:false,raw_files:[file],messages:[],events:[],artifacts:[]};
    else if(url==='/api/profile-columns')data={answer:'字段检查结果',events:[event],artifacts:[],loaded:false,dataset:null};
    else throw new Error(`unexpected request ${url}`);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
  render(<App/>);await screen.findByText('ROE.dta');
  fireEvent.click(screen.getByRole('button',{name:/检查字段格式/}));
  await screen.findByText('字段检查结果');
  expect(screen.getByText('%10.0g')).toBeTruthy();
  const request=fetcher.mock.calls.find(([url])=>url==='/api/profile-columns');
  expect(JSON.parse(request[1].body).file_ids).toEqual(['a']);
  expect(fetcher.mock.calls.some(([url])=>url==='/api/chat')).toBe(false);
});
