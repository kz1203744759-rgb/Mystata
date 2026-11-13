// @vitest-environment jsdom
import React from 'react';
import {afterEach,it,expect,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {App} from '../main';

afterEach(()=>{cleanup();vi.restoreAllMocks()});
it('offers Windows user environment persistence for the DeepSeek official endpoint',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const fetcher=vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    const data=url==='/api/status'?{api_key_set:false,provider:'deepseek',model:'deepseek-flash',base_url:'https://api.deepseek.com'}:
      url==='/api/workspace'?{dataset:null,loaded:false,raw_files:[],messages:[],events:[],artifacts:[]}:
      url==='/api/settings'?{saved:true,remembered:true}:null;
    if(!data)throw new Error(url);
    return {ok:true,status:200,text:async()=>JSON.stringify(data)};
  });
  render(<App/>);await waitFor(()=>expect(fetcher).toHaveBeenCalledWith('/api/status',{}));
  fireEvent.click(screen.getByRole('button',{name:'模型设置'}));
  const checkbox=screen.getByLabelText('保存 DeepSeek 密钥和模型到当前 Windows 用户环境变量');
  expect(checkbox.checked).toBe(true);
  fireEvent.change(screen.getByLabelText('API 密钥'),{target:{value:'fake-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'保存设置'}));
  await screen.findByText('已保存到当前 Windows 用户的环境变量。连接将在发送消息时验证。');
  const call=fetcher.mock.calls.find(([url])=>url==='/api/settings');
  expect(JSON.parse(call[1].body).remember_api_key).toBe(true);
  expect(screen.getByLabelText('API 密钥').value).toBe('');
});
