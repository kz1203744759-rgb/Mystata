// @vitest-environment jsdom
import React from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {App} from '../main';

beforeEach(()=>localStorage.clear());
afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear()});

it('folds dataset and dictionary together, independently of research variables, and remembers both choices',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  const dataset={filename:'panel.dta',format:'dta',size:100,observations:3,variables:[{name:'roe',type:'float',label:'收益率'}],preview:[[1]]};
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    let value;
    if(url==='/api/status')value={provider:'deepseek',model:'fake',stata_found:true};
    else if(url==='/api/workspace')value={dataset,loaded:true,raw_files:[],messages:[],events:[],artifacts:[],research_variables:{x:['roe'],y:[],mediators:[],moderators:[],instruments:[]},dataset_revision:'r1'};
    else throw new Error('unexpected request '+url);
    return {ok:true,status:200,text:async()=>JSON.stringify(value)};
  });
  const {unmount}=render(<App/>);
  await screen.findByRole('button',{name:'移除X变量 roe'});
  const dataButton=screen.getByRole('button',{name:'主分析集与变量字典'});
  const researchButton=screen.getByRole('button',{name:'研究变量'});
  const dataBody=document.getElementById(dataButton.getAttribute('aria-controls'));
  const researchBody=document.getElementById(researchButton.getAttribute('aria-controls'));
  expect(dataBody.contains(screen.getByPlaceholderText('搜索变量名或标签'))).toBe(true);
  expect(dataBody.textContent).toContain('panel.dta');
  expect(dataButton.getAttribute('aria-expanded')).toBe('true');
  fireEvent.click(dataButton);
  expect(dataBody.hidden).toBe(true);
  expect(researchBody.hidden).toBe(false);
  fireEvent.click(researchButton);
  expect(researchBody.hidden).toBe(true);
  expect(dataBody.hidden).toBe(true);
  fireEvent.click(researchButton);
  expect(researchBody.hidden).toBe(false);
  expect(screen.getByRole('button',{name:'移除X变量 roe'})).toBeTruthy();
  fireEvent.click(researchButton);
  unmount();
  render(<App/>);
  await waitFor(()=>expect(screen.getByRole('button',{name:'主分析集与变量字典'}).getAttribute('aria-expanded')).toBe('false'));
  expect(screen.getByRole('button',{name:'研究变量'}).getAttribute('aria-expanded')).toBe('false');
  fireEvent.click(screen.getByRole('button',{name:'研究变量'}));
  await screen.findByRole('button',{name:'移除X变量 roe'});
});
