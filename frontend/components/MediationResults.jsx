import React,{useState} from 'react';
import {Copy} from 'lucide-react';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>typeof n==='number'&&Number.isFinite(n)?(Object.is(n,-0)?0:n).toFixed(4):'—';
const stars=p=>p==null?'':p<.01?'***':p<.05?'**':p<.1?'*':'';
export function mediationTable(r){
  const rows=[r.exposure,...(r.method==='fitted_two_stage'?r.mediators.map(v=>v+'_hat'):r.mediators)].flatMap(name=>{
    const values=r.models.map(m=>m.coefficients.find(c=>c.variable===name));
    return [[name,...values.map(v=>!v?'—':v.omitted?'已省略':fmt(v.coefficient)+stars(v.p))],['',...values.map(v=>!v||v.omitted?'':`(${fmt(v.se)})`)]];
  });
  const fe=r.fixed_effects.map(v=>v.join(' × ')).join(' + ');
  rows.push(['控制变量',...r.models.map(()=>r.controls.length?'是':'否')],['固定效应',...r.models.map(()=>fe)],['观测数',...r.models.map(m=>String(m.n??'—'))],['R²',...r.models.map(m=>fmt(m.r2))]);
  const caution=r.method==='jiang'?'两步机制检验不估计间接效应。':r.method==='fitted_two_stage'?'第二阶段标准误直接来自拟合值回归，未校正第一阶段拟合值的不确定性；仅凭显著性不能认定因果中介。':'逐步回归及显著性不能单独证明因果中介。';
  const note=`括号内为标准误；*** p<0.01，** p<0.05，* p<0.10。${r.se_type==='cluster'?`标准误按 ${r.cluster} 聚类。`:r.se_type==='robust'?'使用稳健标准误。':'使用常规标准误。'}各列使用对应回归的非缺失样本；样本量相同不代表样本完全一致。${caution}`;
  return {headers:['变量',...r.models.map((m,i)=>`(${i+1}) ${m.outcome}`)],rows,note};
}
export function mediationWord(r){
  const table=mediationTable(r),font="font-family:SimSun,'宋体',serif;mso-fareast-font-family:SimSun;font-size:9pt;color:#000;";
  const row=(v,h)=>'<tr>'+v.map((x,i)=>`<${h?'th':'td'} style="padding:2pt 6pt;text-align:${i?'center':'left'};${h?'border-bottom:0.5pt solid #000;':''}">${esc(x).replace(/(\*{1,3})$/,'<sup>$1</sup>')}</${h?'th':'td'}>`).join('')+'</tr>';
  const html=`<div style="${font}"><table style="${font}border-collapse:collapse;border-top:1pt solid #000;border-bottom:1pt solid #000">${row(table.headers,true)}${table.rows.map(r=>row(r,false)).join('')}</table><p>${esc(table.note)}</p></div>`;
  return {html,plain:[table.headers.join('\t'),...table.rows.map(r=>r.join('\t')),table.note].join('\n')};
}
function formula(r){const c=n=>r.controls.length?`+\\gamma_{${n}}^{\\prime}C_{it}`:'';const first=`Y_{it}=cX_{it}${c(0)}+\\mathrm{FE}_{0}+\\varepsilon_{it}`,second=`M_{it}=aX_{it}${c(1)}+\\mathrm{FE}_{1}+u_{it}`;return r.method==='jiang'?[first,second]:r.method==='fitted_two_stage'?[second,`Y_{it}=b\\widehat{M}_{it}${c(2)}+\\mathrm{FE}_{2}+v_{it}`]:[first,second,`Y_{it}=c^{\\prime}X_{it}+bM_{it}${c(2)}+\\mathrm{FE}_{2}+v_{it}`]}
function Card({report:r}){
  const [status,setStatus]=useState(''),table=mediationTable(r);
  async function copy(){try{const {html,plain}=mediationWord(r);if(navigator.clipboard?.write&&typeof ClipboardItem!=='undefined'){await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);setStatus('已复制，可粘贴到 Word。')}else{await navigator.clipboard.writeText(plain);setStatus('已复制文本，请在 Word 中转换为表格。')}}catch{setStatus('复制失败，请检查剪贴板权限。')}}
  async function copyFormula(){try{await navigator.clipboard.writeText(formula(r).join('\n'));setStatus('公式已复制。在 Word 中按 Alt+= 插入公式，选择 LaTeX 输入并粘贴，再设置小五字号。')}catch{setStatus('复制失败，请手动选择公式。')}}
  return <section className="statistics-result"><div className="statistics-result-head"><strong>{r.method==='jiang'?'江艇两步机制检验':r.method==='fitted_two_stage'?'拟合值两阶段机制回归':'传统三步中介回归'}</strong><button type="button" className="outline-action" onClick={copy} aria-label="复制中介结果到 Word"><Copy size={14}/></button></div>
    <div className="table-wrap"><table><thead><tr>{table.headers.map((v,i)=><th key={i}>{v}</th>)}</tr></thead><tbody>{table.rows.map((row,i)=><tr key={i}>{row.map((v,j)=><td key={j}>{v}</td>)}</tr>)}</tbody></table></div><p className="footnote">{table.note}</p><p className="footnote">控制变量：{r.controls.join('、')||'无'}；数据：{r.dataset||'未记录'}。</p>
    <div className="statistics-result-head"><strong>LaTeX 公式</strong><button type="button" className="outline-action" onClick={copyFormula} aria-label="复制中介公式"><Copy size={14}/></button></div>{formula(r).map((v,i)=><p key={i}><code style={{overflowWrap:'anywhere',fontFamily:'SimSun,serif',fontSize:'9pt'}}>{v}</code></p>)}<p className="footnote">X={r.exposure}，Y={r.outcome}，M={r.mediators.join('、')}；每个机制变量分别估计。Word 中可按 Alt+= 插入公式并设置小五字号。</p><p className="statistics-copy-status" role="status">{status}</p>
  </section>;
}
export default function MediationResults({events}){return <>{events.filter(e=>!e.error&&e.mediation_report).slice().reverse().map((e,i)=><Card key={i} report={e.mediation_report}/>)}</>}
