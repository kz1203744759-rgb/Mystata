"""Validate and compile a fixed-effects linear regression."""
import math
import re
from numeric_types import is_numeric_type

def validate_fixed_effects(spec,dataset):
    if not isinstance(spec,dict):raise ValueError('回归参数无效。')
    vars=dataset.get('variables',[])
    def resolve(value,numeric=False):
        if not isinstance(value,str) or not value or not value.isidentifier() or len(value.encode('utf-8'))>32:
            raise ValueError('请明确指定有效的变量名。')
        matches=[v for v in vars if v['name']==value] or [v for v in vars if v['name'].casefold()==value.casefold()]
        if len(matches)!=1:raise ValueError(f'变量 {value} 不存在或大小写有歧义。')
        v=matches[0]
        if numeric and not is_numeric_type(v.get('type','')):raise ValueError(f"{v['name']} 不是数值变量。")
        return v['name']
    y=resolve(spec.get('outcome'),True)
    explanatory=spec.get('explanatory_variables')
    if not isinstance(explanatory,list) or not 1<=len(explanatory)<=50:raise ValueError('请明确指定解释变量。')
    explanatory=[resolve(v,True) for v in explanatory]
    controls=spec.get('controls')
    if not isinstance(controls,list) or len(controls)>50:raise ValueError('控制变量格式无效。')
    controls=[resolve(v,True) for v in controls]
    if len(set([y,*explanatory,*controls]))!=1+len(explanatory)+len(controls):raise ValueError('因变量、解释变量和控制变量不能重复。')
    fixed=spec.get('fixed_effects')
    if not isinstance(fixed,list) or not 1<=len(fixed)<=10:raise ValueError('请明确指定固定效应。')
    effects=[]
    for effect in fixed:
        if not isinstance(effect,dict) or set(effect)!={'variables'} or not isinstance(effect['variables'],list) or not 1<=len(effect['variables'])<=3:
            raise ValueError('固定效应应由一个字段或多个交互字段构成。')
        columns=[resolve(v) for v in effect['variables']]
        if len(columns)!=len(set(columns)):raise ValueError('固定效应交互字段不能重复。')
        effects.append(columns)
    if len({tuple(sorted(item)) for item in effects})!=len(effects):raise ValueError('固定效应不能重复。')
    mode=spec.get('se_type')
    if mode not in ('cluster','robust','conventional'):raise ValueError('请明确标准误方式。')
    cluster=resolve(spec.get('cluster')) if mode=='cluster' else ''
    if mode!='cluster' and spec.get('cluster'):raise ValueError('标准误和聚类字段设置不一致。')
    return {'outcome':y,'explanatory_variables':explanatory,'controls':controls,'fixed_effects':effects,'se_type':mode,'cluster':cluster}

def compile_fixed_effects(s,path,readable=False):
    output=str(path).replace('\\','/')
    if any(c in output for c in ['"','\n','\r']):raise ValueError('结果路径无效。')
    names=[*s['explanatory_variables'],*s['controls']]
    option=f"vce(cluster {s['cluster']})" if s['se_type']=='cluster' else 'vce(robust)' if s['se_type']=='robust' else ''
    lines=['* 固定效应线性回归；基于当前主分析集。','capture which reghdfe',
           'if _rc {','    display as error "未安装 reghdfe。"','    exit 499','}',
           f"reghdfe {s['outcome']} {' '.join(names)}, absorb({' '.join('#'.join(v) for v in s['fixed_effects'])}) {option}".rstrip(),
           'tempname didfile',f'file open `didfile\' using "{output}", write text replace',
           'capture local clusters = e(N_clust)',"if _rc local clusters = .",
           'file write `didfile\' "M|" %24.16g (e(N)) "|" %24.16g (e(r2)) "|" %24.16g (e(df_r)) "|" %24.16g (`clusters\') _n']
    if readable:return '\n'.join(lines[:7])+'\n'
    for i,var in enumerate(names,1):
        lines += [f'local b = _b[{var}]',f'local se = _se[{var}]','local p = .',
                  "if `se' > 0 & !missing(`se') & e(df_r) > 0 & !missing(e(df_r)) local p = 2 * ttail(e(df_r), abs(`b'/`se'))",
                  f'file write `didfile\' "B|{i}|" %24.16g (`b\') "|" %24.16g (`se\') "|" %24.16g (`p\') _n']
    lines += ["file close `didfile'",'display "FIXED_EFFECTS_COMPLETED"']
    return '\n'.join(lines)+'\n'

def parse_fixed_effects(text,s):
    def n(x):
        x=x.strip()
        if re.fullmatch(r'\.[a-z]?',x,re.I):return None
        value=float(x)
        return value if math.isfinite(value) else None
    meta=None;rows={}
    for line in text.splitlines():
        part=line.split('|')
        if part[0]=='M' and len(part)==5:meta=[n(v) for v in part[1:]]
        elif part[0]=='B' and len(part)==5:rows[int(part[1])]=[n(v) for v in part[2:]]
        elif line.strip():raise ValueError('回归结果格式无效。')
    names=[*s['explanatory_variables'],*s['controls']]
    if meta is None or len(rows)!=len(names):raise ValueError('回归结果不完整。')
    coefficients=[]
    for i,name in enumerate(names,1):
        b,se,p=rows[i]
        coefficients.append({'variable':name,'coefficient':b,'se':se,'p':p,'omitted':se is None or se<=0})
    return {**s,'n':meta[0],'r2':meta[1],'df':meta[2],'clusters':meta[3],'coefficients':coefficients}
