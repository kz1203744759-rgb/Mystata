import React, {useState} from 'react';
import {Copy} from 'lucide-react';

const fmt = value => value == null || !Number.isFinite(value) ? '—' : (Object.is(value, -0) ? 0 : value).toFixed(3);
const count = value => value == null ? '—' : String(value);
const stars = p => p == null ? '' : p < .01 ? '***' : p < .05 ? '**' : p < .1 ? '*' : '';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function tableModel(report, kind) {
  if (kind === 'descriptive') return {
    title:'描述性统计', headers:['变量','样本量 N','均值','标准差','中位数','最小值','最大值'],
    rows:report.descriptive.map(x=>[x.variable,count(x.n),fmt(x.mean),fmt(x.sd),fmt(x.median),fmt(x.min),fmt(x.max)]),
    note:'各变量按非缺失样本计算；数值保留三位小数。',
  };
  const pairCounts=report.correlation.flatMap((row,i)=>row.filter((cell,j)=>j<i && cell.n!=null).map(cell=>cell.n));
  const sampleNote=pairCounts.length ? `配对样本量 N：${Math.min(...pairCounts)}–${Math.max(...pairCounts)}。` : '';
  return {
    title:'Pearson 相关性检验', headers:['变量',...report.variables.map((v,i)=>`${i+1}. ${v}`)],
    rows:report.variables.map((v,i)=>[`${i+1}. ${v}`,...report.correlation[i].map((cell,j)=>j>i?'':cell.r==null?'—':fmt(cell.r)+(i===j?'':stars(cell.p)))]),
    note:`逐对非缺失样本；${sampleNote}双侧检验，*** p<0.01，** p<0.05，* p<0.10；— 表示无法计算。`,
  };
}

export function clipboardContent(table) {
  const cellStyle='padding:5px 10px;text-align:center;white-space:nowrap;';
  const header=table.headers.map(v=>`<th style="${cellStyle}border-bottom:1px solid black;">${esc(v)}</th>`).join('');
  const rows=table.rows.map(row=>'<tr>'+row.map((v,i)=>`<td style="${cellStyle}${i===0?'text-align:left;':''}">${esc(v)}</td>`).join('')+'</tr>').join('');
  const html=`<div style="font-family:宋体,SimSun,serif;font-size:10.5pt;color:black"><p><strong>${esc(table.title)}</strong></p><table style="border-collapse:collapse;border-top:1.5px solid black;border-bottom:1.5px solid black"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table><p>${esc(table.note)}</p></div>`;
  const plain=[table.title,table.headers.join('\t'),...table.rows.map(row=>row.join('\t')),table.note].join('\n');
  return {html,plain};
}

// Match the supplied Word example: six columns, small-five Song font and grid lines.
export function descriptiveWordContent(report) {
  const headers=['变量','均值','中位数','标准差','最小值','最大值'];
  const rows=report.descriptive.map(x=>[x.variable,fmt(x.mean),fmt(x.median),fmt(x.sd),fmt(x.min),fmt(x.max)]);
  const font="font-family:SimSun,'宋体',serif;mso-ascii-font-family:SimSun;mso-hansi-font-family:SimSun;mso-fareast-font-family:SimSun;font-size:9pt;color:#000;";
  function rowHtml(row,index){
    const top=index===0?'border-top:1.5pt solid #000;':'';
    const bottom=index===rows.length?'border-bottom:1.5pt solid #000;':'border-bottom:0.5pt solid #000;';
    return '<tr>'+row.map((value,i)=>{
      const right=i<row.length-1?'border-right:0.5pt solid #000;':'border-right:none;';
      const italics=index>0&&i===0?'font-style:italic;':'font-style:normal;';
      const cell=`width:16.666%;padding:2pt 4pt;text-align:center;vertical-align:middle;border-left:none;${top}${bottom}${right}`;
      return `<td width="16.666%" style="${cell}"><p style="margin:0;text-align:center;${font}${italics}font-weight:normal;"><span style="${font}${italics}font-weight:normal;">${esc(value)}</span></p></td>`;
    }).join('')+'</tr>';
  }
  const html=`<table cellspacing="0" cellpadding="0" style="width:100%;border-collapse:collapse;table-layout:fixed;${font}"><tbody>${[headers,...rows].map(rowHtml).join('')}</tbody></table>`;
  const plain=[headers,...rows].map(row=>row.join('\t')).join('\n');
  return {html,plain};
}

function ResultTable({report,kind}) {
  const [copyStatus,setCopyStatus]=useState('');
  const table=tableModel(report,kind);
  async function copy(){
    setCopyStatus('');
    const {html,plain}=kind==='descriptive'?descriptiveWordContent(report):clipboardContent(table);
    try {
      if (navigator.clipboard?.write && typeof ClipboardItem !== 'undefined') {
        await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([html],{type:'text/html'}),'text/plain':new Blob([plain],{type:'text/plain'})})]);
        setCopyStatus('已复制表格，可粘贴到 Word。');
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(plain);
        setCopyStatus('已复制制表符文本；此浏览器不支持复制表格样式，需在 Word 中转换并设置格式。');
      } else throw new Error('当前浏览器不支持复制，请手动选择表格。');
    } catch(e){setCopyStatus('复制失败，请检查浏览器剪贴板权限或手动选择表格。')}
  }
  return <section className="statistics-result"><div className="statistics-result-head"><strong>{table.title}</strong><button type="button" className="outline-action" onClick={copy} aria-label="复制到 Word" title="复制到 Word"><Copy size={14}/></button></div>
    <div className="table-wrap"><table><thead><tr>{table.headers.map((h,i)=><th key={i}>{h}</th>)}</tr></thead><tbody>{table.rows.map((row,i)=><tr key={i}>{row.map((value,j)=><td key={j} title={kind==='correlation'&&j>0&&j-1<=i?`配对样本量 N=${count(report.correlation[i][j-1].n)}${report.correlation[i][j-1].p==null?'':`，p=${report.correlation[i][j-1].p}`}`:undefined}>{value}</td>)}</tr>)}</tbody></table></div>
    <p className="footnote">{table.note}{kind==='correlation'?' 鼠标悬停单元格可查看每对变量的样本量和 p 值。':' 复制到 Word 时使用示例的六列格式，样本量仅在网页显示。'}</p><p className="statistics-copy-status" role="status">{copyStatus}</p>
  </section>;
}

export default function StatisticsResults({events}) {
  const reports=events.filter(e=>!e.error&&e.statistics_report).slice().reverse();
  return <div className="statistics-workbench">
    {reports.map((event,i)=><div className="statistics-group" key={i}><p className="footnote">基于执行时的主分析集：{event.statistics_report.dataset} {i===0?'（最近一次）':'（历史结果）'}</p>{event.statistics_report.descriptive&&<ResultTable report={event.statistics_report} kind="descriptive"/>}{event.statistics_report.correlation&&<ResultTable report={event.statistics_report} kind="correlation"/>}</div>)}
  </div>;
}
