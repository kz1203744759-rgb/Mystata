import React,{useEffect,useMemo,useState} from 'react';
import {Copy} from 'lucide-react';

const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>typeof n==='number'&&Number.isFinite(n)?(Object.is(n,-0)?0:n).toFixed(4):'—';
const stars=p=>p==null?'':p<.01?'***':p<.05?'**':p<.1?'*':'';
export const regressionReports=events=>events.filter(e=>!e.error&&(e.fixed_effects_report||e.did_report)).map(e=>e.fixed_effects_report||e.did_report);
const effects=r=>Array.isArray(r.fixed_effects)?r.fixed_effects.map(v=>Array.isArray(v)?v.join(' × '):String(v)):[r.entity_fe,r.time_fe].filter(Boolean);
const mainVars=r=>r.explanatory_variables?.length?r.explanatory_variables:r.treatment?[r.treatment]:r.coefficients?.length?[r.coefficients[0].variable]:[];

export function combinedTable(reports,selection,requestedVariables=[],groups=[]){
  const models=selection.map(i=>reports[i]).filter(Boolean);
  const variables=requestedVariables.length?requestedVariables:[...new Set(models.flatMap(mainVars))];
  const rows=variables.flatMap(v=>{
    const values=models.map(m=>m.coefficients.find(c=>c.variable===v));
    return [{type:'variable',cells:[v,...values.map(c=>!c?'—':c.omitted?'已省略':fmt(c.coefficient)+stars(c.p))]},
      {type:'se',cells:['',...values.map(c=>!c||c.omitted?'':`(${fmt(c.se)})`)]}];
  });
  const grouped=new Set(groups.flatMap(g=>g.variables));
  if(groups.length){
    for(const g of groups)rows.push({type:'setting',cells:[g.name,...models.map(m=>{
      const count=g.variables.filter(v=>(m.controls||[]).includes(v)).length;
      return !count?'否':count===g.variables.length?'是':'部分';
    })]});
    rows.push({type:'setting',cells:['其他控制变量',...models.map(m=>(m.controls||[]).some(v=>!grouped.has(v))?'是':'否')]});
  }else rows.push({type:'setting',cells:['控制变量',...models.map(m=>(m.controls||[]).length?'是':'否')]});
  for(const fe of [...new Set(models.flatMap(effects))])rows.push({type:'setting',cells:[`${fe} 固定效应`,...models.map(m=>effects(m).includes(fe)?'是':'否')]});
  rows.push({type:'summary',cells:['观测数',...models.map(m=>m.n==null?'—':String(m.n))]},
    {type:'summary',cells:['R²',...models.map(m=>fmt(m.r2))]});
  return {models,rows,note:'括号内为标准误；*** p<0.01，** p<0.05，* p<0.10。各列样本和标准误方式可能不同，具体以执行日志为准。',
    details:models.map((m,i)=>`(${i+1}) ${m.dataset||'数据集未记录'}；控制变量：${(m.controls||[]).join('、')||'无'}；标准误：${m.se_type==='cluster'?`按 ${m.cluster} 聚类`:m.se_type==='robust'?'稳健':m.se_type==='conventional'?'常规':'未记录'}`)};
}

