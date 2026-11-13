import React,{useState} from 'react';
import {Copy} from 'lucide-react';
import {clipboardContent} from './StatisticsWorkbench';
import {parseStataRegressions} from '../regression_parser';

const fmt=n=>typeof n==='number'&&Number.isFinite(n)?n.toFixed(3):'—';
const stars=p=>p==null||[.01,.05,.1].some(x=>Math.abs(p-x)<1e-10)?'':p<.01?'***':p<.05?'**':p<.1?'*':'';
export function regressionTable(models){
  const variables=[...new Set(models.flatMap(m=>m.coefficients.map(c=>c.variable)))];
  const rows=variables.flatMap(v=>{
    const cells=models.map(m=>m.coefficients.find(c=>c.variable===v));
    return [[v,...cells.map(c=>!c?'—':c.omitted?'已省略':fmt(c.coefficient)+stars(c.p))],['',...cells.map(c=>!c||c.omitted?'':`(${fmt(c.se)})`)]];
  });
  rows.push(['样本量',...models.map(m=>String(m.n))],['R²',...models.map(m=>fmt(m.r2))],['组内 R²',...models.map(m=>fmt(m.within))],['固定效应',...models.map(m=>m.fixed.join(' + ')||'见日志')],['标准误',...models.map(m=>m.cluster?`按 ${m.cluster} 聚类`:'见日志')],['聚类数',...models.map(m=>m.clusters==null?'—':String(m.clusters))]);
  return {title:'Stata 回归结果',headers:['变量',...models.map(m=>`${m.name} · ${m.outcome}`)],rows,
    note:'括号内为标准误；*** p<0.01，** p<0.05，* p<0.10。p 值来自 Stata 日志显示精度；显示为 0.010、0.050 或 0.100 的临界值不标星，请核对原日志。不同模型的样本量可能不同。'};
}
function RegressionCard({models}){
  const [status,setStatus]=useState('');const table=regressionTable(models);
  async function copy(){try{const {html,plain}=clipboardContent(table);if(navigator.clipboard?.write&&typeof ClipboardItem!=='undefined'){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);setStatus('已复制，可粘贴到 Word。')}else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(plain);setStatus('已复制文本，请在 Word 中转换为表格。')}else throw Error()}catch{setStatus('复制失败，请检查浏览器剪贴板权限。')}}
  return <section className="statistics-result"><div className="statistics-result-head"><strong>Stata 回归结果</strong><button type="button" className="outline-action" title="复制回归表到 Word" aria-label="复制回归表到 Word" onClick={copy}><Copy size={14}/></button></div><div className="table-wrap"><table><thead><tr>{table.headers.map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{table.rows.map((row,i)=><tr key={i}>{row.map((value,j)=><td key={j}>{value}</td>)}</tr>)}</tbody></table></div><p className="footnote">{table.note}</p><p className="statistics-copy-status" role="status">{status}</p></section>;
}
export default function RegressionResults({events}){return <>{events.filter(e=>!e.error&&e.tool==='run_stata').slice().reverse().map((event,i)=>{const models=parseStataRegressions(event);return models.length?<RegressionCard key={i} models={models}/>:null})}</>}
