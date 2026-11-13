import React,{useState} from 'react';
import {Copy} from 'lucide-react';
import {clipboardContent} from './StatisticsWorkbench';

const fmt=n=>typeof n==='number'&&Number.isFinite(n)?n.toFixed(3):'—';
const stars=p=>p==null?'':p<.01?'***':p<.05?'**':p<.1?'*':'';

function DidCard({report}){
  const [status,setStatus]=useState('');
  const rows=report.coefficients.flatMap(v=>v.omitted?[[v.variable,'已省略'],['','']]:[[v.variable,fmt(v.coefficient)+stars(v.p)],['',`(${fmt(v.se)})`]]);
  const fixed=Array.isArray(report.fixed_effects)?report.fixed_effects.map(group=>group.join(' × ')).join(' + '):[report.entity_fe,report.time_fe].filter(Boolean).join(' + ');
  rows.push(['样本量',String(report.n??'—')],['R²',fmt(report.r2)],['固定效应',fixed||'—'],['标准误',report.se_type==='cluster'?`聚类：${report.cluster}`:report.se_type==='robust'?'稳健':'常规']);
  if(report.clusters!=null)rows.push(['聚类数',String(report.clusters)]);
  const table={title:'固定效应回归',headers:['变量',report.outcome],rows,note:'括号内为标准误；*** p<0.01，** p<0.05，* p<0.10。样本与估计值以本次 Stata 执行为准。'};
  async function copy(){try{const {html,plain}=clipboardContent(table);if(navigator.clipboard?.write&&typeof ClipboardItem!=='undefined'){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);setStatus('已复制，可粘贴到 Word。')}else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(plain);setStatus('已复制文本，请在 Word 中转换为表格。')}else throw Error()}catch{setStatus('复制失败，请检查浏览器剪贴板权限。')}}
  return <section className="statistics-result"><div className="statistics-result-head"><strong>固定效应回归 · {report.outcome}</strong><button className="outline-action" type="button" title="复制到 Word" aria-label="复制到 Word" onClick={copy}><Copy size={14}/></button></div><div className="table-wrap"><table><thead><tr>{table.headers.map(v=><th key={v}>{v}</th>)}</tr></thead><tbody>{rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div><p className="footnote">{table.note}</p><p className="statistics-copy-status" role="status">{status}</p></section>;
}
export default function DidResults({events}){return <>{events.filter(e=>!e.error&&(e.fixed_effects_report||e.did_report)).slice().reverse().map((event,i)=>{const report=event.fixed_effects_report||event.did_report;return <div key={i}><p className="footnote">基于执行时的主分析集：{report.dataset}</p><DidCard report={report}/></div>})}</>}
