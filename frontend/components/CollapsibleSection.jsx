import React, {useId, useState} from 'react';
import {ChevronDown, ChevronRight} from 'lucide-react';

export default function CollapsibleSection({title,summary,storageKey,children}) {
  const id=useId();
  const [expanded,setExpanded]=useState(()=>{
    try{return localStorage.getItem(storageKey)!=='collapsed'}catch{return true}
  });
  function toggle(){
    const next=!expanded;
    setExpanded(next);
    try{localStorage.setItem(storageKey,next?'expanded':'collapsed')}catch{}
  }
  return <section className="sidebar-collapsible">
    <button type="button" className="raw-collapse-header" aria-label={title} aria-expanded={expanded} aria-controls={id} onClick={toggle}>
      <span>{expanded?<ChevronDown size={14}/>:<ChevronRight size={14}/>} {title}</span><span>{summary}</span>
    </button>
    <div id={id} hidden={!expanded}>{children}</div>
  </section>;
}
