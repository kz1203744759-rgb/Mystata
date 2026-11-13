"""Validate and compile explicitly requested linear mechanism regressions."""
import math
import re
from did_engine import validate_fixed_effects

def validate_mediation(spec,dataset):
    if not isinstance(spec,dict) or spec.get('method') not in ('three_step','jiang','fitted_two_stage'):
        raise ValueError('请选择三步法、江艇两步法或拟合值两阶段法。')
    mediators=spec.get('mediators')
    if not isinstance(mediators,list) or not 1<=len(mediators)<=10:raise ValueError('请明确指定一个至十个机制变量。')
    base=validate_fixed_effects({'outcome':spec.get('outcome'),'explanatory_variables':[spec.get('exposure')], 'controls':spec.get('controls'),'fixed_effects':spec.get('fixed_effects'),'se_type':spec.get('se_type'),'cluster':spec.get('cluster')},dataset)
    resolved=[]
    for v in mediators:
        candidate=validate_fixed_effects({'outcome':v,'explanatory_variables':base['explanatory_variables'],'controls':base['controls'],'fixed_effects':spec.get('fixed_effects'),'se_type':base['se_type'],'cluster':base['cluster']},dataset)
        resolved.append(candidate['outcome'])
    x=base.pop('explanatory_variables')[0]
    if len(set(resolved))!=len(resolved) or base['outcome'] in resolved:raise ValueError('机制变量不能重复，也不能与因变量相同。')
    return {**base,'exposure':x,'mediators':resolved,'method':spec['method']}

def model_plan(s):
    models=[] if s['method']=='fitted_two_stage' else [{'stage':'total','outcome':s['outcome'],'mediator':None,'variables':[s['exposure']]}]
    for m in s['mediators']:
        models.append({'stage':'mechanism','outcome':m,'mediator':m,'variables':[s['exposure']]})
        if s['method']=='three_step':models.append({'stage':'adjusted','outcome':s['outcome'],'mediator':m,'variables':[s['exposure'],m]})
        if s['method']=='fitted_two_stage':models.append({'stage':'fitted','outcome':s['outcome'],'mediator':m,'variables':[m+'_hat']})
    return models

def compile_mediation(s,result_path,frame=None):
    path=str(result_path).replace('\\','/')
    if any(c in path for c in ['"','\n','\r']):raise ValueError('结果路径无效。')
    option=f"vce(cluster {s['cluster']})" if s['se_type']=='cluster' else 'vce(robust)' if s['se_type']=='robust' else ''
    fe=' '.join('#'.join(v) for v in s['fixed_effects'])
    isolated=s['method']=='fitted_two_stage'
    if isolated and (not isinstance(frame,str) or not re.fullmatch(r'md[a-f0-9]{12}',frame)):raise ValueError('临时数据框无效。')
    setup=["local med_original_frame = c(frame)",f'frame put _all, into({frame})',f'frame change {frame}'] if isolated else []
    cleanup=["frame change `med_original_frame'",f'frame drop {frame}'] if isolated else []
    lines=['* 中介与机制回归；使用当前主分析集，各列按 Stata 实际非缺失样本估计。',*setup,'capture which reghdfe','if _rc exit 499',
      'tempname output',f'file open `output\' using "{path}", write text replace']
    readable=['* 中介与机制回归；基于当前主分析集，各列按实际非缺失样本估计。',*setup]
    for i,m in enumerate(model_plan(s),1):
        desc={'total':'总效应','mechanism':'解释变量对机制变量','adjusted':'加入机制变量的结果回归','fitted':'机制变量拟合值对结果变量'}[m['stage']]
        fit_index=s['mediators'].index(m['mediator'])+1 if m['mediator'] else 0
        actual=[f"`medfit{fit_index}'"] if m['stage']=='fitted' else m['variables']
        command=f"reghdfe {m['outcome']} {' '.join([*actual,*s['controls']])}, absorb({fe}) {option}".rstrip()
        lines += [f'* 第 {i} 列：{desc}',command,
          f'file write `output\' "M|{i}|" %24.16g (e(N)) "|" %24.16g (e(r2)) "|" %24.16g (e(df_r)) _n']
        readable += [f'* 第 {i} 列：{desc}',command,'']
        for j,v in enumerate(actual,1):
            lines += [f'local b = _b[{v}]',f'local se = _se[{v}]','local p = .',
              "if `se' > 0 & !missing(`se') & e(df_r) > 0 & !missing(e(df_r)) local p = 2 * ttail(e(df_r), abs(`b'/`se'))",
              f'file write `output\' "B|{i}|{j}|" %24.16g (`b\') "|" %24.16g (`se\') "|" %24.16g (`p\') _n']
        if isolated and m['stage']=='mechanism':
            make=[f'tempvar medfit{fit_index}',f"predict `medfit{fit_index}' if e(sample)"]
            lines += make;readable += make+['']
    lines += ["file close `output'",*cleanup,'display "MEDIATION_COMPLETED"'];readable+=cleanup
    return '\n'.join(lines)+'\n','\n'.join(readable)+'\n'

def parse_mediation(text,s):
    def number(x):
        if re.fullmatch(r'\.[a-z]?',x.strip(),re.I):return None
        v=float(x);return v if math.isfinite(v) else None
    models=model_plan(s);meta={};rows={}
    for line in text.splitlines():
        p=line.split('|')
        if p[0]=='M' and len(p)==5:meta[int(p[1])]=[number(v) for v in p[2:]]
        elif p[0]=='B' and len(p)==6:rows[(int(p[1]),int(p[2]))]=[number(v) for v in p[3:]]
        elif line.strip():raise ValueError('机制回归结果格式无效。')
    result=[]
    for i,m in enumerate(models,1):
        if i not in meta or any((i,j) not in rows for j in range(1,len(m['variables'])+1)):raise ValueError('机制回归结果不完整。')
        coefficients=[]
        for j,name in enumerate(m['variables'],1):
            b,se,p=rows[(i,j)];coefficients.append({'variable':name,'coefficient':b,'se':se,'p':p,'omitted':se is None or se<=0})
        n,r2,df=meta[i];result.append({**m,'n':n,'r2':r2,'df':df,'coefficients':coefficients})
    return {**s,'models':result}
