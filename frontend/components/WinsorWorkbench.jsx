import React, {useEffect,useState} from 'react';
import {Scissors} from 'lucide-react';

export default function WinsorWorkbench({dataset,onRun,busy}){
  const [selected,setSelected]=useState([]),[lower,setLower]=useState(''),[upper,setUpper]=useState(''),[mode,setMode]=useState(''),[suffix,setSuffix]=useState('_w'),[result,setResult]=useState(null),[message,setMessage]=useState('');
  const variables=(dataset?.variables||[]).filter(v=>/^(?:byte|int|long|float|double|u?int\d+|float\d+|double\d*)/i.test(v.type));
  const signature=variables.map(v=>v.name).join('|');
  useEffect(()=>{setSelected(old=>old.filter(name=>variables.some(v=>v.name===name)))},[signature]);
  async function submit(event){
    event.preventDefault();setMessage('');setResult(null);
    if(!selected.length){setMessage('请先选择需要缩尾的连续变量。');return}
    if(lower===''||upper===''){setMessage('请填写本次上下分位点。');return}
    if(!mode){setMessage('请指定生成新变量还是覆盖原变量。');return}
    try{const response=await onRun({variables:selected,lower:Number(lower),upper:Number(upper),mode,suffix:mode==='new'?suffix:''});setResult(response.report);setSelected([]);setLower('');setUpper('');setMode('')}catch(error){setMessage(error.message)}
  }
  return <div className="winsor-workbench"><div className="content-head"><div><div className="eyebrow">DATA TRANSFORMATION</div><h2>连续变量缩尾</h2><p>使用 Stata winsor2，按全样本计算分位点；每次选择变量和保存方式。</p></div><Scissors size={19}/></div>
    {!dataset?<div className="etl-empty"><strong>请先挂载主分析集</strong><p>数据加载完成后，可以选择需要缩尾的连续变量。</p></div>:<form onSubmit={submit}>
      <div className="winsor-group"><strong>选择连续变量</strong><small>只列出数值字段；代码、年份和仅含 0/1 的变量不参与缩尾。</small><div className="winsor-variables">{variables.map(v=>{const key=['id','year','stock_code','stkcd','证券代码','年份'].includes(v.name.toLowerCase());return <label key={v.name}><input type="checkbox" disabled={busy||key} checked={selected.includes(v.name)} onChange={e=>setSelected(old=>e.target.checked?[...old,v.name]:old.filter(n=>n!==v.name))}/><span>{v.name}</span><small>{v.label||v.type}{key?' · 标识字段':''}</small></label>})}</div></div>
      <div className="winsor-group"><strong>缩尾分位点</strong><div className="winsor-points"><label>下分位点（%）<input aria-label="下分位点（%）" type="number" min="0" max="100" step="any" value={lower} onChange={e=>setLower(e.target.value)} placeholder="例如 1"/></label><label>上分位点（%）<input aria-label="上分位点（%）" type="number" min="0" max="100" step="any" value={upper} onChange={e=>setUpper(e.target.value)} placeholder="例如 99"/></label></div></div>
      <div className="winsor-group"><strong>结果保存方式</strong><label><input type="radio" name="winsor-mode" checked={mode==='new'} onChange={()=>setMode('new')}/> 生成新变量，保留原变量</label><label><input type="radio" name="winsor-mode" checked={mode==='replace'} onChange={()=>setMode('replace')}/> 在新主分析集中覆盖原变量</label>{mode==='new'&&<label>新变量后缀 <input aria-label="新变量后缀" value={suffix} onChange={e=>setSuffix(e.target.value)} maxLength={21}/></label>}<small>结果写入新的主分析集；上传的原始文件不变。</small></div>
      <button className="primary winsor-submit" disabled={busy} type="submit">运行缩尾并更新主分析集</button>
    </form>}
    {message&&<div className="etl-message" role="alert">{message}</div>}
    {result&&<div className="etl-report" role="status"><strong>缩尾完成</strong><p>分位点：{result.lower}% 和 {result.upper}% · 样本：{result.observations.toLocaleString()} 行</p><div className="etl-metrics">{result.changed.map(item=><span key={item.source}>{item.source} → {item.target}：<b>{item.rows.toLocaleString()}</b> 行变化</span>)}</div><small>可在 Do-file 查看并下载 Stata 代码。</small></div>}
  </div>;
}
