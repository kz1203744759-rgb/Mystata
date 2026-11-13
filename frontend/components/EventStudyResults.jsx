import React,{useState} from 'react';
import {Copy,Download} from 'lucide-react';

export function latexFormula(r){
  const controls=r.controls?.length?' + \\mathbf{X}_{it}^{\\prime}\\gamma':'';
  return `Y_{it}=\\alpha+\\sum_{k=${r.min_period},\\,k\\ne ${r.reference_period}}^{${r.max_period}}\\beta_k D_{it}^{k}${controls}+\\sum_h\\eta_{h,g_h(i,t)}+\\varepsilon_{it}`;
}
export function eventPlot(r){
  const points=r.points||[], w=720,h=430,L=88,R=36,T=26,B=62;
  const bounds=points.flatMap(p=>[p.coefficient,p.lower,p.upper]).filter(Number.isFinite).concat([0]);
  const min=Math.min(...bounds),max=Math.max(...bounds),span=Math.max(max-min,.01),pad=span*.12,ymin=min-pad,ymax=max+pad;
  const x=k=>L+(k-r.min_period)/(r.max_period-r.min_period)*(w-L-R),y=v=>T+(ymax-v)/(ymax-ymin)*(h-T-B);
  const line=points.map(p=>`${x(p.period).toFixed(1)},${y(p.coefficient).toFixed(1)}`).join(' ');
  const y0=y(0), zeroX=x(0);
  const ticks=Array.from({length:5},(_,i)=>ymin+(ymax-ymin)*i/4);
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="事件研究动态系数及95%置信区间"><rect width="100%" height="100%" fill="white"/><g stroke="black" stroke-width="1" fill="none"><path d="M ${L} ${T} V ${h-B} H ${w-R}"/><path d="M ${L} ${y0} H ${w-R}"/><path d="M ${zeroX} ${T} V ${h-B}"/><polyline points="${line}" stroke-width="1.2"/>${points.filter(p=>!p.reference).map(p=>`<path stroke-dasharray="5 4" d="M ${x(p.period)} ${y(p.lower)} V ${y(p.upper)}"/><path d="M ${x(p.period)-4} ${y(p.lower)} h 8 M ${x(p.period)-4} ${y(p.upper)} h 8"/>`).join('')}</g><g fill="black" font-family="SimSun,serif" font-size="14">${points.map(p=>`<circle cx="${x(p.period)}" cy="${y(p.coefficient)}" r="3.5"/><text x="${x(p.period)}" y="${h-B+22}" text-anchor="middle">${p.period}</text>`).join('')}${ticks.map(v=>`<text x="${L-10}" y="${y(v)+4}" text-anchor="end">${v.toFixed(3)}</text>`).join('')}<text x="${(L+w-R)/2}" y="${h-12}" text-anchor="middle">相对政策实施时间</text><text transform="translate(22 ${(T+h-B)/2}) rotate(-90)" text-anchor="middle">估计系数</text></g></svg>`;
  return svg;
}

function Study({report:r}){
  const [status,setStatus]=useState('');const formula=latexFormula(r),svg=eventPlot(r);
  async function copy(){try{await navigator.clipboard.writeText(formula);setStatus('已复制 LaTeX。在 Word 中按 Alt+= 插入公式，选择 LaTeX 输入并粘贴，再设置小五字号。')}catch{setStatus('复制失败，请手动选择公式。')}}
  function download(){const url=URL.createObjectURL(new Blob([svg],{type:'image/svg+xml;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='事件研究平行趋势.svg';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  return <section className="statistics-result"><div className="statistics-result-head"><strong>传统事件研究 · {r.outcome}</strong><button type="button" className="outline-action" onClick={download} title="下载矢量图" aria-label="下载平行趋势图"><Download size={14}/></button></div>
    <div style={{background:'#fff',overflowX:'auto'}} dangerouslySetInnerHTML={{__html:svg}}/>
    <p className="footnote">基准期：{r.reference_period}；{r.min_period} 和 {r.max_period} 分别包含更早和更晚时期。点为系数，虚线为 95% 置信区间；基准期的零点是归一化值。</p>
    <p>政策前系数联合检验：p = {r.pre_p==null?'不可用':Number(r.pre_p).toFixed(4)}；样本量：{r.n??'—'}。</p>
    <p className="footnote">未拒绝政策前系数为零不证明平行趋势成立。分批实施且处理效应异质时，传统 TWFE 的动态系数可能受到污染。</p>
    <div className="statistics-result-head"><strong>LaTeX 公式</strong><button type="button" className="outline-action" onClick={copy} aria-label="复制平行趋势公式"><Copy size={14}/></button></div><code style={{overflowWrap:'anywhere',fontFamily:'SimSun,serif',fontSize:'9pt'}}>{formula}</code><p className="footnote">公式的固定效应项表示本次指定的全部固定效应；按 Alt+= 在 Word 公式框中粘贴 LaTeX，选中公式后设置小五（9 磅）。</p><p role="status" className="statistics-copy-status">{status}</p>
  </section>;
}
export default function EventStudyResults({events}){return <>{events.filter(e=>!e.error&&e.event_study_report).slice().reverse().map((e,i)=><Study key={i} report={e.event_study_report}/>)}</>}
