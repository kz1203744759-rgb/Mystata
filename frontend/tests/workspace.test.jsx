// @vitest-environment jsdom
import React from 'react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MarkdownMessage from '../components/MarkdownMessage';
import OutputCard, {errorSummary,splitSystemLogs} from '../components/OutputCard';
import ResizableWorkspace from '../components/ResizableWorkspace';
import RawFilesPool from '../components/RawFilesPool';
import ETLWorkbench, {createMappings} from '../components/ETLWorkbench';

afterEach(()=>{cleanup();localStorage.clear()});
const files=[{id:'a',filename:'a.csv',size:200,observations:2,variables:[{name:'stkcd',type:'object'},{name:'year',type:'object'},{name:'sales',type:'object'}]},
             {id:'b',filename:'b.csv',size:300,observations:2,variables:[{name:'证券代码',type:'object'},{name:'年份',type:'object'},{name:'cost',type:'float64'}]}];

describe('workspace components',()=>{
  it('renders markdown safely and formats lists and code',()=>{
    const {container}=render(<MarkdownMessage content={'**环境**\n\n- 数据\n\n`price`\n\n<script>unsafe</script>'}/>);
    expect(container.querySelector('strong').textContent).toBe('环境');
    expect(container.querySelector('li').textContent).toBe('数据');
    expect(container.querySelector('code').textContent).toBe('price');
    expect(container.querySelector('script')).toBeNull();
  });
  it('moves pane boundaries with keyboard and keeps minimums',()=>{
    const {container}=render(<ResizableWorkspace left={<div>left</div>} center={<div>center</div>} right={<div>right</div>}/>);
    const separator=screen.getByRole('separator',{name:'调整数据工作区和研究对话宽度'});
    fireEvent.keyDown(separator,{key:'ArrowRight'});
    expect(container.firstChild.style.gridTemplateColumns).toContain('24fr');
    for(let i=0;i<30;i++)fireEvent.keyDown(separator,{key:'ArrowLeft'});
    expect(container.firstChild.style.gridTemplateColumns).toContain('18fr');
  });
  it('adjusts adjacent panes when the divider is dragged',()=>{
    const previous=window.PointerEvent;
    window.PointerEvent=window.MouseEvent;
    try {
      const {container}=render(<ResizableWorkspace left={<div>left</div>} center={<div>center</div>} right={<div>right</div>}/>);
      container.firstChild.getBoundingClientRect=()=>({width:1000});
      const separator=screen.getByRole('separator',{name:'调整数据工作区和研究对话宽度'});
      fireEvent.pointerDown(separator,{button:0,clientX:220});
      fireEvent.pointerMove(window,{clientX:270});
      fireEvent.pointerUp(window);
      expect(container.firstChild.style.gridTemplateColumns).toContain('27fr');
      expect(container.firstChild.style.gridTemplateColumns).toContain('29fr');
    } finally {window.PointerEvent=previous}
  });
  it('uploads multiple raw files without replacing the selected pool',()=>{
    const upload=vi.fn(), select=vi.fn();
    const {container}=render(<RawFilesPool files={files} selected={['a']} onSelect={select} onUpload={upload} onActivate={()=>{}} onOpen={()=>{}} busy={false}/>);
    const input=container.querySelector('input[type=file]');
    expect(input.multiple).toBe(true);
    fireEvent.change(input,{target:{files:[new File(['x'],'x.csv'),new File(['y'],'y.csv')]}});
    expect(upload.mock.calls[0][0]).toHaveLength(2);
    fireEvent.click(screen.getByLabelText('选择 b.csv'));
    expect(select).toHaveBeenCalledWith('b');
  });
  it('maps synonymous keys and submits a confirmed ETL plan',async()=>{
    const rows=createMappings(files), stock=rows.find(x=>x.target==='id');
    expect(stock.sources).toEqual({a:0,b:0});
    const run=vi.fn().mockResolvedValue({});
    const preview=vi.fn().mockResolvedValue({ok:true,metrics:{MERGE_1_MATCHED:2},output:'checked'});
    render(<ETLWorkbench files={files} selected={['a','b']} onSuggest={()=>{}} onPreview={preview} onRun={run} busy={false}/>);
    expect(screen.getByLabelText('主键目标字段（逗号分隔）').value).toBe('id, year');
    fireEvent.click(screen.getByRole('button',{name:'合并前检查'}));
    await screen.findByText('检查通过');
    fireEvent.click(screen.getByRole('button',{name:'确认方案并生成 Stata 清洗脚本'}));
    await waitFor(()=>expect(run).toHaveBeenCalledOnce());
    expect(run.mock.calls[0][0].keys).toEqual(['id','year']);
    expect(run.mock.calls[0][0].sample_retention).toBe('matched');
    expect(run.mock.calls[0][0].drop_all_missing).toBe(true);
    expect(run.mock.calls[0][0].mappings[0].normalize).toBe('stock');
  });
  it('keeps company names separate and never guesses year alone as the key',()=>{
    const inputs=[{id:'a',filename:'a',variables:[{name:'name',type:'str10'},{name:'year',type:'float'}]},
                  {id:'b',filename:'b',variables:[{name:'name',type:'str10'},{name:'year',type:'float'}]}];
    const names=createMappings(inputs).filter(row=>row.target.startsWith('name'));
    expect(names).toHaveLength(2);
    expect(Object.values(names[0].sources)).toHaveLength(1);
    expect(names.every(row=>row.keep===false)).toBe(true);
    render(<ETLWorkbench files={inputs} selected={['a','b']} onSuggest={()=>{}} onPreview={()=>{}} onRun={()=>{}} busy={false}/>);
    expect(screen.getByLabelText('主键目标字段（逗号分隔）').value).toBe('');
  });
  it('loads an id-only agent preview, and requires a new check if edited',async()=>{
    const mappings=createMappings(files).map(({target,sources,convert,normalize,keep})=>({target,sources,convert,normalize,keep}));
    const plan={file_ids:['a','b'],mode:'merge',cardinality:'1:1',keys:['id'],drop_missing_keys:true,drop_missing:[],drop_all_missing:true,sample_retention:'matched',conflict_policy:'stop',mappings};
    const run=vi.fn().mockResolvedValue({});
    render(<ETLWorkbench files={files} selected={['a','b']} proposal={{id:1,plan,preview:{ok:true,metrics:{FINAL_ROWS:1},log:'checked',error:''}}} onSuggest={()=>{}} onPreview={()=>{}} onRun={run} busy={false}/>);
    expect(screen.getByLabelText('主键目标字段（逗号分隔）').value).toBe('id');
    const button=screen.getByRole('button',{name:'确认方案并生成 Stata 清洗脚本'});
    expect(button.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText('主键目标字段（逗号分隔）'),{target:{value:'id, year'}});
    expect(button.disabled).toBe(true);
    expect(screen.getByText('方案已更改，请重新检查')).toBeTruthy();
  });
  it('folds probe logs and exposes errors to the repair action',()=>{
    const output='. macro define mcp_graph_list ""\n. quietly graph dir, memory\n. regress y x\nvariable x not found\nr(111);';
    const split=splitSystemLogs(output);
    expect(split.system).toContain('mcp_graph_list');
    expect(split.core).toContain('regress y x');
    expect(split.core).toContain('r(111)');
    const item={label:'step.do',code:'regress y x',output,error:true},fix=vi.fn();
    expect(errorSummary(item)).toContain('r(111)');
    render(<OutputCard item={item} onFix={fix}/>);
    fireEvent.click(screen.getByRole('button',{name:'让 AI 诊断并修复'}));
    expect(fix).toHaveBeenCalledWith(item);
    expect(screen.getByText('系统环境日志')).toBeTruthy();
  });
  it('defaults to readable code and allows switching to the executed version',()=>{
    const item={label:'清洗',code:'rename tmp1 id',readable_code:'rename code id',readable_url:'/api/artifacts/run/etl-readable.do',output:'',error:false};
    render(<OutputCard item={item} onFix={()=>{}} showCode/>);
    expect(screen.getByText('rename code id')).toBeTruthy();
    expect(screen.getByRole('link',{name:'下载可读版'}).getAttribute('href')).toBe(item.readable_url);
    fireEvent.click(screen.getByRole('button',{name:'查看实际执行'}));
    expect(screen.getByText('rename tmp1 id')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'查看可读版'}));
    expect(screen.getByText('rename code id')).toBeTruthy();
  });
  it('renders field profiles and only shows duplicates when a check was requested',()=>{
    const file={file_id:'a',file:'sample.csv',observations:3,column_count:2,offset:0,next_offset:null,
      columns:[{name:'id',type:'str6',label:'代码',candidate_role:null},{name:'year',type:'float',label:'年份',candidate_role:'year'}],
      format_profiles:[{column:'year',suggested_rule:'转 Stata float 年份',non_numeric:0,non_integer:0,out_of_range:0}]};
    const report={files:[file],note:'只读字段检查'};
    const {rerender}=render(<OutputCard item={{tool:'profile_columns',label:'字段与格式检查',output:JSON.stringify(report)}} onFix={()=>{}}/>);
    expect(screen.getByText('sample.csv')).toBeTruthy();
    expect(screen.getByText('显示格式')).toBeTruthy();
    expect(screen.queryByText(/重复检查：/)).toBeNull();
    file.duplicate_check={columns:['id','year'],duplicate_groups:1,rows_in_duplicate_groups:2,surplus_rows:1,equality_note:'原始值比较',examples:[{id:'000001',year:2020}]};
    rerender(<OutputCard item={{tool:'profile_columns',label:'字段与格式检查',output:JSON.stringify(report)}} onFix={()=>{}}/>);
    expect(screen.getByText('重复检查：id + year')).toBeTruthy();
    expect(screen.getByText('1 组 · 涉及 2 行 · 多余 1 行')).toBeTruthy();
    expect(screen.getByText('000001')).toBeTruthy();
  });
  it('folds nested graph probes without hiding the following analysis',()=>{
    const output=['. macro define mcp_graph_list ""','. if "`r(list)\'" != "" {',".   foreach g in `r(list)' {",'  2.     global mcp_graph_details "x"','  3.   }','. }','. regress y x','coefficient = 3'].join('\n');
    const split=splitSystemLogs(output);
    expect(split.system).toContain('foreach g');
    expect(split.core).not.toContain('foreach g');
    expect(split.core).toContain('coefficient = 3');
  });
});
