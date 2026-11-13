import React from 'react';

export default function ProfileReport({report}){
  return <div className="profile-report">
    {report.files.map((file,index)=><section className="profile-file" key={`${file.file_id}-${file.offset}-${index}`}>
      <div className="profile-file-head"><strong>{file.file}</strong><span>{file.error?'检查未完成':`${file.observations?.toLocaleString() ?? '—'} 行 · ${file.column_count} 字段`}</span></div>
      {file.error?<p className="profile-error">{file.error}</p>:<div className="profile-table-wrap"><table><thead><tr><th>字段</th><th>存储类型</th><th>显示格式</th><th>变量标签</th></tr></thead><tbody>
        {file.columns.map((column,i)=><tr key={i}><td>{column.name}</td><td>{column.storage_type||column.type||'—'}</td><td>{column.display_format||'—'}</td><td>{column.label||'—'}</td></tr>)}
      </tbody></table></div>}
      {file.next_offset!=null&&<p className="profile-note">当前显示第 {file.offset+1}–{file.offset+file.columns.length} 个字段，还有后续字段。</p>}
      {(file.format_profiles||[]).map((profile,i)=><div className="profile-format" key={i}><b>{profile.column}</b><span>{profile.suggested_rule||'字段用途待核实'}</span>{'non_numeric' in profile&&<small>非数字 {profile.non_numeric} · 非整数 {profile.non_integer} · 超出范围 {profile.out_of_range}</small>}{'leading_zero_strings' in profile&&<small>前导零字符串 {profile.leading_zero_strings}</small>}{'space_variants' in profile&&<small>空格格式需检查 {profile.space_variants} · 非字符串 {profile.non_string_values}</small>}{profile.note&&<small>{profile.note}</small>}</div>)}
      {file.duplicate_check&&<div className="profile-duplicate"><strong>重复检查：{file.duplicate_check.columns.join(' + ')}</strong><span>{file.duplicate_check.duplicate_groups} 组 · 涉及 {file.duplicate_check.rows_in_duplicate_groups} 行 · 多余 {file.duplicate_check.surplus_rows} 行</span>{file.duplicate_check.examples?.length>0&&<details><summary>查看本地重复键样例（最多 5 组）</summary><div className="profile-table-wrap"><table><thead><tr>{file.duplicate_check.columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{file.duplicate_check.examples.map((row,i)=><tr key={i}>{file.duplicate_check.columns.map(c=><td key={c}>{row[c] == null?'—':String(row[c])}</td>)}</tr>)}</tbody></table></div><small>样例仅显示在本地结果中，不发送给模型。</small></details>}<small>{file.duplicate_check.equality_note}</small></div>}
    </section>)}
    {report.duplicate_request_status&&<p className="profile-note">{report.duplicate_request_status}</p>}
    <p className="profile-note">{report.note}</p>
  </div>;
}
