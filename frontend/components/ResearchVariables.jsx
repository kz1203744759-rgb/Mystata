import React, {useEffect,useRef,useState} from 'react';
import {X} from 'lucide-react';

const groups=[
  {key:'x',label:'解释变量 X',short:'X',hint:'自变量'},
  {key:'y',label:'被解释变量 Y',short:'Y',hint:'因变量'},
  {key:'controls',label:'控制变量集',short:'控制',hint:'控制变量'},
  {key:'mediators',label:'中介变量',short:'中介',hint:'中介效应'},
  {key:'moderators',label:'调节变量',short:'调节',hint:'调节效应'},
  {key:'instruments',label:'工具变量',short:'工具',hint:'工具变量'},
];

export default function ResearchVariables({dataset,roles={},onChange,onSuggest,datasetRevision,confirmedModel,busy,showHeading=true}) {
  const [saving,setSaving]=useState(false),[message,setMessage]=useState('');
  const [suggestions,setSuggestions]=useState({}),[suggesting,setSuggesting]=useState(false);
  const attempted=useRef(null),latest=useRef(datasetRevision);
  latest.current=datasetRevision;
  const variables=dataset?.variables||[];
  async function suggest(){
    if(!onSuggest||!datasetRevision||suggesting)return;
    const revision=datasetRevision;attempted.current=revision;setSuggesting(true);setMessage('');
    try{const result=await onSuggest(revision);if(latest.current===revision)setSuggestions(result.suggestions||{})}
    catch(e){if(latest.current===revision)setMessage(e.message||'预识别未完成，可手动选择。')}
    finally{if(latest.current===revision)setSuggesting(false)}
  }
  useEffect(()=>{setSuggestions({});setSuggesting(false);setMessage('')},[datasetRevision]);
  useEffect(()=>{if(dataset&&datasetRevision&&!busy&&onSuggest&&attempted.current!==datasetRevision)suggest()},[datasetRevision,dataset,busy]);
  async function update(key,values){
    if(saving||busy||!dataset)return;
    setSaving(true);setMessage('');
    try{await onChange(key,values)}catch(e){setMessage(e.message||'保存失败，请重试。')}
    finally{setSaving(false)}
  }
  return <section className="research-variables" aria-label="研究变量配置">
    {showHeading&&<div className="section-label">研究变量 <span>RESEARCH VARIABLES</span></div>}
    <p className="research-intro">从主分析集选择字段，每类可添加多个；助手会在对话中参考。</p>
    {dataset?.memory_only&&<p className="research-error" role="status">当前数据可能含未保存的 Stata 内存修改，重启后无法自动恢复；请先保存数据。</p>}
    {onSuggest&&<><button type="button" className="outline-action" onClick={suggest} disabled={!dataset||busy||suggesting}>{suggesting?'正在预识别…':'重新预识别'}</button><p className="research-intro">仅发送字段名、标签和类型。识别结果是候选，点击添加后才会使用。</p></>}
    {groups.map(group=>{
      const chosen=roles[group.key]||[];
      return <div className="research-role" key={group.key}>
        <div className="research-role-head"><strong>{group.label}</strong><span>{chosen.length} 个</span></div>
        <div className="research-chips">{chosen.map(name=><span className="research-chip" key={name} title={variables.find(v=>v.name===name)?.label||name}>{name}<button type="button" onClick={()=>update(group.key,chosen.filter(v=>v!==name))} disabled={busy||saving} aria-label={`移除${group.short}变量 ${name}`}><X size={12}/></button></span>)}</div>
        <select aria-label={`添加${group.short}变量`} value="" disabled={!dataset||busy||saving||chosen.length>=100} onChange={e=>{if(e.target.value)update(group.key,[...chosen,e.target.value])}}>
          <option value="">{dataset?'＋ 添加'+group.hint:'先挂载主分析集'}</option>
          {variables.filter(v=>!chosen.includes(v.name)).map(v=><option key={v.name} value={v.name}>{v.name}{v.label?` · ${v.label}`:''}</option>)}
        </select>
        {(suggestions[group.key]||[]).filter(v=>!chosen.includes(v.name)).map(v=><button className="research-suggestion" type="button" key={v.name} title={v.reason} disabled={busy||saving} onClick={()=>update(group.key,[...chosen,v.name])}>＋ {v.name} <small>{v.reason}</small></button>)}
      </div>;
    })}
    {message&&<p className="research-error" role="alert">{message}</p>}
    {saving&&<p className="research-intro" role="status">正在保存…</p>}
    <p className="research-intro">变量选择会保存在本机，并与数据集绑定；更换主分析集后需重新设置。</p>
    {dataset&&confirmedModel?.dataset_revision===datasetRevision&&confirmedModel?.spec&&<p className="research-intro">最近固定效应设定：Y = {confirmedModel.spec.outcome}，X = {(confirmedModel.spec.explanatory_variables||[]).join('、')}；{({completed:'已完成',failed:'执行失败',running:'执行中',interrupted:'执行中断'})[confirmedModel.status]||'状态未知'}。</p>}
  </section>;
}
