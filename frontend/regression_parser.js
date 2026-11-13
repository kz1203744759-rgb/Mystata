// Read complete regression tables already printed by Stata; never infer missing values.
const numberPattern='[-+]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)(?:[eE][-+]?\\d+)?';
const valueRe=new RegExp(`^\\s*(${numberPattern})\\s+(${numberPattern})\\s+(${numberPattern})\\s+(${numberPattern}|\\.)\\s+(${numberPattern})\\s+(${numberPattern})\\s*$`);
const separator=line=>/^\s*-{3,}\+-{3,}/.test(line);

export function parseStataRegressions(event){
  if(event?.error||event?.tool!=='run_stata'||!event.output)return [];
  const lines=String(event.output).replace(/\r/g,'').split('\n');
  const models=[];
  for(let h=0;h<lines.length;h++){
    const header=lines[h].match(/^\s*(\S+)\s*\|\s*Coefficient\s+std\.\s*err\./i);
    if(!header)continue;
    let command=h-1;
    while(command>=0&&!/^\s*\.\s*(?:(?:quietly|qui|capture|cap|noisily)\s+)*(?:reghdfe|regress|reg|xtreg|areg)\s/i.test(lines[command]))command--;
    if(command<0)continue;
    const before=lines.slice(command,h).join('\n');
    const matchN=before.match(/Number of obs\s*=\s*([\d,]+)/i);
    if(!matchN)continue;
    let start=h+1;while(start<lines.length&&!separator(lines[start]))start++;
    if(start>=lines.length)continue;
    let end=start+1;while(end<lines.length&&!separator(lines[end]))end++;
    if(end>=lines.length)continue;
    const coefficients=[];let valid=true;
    for(const line of lines.slice(start+1,end)){
      if(!line.trim())continue;
      const row=line.match(/^\s*(\S+)\s*\|\s*(.*?)\s*$/);
      if(!row){valid=false;break}
      if(/\(omitted\)/i.test(row[2])){coefficients.push({variable:row[1],omitted:true});continue}
      const values=row[2].match(valueRe);
      if(!values){valid=false;break}
      coefficients.push({variable:row[1],coefficient:Number(values[1]),se:Number(values[2]),p:values[4]==='.'?null:Number(values[4]),omitted:false});
    }
    if(!valid||!coefficients.length)continue;
    let next=end+1;while(next<lines.length&&!/^\s*\.\s*(?:(?:quietly|qui|capture|cap|noisily)\s+)*(?:reghdfe|regress|reg|xtreg|areg)\s/i.test(lines[next]))next++;
    const after=lines.slice(end+1,next).join('\n');
    const name=after.match(/\.\s*estimates\s+store\s+(\w+)/i)?.[1];
    const cluster=before.match(/Number of clusters\s*\(([^)]+)\)\s*=\s*([\d,]+)/i);
    const r2=before.match(/(?:^|\n)\s*R-squared\s*=\s*([\d.]+)/i);
    const within=before.match(/Within R-sq\.\s*=\s*([\d.]+)/i);
    const fixed=[];const fixedStart=after.indexOf('Absorbed FE');
    if(fixedStart>=0){
      for(const line of after.slice(fixedStart).split('\n').slice(1)){
        const m=line.match(/^\s*(\S+)\s*\|\s*\d+\s+\d+\s+\d+/);
        if(m)fixed.push(m[1]);
      }
    }
    models.push({name:name||`模型 ${models.length+1}`,outcome:header[1],coefficients,n:Number(matchN[1].replace(/,/g,'')),
      r2:r2?Number(r2[1]):null,within:within?Number(within[1]):null,
      cluster:cluster?cluster[1].trim():'',clusters:cluster?Number(cluster[2].replace(/,/g,'')):null,
      fixed,command:lines[command].trim()});
    h=end;
  }
  return models;
}
