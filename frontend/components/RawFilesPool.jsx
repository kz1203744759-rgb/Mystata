import React, {useRef, useState} from 'react';
import {ChevronDown, ChevronRight, Database, FileSpreadsheet, LoaderCircle, UploadCloud, WandSparkles} from 'lucide-react';

const size = n => n < 1024*1024 ? (n/1024).toFixed(1)+' KB' : (n/(1024*1024)).toFixed(1)+' MB';

export default function RawFilesPool({files,selected,onSelect,onUpload,onActivate,onOpen,onProfile=()=>{},busy,collapsed=false,onToggle=()=>{}}) {
  const input=useRef(null); const [dragging,setDragging]=useState(false);
  function change(event){onUpload(Array.from(event.target.files||[]));event.target.value=''}
  function drop(event){event.preventDefault();setDragging(false);if(!busy)onUpload(Array.from(event.dataTransfer.files||[]))}
  return <>
    <button type="button" className="raw-collapse-header" aria-expanded={!collapsed} onClick={onToggle}><span>{collapsed?<ChevronRight size={14}/>:<ChevronDown size={14}/>} 原始文件池</span><span>RAW FILES · {files.length}</span></button>
    <div hidden={collapsed}>
    <div className={'upload-drop '+(dragging?'dragging':'')} onDragOver={event=>{event.preventDefault();setDragging(true)}} onDragLeave={()=>setDragging(false)} onDrop={drop}>
      <input ref={input} type="file" accept=".dta,.csv,.xlsx" multiple hidden onChange={change}/>
      <button className="upload" disabled={busy} onClick={()=>input.current?.click()}>{busy?<LoaderCircle size={15} className="spin"/>:<UploadCloud size={15}/>} 点击上传或拖拽文件</button>
      <p className="upload-hint">支持多选 .dta、UTF-8 .csv、.xlsx；单个文件 ≤ 60 MB</p>
      <p className="upload-hint">后台重新启动会清空上传数据和历史产物，请先下载保存。</p>
    </div>
    {files.length>0?<div className="raw-list">{files.map(file=><div className="raw-row" key={file.id}><label className="raw-check"><input type="checkbox" checked={selected.includes(file.id)} onChange={()=>onSelect(file.id)} aria-label={'选择 '+file.filename}/><FileSpreadsheet size={15}/><span title={file.filename}><b>{file.filename}</b><small>{size(file.size)} · {file.observations.toLocaleString()} 行</small></span></label><button disabled={busy} onClick={()=>onActivate(file.id)} title="将此文件挂载为主分析集">挂载</button></div>)}</div>:<div className="raw-empty"><Database size={15}/> 上传的源文件不会覆盖主分析集</div>}
    {files.length>0&&<button className="profile-trigger" disabled={busy||selected.length===0} onClick={onProfile}><FileSpreadsheet size={14}/> 检查字段格式 <span>{selected.length} 个已选</span></button>}
    {files.length>1&&<button className="etl-trigger" disabled={busy||selected.length<2} onClick={onOpen}><WandSparkles size={15}/> 智能清洗与整合 <span>{selected.length} 个已选</span></button>}
    </div>
  </>;
}
