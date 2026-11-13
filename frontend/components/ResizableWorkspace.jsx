import React, {useEffect, useRef, useState} from 'react';

const defaults = [22, 34, 44];
const minimums = [18, 24, 24];

function readWidths() {
  try {
    const value = JSON.parse(localStorage.getItem('econagent-pane-widths'));
    if (Array.isArray(value) && value.length === 3 && value.every((n,i)=>Number.isFinite(n) && n >= minimums[i]) && Math.abs(value.reduce((a,b)=>a+b,0)-100)<0.1) return value;
  } catch {}
  return defaults;
}

export default function ResizableWorkspace({left,center,right}) {
  const [widths,setWidths] = useState(readWidths);
  const container = useRef(null);
  const drag = useRef(null);
  useEffect(()=>{try{localStorage.setItem('econagent-pane-widths', JSON.stringify(widths))}catch{}},[widths]);
  useEffect(()=>{
    function move(event) {
      if (!drag.current || !container.current) return;
      const {index,start,initial} = drag.current;
      const delta=(event.clientX-start)/container.current.getBoundingClientRect().width*100;
      const bounded=Math.max(minimums[index]-initial[index],Math.min(initial[index+1]-minimums[index+1],delta));
      const next=[...initial]; next[index]+=bounded; next[index+1]-=bounded; setWidths(next);
    }
    function end(){drag.current=null;document.body.classList.remove('resizing');}
    window.addEventListener('pointermove',move); window.addEventListener('pointerup',end); window.addEventListener('pointercancel',end);
    return ()=>{window.removeEventListener('pointermove',move);window.removeEventListener('pointerup',end);window.removeEventListener('pointercancel',end);document.body.classList.remove('resizing')};
  },[]);
  function start(event,index){if(event.button!==0)return;event.preventDefault();drag.current={index,start:event.clientX,initial:[...widths]};document.body.classList.add('resizing')}
  function keyboard(event,index){if(!['ArrowLeft','ArrowRight'].includes(event.key))return;event.preventDefault();const delta=event.key==='ArrowLeft'?-2:2;setWidths(old=>{const d=Math.max(minimums[index]-old[index],Math.min(old[index+1]-minimums[index+1],delta));const next=[...old];next[index]+=d;next[index+1]-=d;return next})}
  const separator=(index,label)=><div className="pane-divider" role="separator" aria-orientation="vertical" aria-label={label} tabIndex="0" onPointerDown={event=>start(event,index)} onKeyDown={event=>keyboard(event,index)}><span/></div>;
  return <div ref={container} className="layout resizable-layout" style={{gridTemplateColumns:`minmax(0, ${widths[0]}fr) 7px minmax(0, ${widths[1]}fr) 7px minmax(0, ${widths[2]}fr)`}}>{left}{separator(0,'调整数据工作区和研究对话宽度')}{center}{separator(1,'调整研究对话和分析工作台宽度')}{right}</div>;
}
