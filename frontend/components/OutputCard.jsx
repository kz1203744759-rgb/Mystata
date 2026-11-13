import React, {useState} from 'react';
import {AlertCircle, FileCode2, Sparkles, Terminal} from 'lucide-react';
import ProfileReport from './ProfileReport';
import MergePreviewCard from './MergePreviewCard';

export function splitSystemLogs(text='') {
  const lines=String(text).split('\n'), core=[], system=[];
  let probeBlock=0;
  for(let i=0;i<lines.length;i++) {
    const line=lines[i];
    const graphBlock=/^\s*\.\s*if\s+.*r\(list\)/.test(line) && lines.slice(i,i+9).some(x=>x.includes('mcp_graph_details'));
    if(graphBlock) probeBlock=1;
    const probe=probeBlock || /mcp_graph_list|mcp_graph_details|_mcp_saved_rc|_mcp_sentinel_rc|_mcp_startup_sentinel|_mcp_session|mcp_hold_[0-9a-f]+|^\s*\.\s*quietly graph dir, memory\s*$/.test(line);
    if(probe) system.push(line); else core.push(line);
    if(probeBlock && /\}/.test(line)) {const tail=lines.slice(i+1,i+3).join('\n');if(!/^\s*(?:\d+\s*)?\.?(?:\s*)\}/m.test(tail)) probeBlock=0;}
  }
  return {core:core.join('\n').trim(),system:system.join('\n').trim()};
}

export function errorSummary(item) {
  const text=String(item.output||'');
  const code=text.match(/\br\((\d+)\)/i)?.[1] || text.match(/"rc"\s*:\s*(\d+)/)?.[1];
  const message=text.match(/"message"\s*:\s*"([^"\n]+)"/)?.[1] || text.split('\n').map(s=>s.trim()).filter(s=>s && !s.startsWith('.') && !/^r\(\d+\);?$/.test(s)).slice(-1)[0];
  return [code?`Stata r(${code})`:null,message||'执行失败，请查看完整输出。'].filter(Boolean).join(' · ');
}

export default function OutputCard({item,onFix,showCode=false}) {
  const [showActual,setShowActual]=useState(false);
  if(!showCode&&item.tool==='preview_merge'&&item.preview)return <MergePreviewCard item={item}/>;
  const hasReadable=showCode&&typeof item.readable_code==='string'&&!!item.readable_code;
  const {core,system}=splitSystemLogs(showCode?(hasReadable&&!showActual?item.readable_code:item.code):item.output);
  let report=null;
  if(!showCode&&!item.error&&item.tool==='profile_columns'){
    try{const parsed=JSON.parse(item.output);if(Array.isArray(parsed.files))report=parsed}catch{}
  }
  return <div className={showCode?'code-card':'output-card'}>
    <div className="code-head">{showCode?<FileCode2 size={15}/>:<Terminal size={14}/>}<b>{item.label}</b>{hasReadable&&<><button className="code-view-toggle" type="button" onClick={()=>setShowActual(old=>!old)}>{showActual?'查看可读版':'查看实际执行'}</button>{item.readable_url&&<a className="code-download" href={item.readable_url} download>下载可读版</a>}</>}<span className={item.error?'fail':'success'}>{item.error?'出错':hasReadable&&!showActual?'可读版':'已返回'}</span></div>
    {showCode&&item.readable_error&&<div className="code-note">{item.readable_error}</div>}
    {item.error&&<div className="error-summary"><AlertCircle size={16}/><div><strong>执行出错</strong><span>{errorSummary(item)}</span></div><button type="button" onClick={()=>onFix(item)}><Sparkles size={14}/>让 AI 诊断并修复</button></div>}
    {report?<ProfileReport report={report}/>:<pre>{core || (system?'核心输出为空。':'没有返回文本。')}</pre>}
    {!report&&system&&<details className="system-log"><summary>系统环境日志</summary><pre>{system}</pre></details>}
  </div>;
}
