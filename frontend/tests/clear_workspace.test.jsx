// @vitest-environment jsdom
import React from 'react';
import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {App} from '../main';

afterEach(()=>{cleanup();vi.restoreAllMocks()});

function mockBackend(){
  let cleared=false;
  const file={id:'a',filename:'input.csv',size:100,observations:2,variables:[]};
  return vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    let data;
    if(url==='/api/status')data={api_key_set:true,model:'test',provider:'deepseek',stata_found:true};
    else if(url==='/api/workspace')data={dataset:null,loaded:false,raw_files:cleared?[]:[file],messages:[],events:[],artifacts:[]};
    else if(url==='/api/workspace/clear'){cleared=true;data={cleared:true,removed_files:1}}
    else throw new Error(`unexpected request ${url}`);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
}

it('does not clear when the user cancels',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const fetcher=mockBackend();vi.spyOn(window,'confirm').mockReturnValue(false);
  render(<App/>);await screen.findByText('input.csv');
  fireEvent.click(screen.getByRole('button',{name:'清空数据'}));
  expect(fetcher.mock.calls.some(([url])=>url==='/api/workspace/clear')).toBe(false);
  expect(screen.getByText('input.csv')).toBeTruthy();
});

it('clears and refreshes files after confirmation',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const fetcher=mockBackend();vi.spyOn(window,'confirm').mockReturnValue(true);
  render(<App/>);await screen.findByText('input.csv');
  fireEvent.click(screen.getByRole('button',{name:'清空数据'}));
  await waitFor(()=>expect(screen.queryByText('input.csv')).toBeNull());
  expect(fetcher.mock.calls.some(([url])=>url==='/api/workspace/clear')).toBe(true);
  expect(screen.getByText('后台重新启动会清空上传数据和历史产物，请先下载保存。')).toBeTruthy();
});