export function combinedWordContent(table){
  const {models,rows,note,details}=table;
  const same=models.every(m=>m.outcome===models[0]?.outcome);
  const font="font-family:SimSun,'宋体',serif;mso-ascii-font-family:SimSun;mso-hansi-font-family:SimSun;mso-fareast-font-family:SimSun;font-size:9pt;color:#000;";
  const cell='padding:2pt 7pt;text-align:center;vertical-align:middle;border-right:0.5pt solid #000;';
  const first=`<th rowspan="2" style="${cell}border-bottom:0.5pt solid #000;">变量</th>`;
  const heads=same?`<th colspan="${models.length}" style="${cell}border-bottom:0.5pt solid #000;font-style:italic;">${esc(models[0].outcome)}</th>`:models.map(m=>`<th style="${cell}border-bottom:0.5pt solid #000;">${esc(m.outcome)}</th>`).join('');
  const header=`<thead><tr>${first}${heads}</tr><tr>${models.map((_,i)=>`<th style="${cell}border-bottom:0.5pt solid #000;">(${i+1})</th>`).join('')}</tr></thead>`;
  const body=rows.map((r,i)=>'<tr>'+r.cells.map((v,j)=>`<td style="${cell}${j===0?'text-align:left;':''}${r.type==='summary'&&rows[i-1]?.type!=='summary'?'border-top:0.5pt solid #000;':''}">${esc(v).replace(/(\*{1,3})$/,'<sup>$1</sup>')}</td>`).join('')+'</tr>').join('');
  const html=`<div style="${font}"><table cellspacing="0" cellpadding="0" style="${font}border-collapse:collapse;border-top:1pt solid #000;border-bottom:1pt solid #000;">${header}<tbody>${body}</tbody></table><p>${esc(note)}</p><p>${details.map(esc).join('<br>')}</p></div>`;
  const plain=[['变量',...models.map((m,i)=>`${m.outcome} (${i+1})`)].join('\t'),...rows.map(r=>r.cells.join('\t')),note,...details].join('\n');
  return {html,plain};
}

export default function CombinedRegression({events}){
  const reports=useMemo(()=>regressionReports(events),[events]);
  const proposal=useMemo(()=>[...events].reverse().find(e=>!e.error&&e.combined_regression)?.combined_regression,[events]);
  const [selection,setSelection]=useState([]);const [variables,setVariables]=useState([]);const [groups,setGroups]=useState([]);const [visible,setVisible]=useState(false);const [status,setStatus]=useState('');
  useEffect(()=>{if(proposal){setSelection(proposal.model_numbers.map(n=>n-1));setVariables(proposal.variables||[]);setGroups(proposal.control_groups||[]);setVisible(true)}},[proposal]);
  if(!reports.length)return null;
  const toggle=i=>setSelection(old=>old.includes(i)?old.filter(x=>x!==i):[...old,i].sort((a,b)=>a-b));
  const validSelection=selection.filter(i=>i>=0&&i<reports.length);
  const table=visible&&validSelection.length?combinedTable(reports,validSelection,variables,groups):null;
  async function copy(){try{const {html,plain}=combinedWordContent(table);if(navigator.clipboard?.write&&typeof ClipboardItem!=='undefined'){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);setStatus('已复制，可粘贴到 Word。')}else if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(plain);setStatus('已复制文本，请在 Word 中转换为表格。')}else throw Error()}catch{setStatus('复制失败，请检查浏览器剪贴板权限。')}}
  return <section className="statistics-result"><div className="statistics-result-head"><strong>合并回归表</strong>{table&&<button type="button" className="outline-action" aria-label="复制合并回归表到 Word" title="复制到 Word" onClick={copy}><Copy size={14}/></button>}</div>
    <p className="footnote">选择要合并的模型；默认展示各模型的解释变量，控制变量和固定效应按实际设定列示。</p>
    <div>{reports.map((m,i)=><label key={i} style={{display:'inline-flex',gap:6,margin:'4px 12px 4px 0'}}><input type="checkbox" checked={selection.includes(i)} onChange={()=>toggle(i)}/>{`模型 ${i+1} · ${m.outcome} · N=${m.n??'—'}`}</label>)}</div>
    <button type="button" className="outline-action" disabled={!selection.length} onClick={()=>{setVariables([]);setGroups([]);setVisible(true)}}>生成合并表</button>
    {table&&<><div className="table-wrap"><table><thead><tr><th rowSpan="2">变量</th>{table.models.every(m=>m.outcome===table.models[0].outcome)?<th colSpan={table.models.length}>{table.models[0].outcome}</th>:table.models.map((m,i)=><th key={i}>{m.outcome}</th>)}</tr><tr>{table.models.map((_,i)=><th key={i}>({i+1})</th>)}</tr></thead><tbody>{table.rows.map((r,i)=><tr key={i}>{r.cells.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div><p className="footnote">{table.note}</p>{table.details.map((d,i)=><p className="footnote" key={i}>{d}</p>)}</>}<p className="statistics-copy-status" role="status">{status}</p>
  </section>;
}
