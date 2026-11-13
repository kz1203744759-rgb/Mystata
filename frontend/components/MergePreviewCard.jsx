import React from 'react';
import {AlertCircle, CheckCircle2, Table2} from 'lucide-react';

function metricLabel(key){return key.replace(/^SOURCE_(\d+)_MISSING_KEYS$/,'文件 $1 主键缺失')
  .replace(/^SOURCE_(\d+)_DUPLICATE_ROWS$/,'文件 $1 重复键行')
  .replace(/^MERGE_(\d+)_MASTER_ONLY$/,'第 $1 次仅主表')
  .replace(/^MERGE_(\d+)_USING_ONLY$/,'第 $1 次仅从表')
  .replace(/^MERGE_(\d+)_MATCHED$/,'第 $1 次匹配')
  .replace(/^MERGE_(\d+)_CONFLICTS$/,'第 $1 次字段冲突')
  .replace(/^FIELD_(\d+)_(.+)$/,'第 $1 次 $2 冲突')
  .replace(/^FINAL_BEFORE_MISSING$/,'删除缺失前样本')
  .replace(/^ANALYSIS_MISSING_ROWS$/,'删除缺失行')
  .replace(/^FINAL_ROWS$/,'最终样本行')}

export default function MergePreviewCard({item}){
  const p=item.preview;
  return <div className="output-card"><div className="code-head"><Table2 size={15}/><b>合并预检</b><span className={p.ok?'success':'fail'}>{p.ok?'检查通过':'需要处理'}</span></div>
    <div className="merge-preview"><div className="merge-preview-summary">{p.ok?<CheckCircle2 size={16}/>:<AlertCircle size={16}/>}<span>{p.ok?'已完成预检，尚未生成或挂载主分析集。':p.error||'预检未通过，请查看日志。'}</span></div>
      <div className="etl-metrics"><span>关系：<b>{p.cardinality}</b></span><span>合并键：<b>{p.keys.join(' + ')}</b></span><span>样本：<b>仅保留匹配</b></span><span>缺失：<b>保留字段有缺失则删除</b></span></div>
      <div className="profile-table-wrap"><table><thead><tr><th>目标字段</th><th>来源</th><th>处理</th></tr></thead><tbody>{p.mappings.map((row,i)=><tr key={i}><td>{row.target}</td><td>{row.sources.map(source=>`${source.file}：${source.column}`).join('；')}</td><td>{!row.keep?'企业名称不保留':row.normalize==='stock'?'转 long':row.normalize==='year'?'转 float':'保持原格式'}</td></tr>)}</tbody></table></div>
      <div className="etl-metrics">{Object.entries(p.metrics||{}).map(([key,value])=><span key={key}>{metricLabel(key)}：<b>{value}</b></span>)}</div>
      {p.log&&<details className="system-log"><summary>查看预检日志</summary><pre>{p.log}</pre></details>}
    </div>
  </div>;
}
