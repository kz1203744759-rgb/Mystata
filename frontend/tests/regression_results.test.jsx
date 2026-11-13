// @vitest-environment jsdom
import React from 'react';
import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import RegressionResults,{regressionTable} from '../components/RegressionResults';
import {parseStataRegressions} from '../regression_parser';
import {App} from '../main';
import {TextEncoder,TextDecoder} from 'node:util';
globalThis.TextDecoder=TextDecoder;

afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear()});
const log=`. reghdfe y did, absorb(firm year) vce(cluster city)
HDFE Linear regression                            Number of obs   =        100
                                                  R-squared       =     0.8300
                                                  Within R-sq.    =     0.3100
Number of clusters (city)    =        20
         y | Coefficient  std. err.      t    P>|t|     [95% conf. interval]
-------------+----------------------------------------------------------------
       did |    .123456    .020000     6.17   0.000     .081     .165
     _cons |    1.00000    .300000     3.33   0.010     .370    1.630
-------------+----------------------------------------------------------------
Absorbed degrees of freedom:
  Absorbed FE | Categories  - Redundant  = Num. Coefs |
        firm |      20       20       0    *|
        year |       5        1       4     |
. estimates store A
`;
const event={tool:'run_stata',error:false,output:log,code:'reghdfe y did, absorb(firm year) vce(cluster city)'};

it('formats only complete Stata regression output, without inventing data',()=>{
  const models=parseStataRegressions(event);
  expect(models).toHaveLength(1);expect(models[0].n).toBe(100);
  expect(models[0].fixed).toEqual(['firm','year']);expect(models[0].clusters).toBe(20);
  const table=regressionTable(models);
  expect(table.rows[0]).toEqual(['did','0.123***']);
  expect(table.rows[1]).toEqual(['','(0.020)']);
  expect(table.rows[2]).toEqual(['_cons','1.000']); // rounded p=0.010 is ambiguous
  expect(parseStataRegressions({...event,output:log.slice(0,log.indexOf('     _cons'))})).toHaveLength(0);
  expect(parseStataRegressions({...event,error:true})).toHaveLength(0);
});

it('renders a copyable table and does not alter the event',async()=>{
  const write=vi.fn().mockResolvedValue();Object.defineProperty(navigator,'clipboard',{value:{write},configurable:true});
  vi.stubGlobal('ClipboardItem',class {constructor(items){this.items=items}});
  render(<RegressionResults events={[event]}/>);
  expect(screen.getByText('A · y')).toBeTruthy();expect(screen.getByText('0.123***')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'复制回归表到 Word'}));
  await waitFor(()=>expect(write).toHaveBeenCalledOnce());vi.unstubAllGlobals();
});

it('hides the old regression results in chat while preserving their table in analysis results',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    let value;if(url==='/api/status')value={provider:'deepseek'};
    else if(url==='/api/workspace')value={dataset:null,loaded:false,raw_files:[],events:[event],artifacts:[],messages:[{role:'assistant',content:'已执行回归，结果如下：\n\n| 模型 | 系数 |\n|---|---|\n| A | 0.123 |'}]};
    else throw Error(url);
    return {ok:true,status:200,text:async()=>JSON.stringify(value)};
  });
  render(<App/>);await screen.findByText(/回归结果请在右侧/);
  expect(screen.queryByText('0.123')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'分析结果'}));
  expect(screen.getByRole('button',{name:'复制回归表到 Word'})).toBeTruthy();
  expect(screen.getByText('0.123***')).toBeTruthy();
});

it('routes a new regression to results and does not leave the model summary in chat',async()=>{
  Element.prototype.scrollIntoView=vi.fn();
  vi.spyOn(globalThis,'fetch').mockImplementation(async url=>{
    if(url==='/api/status')return {ok:true,text:async()=>JSON.stringify({provider:'deepseek'})};
    if(url==='/api/workspace')return {ok:true,text:async()=>JSON.stringify({dataset:null,loaded:false,raw_files:[],events:[],artifacts:[],messages:[]})};
    if(url==='/api/chat/stream'){
      const result={answer:'回归结果：did 系数 0.123456',events:[event],artifacts:[],dataset:null,loaded:false};
      const chunk=[{type:'status',text:'正在执行 Stata'},{type:'delta',text:'did 系数 0.123456'},{type:'done',result}].map(x=>JSON.stringify(x)).join('\n')+'\n';
      let sent=false;return {ok:true,body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{value:new TextEncoder().encode(chunk),done:false}),releaseLock:()=>{}})}};
    }
    throw Error(url);
  });
  render(<App/>);fireEvent.change(screen.getByPlaceholderText('描述你的研究问题或下一步分析…'),{target:{value:'请运行回归'}});
  fireEvent.click(screen.getByRole('button',{name:'发送'}));
  await screen.findByText('0.123***');
  expect(screen.queryByText('did 系数 0.123456')).toBeNull();
  expect(screen.getByRole('button',{name:'分析结果'}).className).toContain('selected');
});
