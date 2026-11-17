"""Traditional event-study specification and result extraction."""
import math
import re
from did_engine import validate_fixed_effects
from numeric_types import is_numeric_type

def validate_event_study(spec,dataset):
    if not isinstance(spec,dict):raise ValueError('事件研究参数无效。')
    base=validate_fixed_effects({'outcome':spec.get('outcome'),'explanatory_variables':[spec.get('treated')], 'controls':spec.get('controls'),'fixed_effects':spec.get('fixed_effects'),'se_type':spec.get('se_type'),'cluster':spec.get('cluster')},dataset)
    variables=dataset.get('variables',[])
    def resolve(value,numeric=True):
        if not isinstance(value,str) or not value.isidentifier() or len(value.encode('utf8'))>32:raise ValueError('请指定有效的字段名。')
        found=[v for v in variables if v['name']==value] or [v for v in variables if v['name'].casefold()==value.casefold()]
        if len(found)!=1:raise ValueError(f'字段 {value} 不存在或有歧义。')
        if numeric and not is_numeric_type(found[0].get('type','')):raise ValueError(f'字段 {value} 必须是数值型。')
        return found[0]['name']
    low,high,reference=spec.get('min_period'),spec.get('max_period'),spec.get('reference_period')
    if any(type(x) is not int for x in (low,high,reference)) or not (-20<=low<=-2 and 0<=high<=20 and low<reference<0):raise ValueError('请指定有效的前后窗口及政策前基准期；基准期不能是合并端点。')
    if sum(1 for k in range(low,0) if k!=reference)<1:raise ValueError('至少需要一个可检验的政策前期。')
    unit=resolve(spec.get('unit'),False);year=resolve(spec.get('year'));cohort=resolve(spec.get('cohort'))
    treated=base.pop('explanatory_variables')[0]
    if len({unit,year,cohort,treated})!=4:raise ValueError('个体、年份、政策年份和处理组字段必须不同。')
    return {**base,'treated':treated,'unit':unit,'year':year,'cohort':cohort,'min_period':low,'max_period':high,'reference_period':reference}

def compile_event_study(s,result_path,frame):
    path=str(result_path).replace('\\','/')
    if any(c in path for c in ['"','\r','\n']) or not re.fullmatch(r'ev[a-f0-9]{12}',frame):raise ValueError('路径或临时数据框无效。')
    t,y,g,i=s['treated'],s['year'],s['cohort'],s['unit']
    low,high,ref=s['min_period'],s['max_period'],s['reference_period']
    periods=[k for k in range(low,high+1) if k!=ref]
    def mac(k):return f'e{abs(k)}m' if k<0 else f'e{k}p'
    def val(k):return f"`{mac(k)}'"
    lines=['* 传统 TWFE 事件研究；在临时数据框中运行，不修改主分析集。',"local event_original_frame = c(frame)",f'frame put _all, into({frame})',f'frame change {frame}',
      f'isid {i} {y}',f'assert inlist({t},0,1) & !missing({t})',f'assert {y}==floor({y}) & !missing({y})',
      f'assert !missing({g}) & {g}==floor({g}) if {t}==1',f'bysort {i} ({y}): assert {t}=={t}[1]',f'bysort {i} ({y}): assert {g}=={g}[1] if {t}==1',
      'tempvar relative',f'gen double `relative\' = {y}-{g} if {t}==1']
    for k in periods:
        condition=f"`relative' <= {low}" if k==low else f"`relative' >= {high}" if k==high else f"`relative' == {k}"
        lines.extend([f'tempvar {mac(k)}',f"gen byte {val(k)} = ({t}==1 & {condition})"])
    fe=' '.join('#'.join(x) for x in s['fixed_effects'])
    option=f"vce(cluster {s['cluster']})" if s['se_type']=='cluster' else 'vce(robust)' if s['se_type']=='robust' else ''
    rhs=' '.join([*(val(k) for k in periods),*s['controls']])
    lines += ['capture which reghdfe','if _rc exit 499',f"reghdfe {s['outcome']} {rhs}, absorb({fe}) {option}".rstrip(),
        f"quietly count if e(sample) & {t}==1 & `relative'=={ref}","if r(N)==0 {",'    display as error "估计样本中没有处理组基准期观测。"','    exit 2000','}',
        'if missing(e(df_r)) | e(df_r)<=0 exit 2001',"local critical = invttail(e(df_r), 0.025)"]
    for k in periods:
        lines += [f"if _se[{val(k)}] <= 0 | missing(_se[{val(k)}]) {{",f'    display as error "相对时期 {k} 的系数被省略或标准误不可用。"','    exit 459','}']
    pre=' '.join(val(k) for k in periods if k<0)
    lines += [f'test {pre}',"local pre_p = r(p)","local pre_f = r(F)","local pre_df = r(df)","local pre_df_r = r(df_r)",
        'tempname out',f'file open `out\' using "{path}", write text replace',
        'file write `out\' "M|" %24.16g (e(N)) "|" %24.16g (`pre_p\') "|" %24.16g (`pre_f\') "|" %24.16g (`pre_df\') "|" %24.16g (`pre_df_r\') _n']
    for k in periods:
        v=val(k)
        lines += [f"file write `out' \"B|{k}|\" %24.16g (_b[{v}]) \"|\" %24.16g (_se[{v}]) \"|\" %24.16g (_b[{v}]-`critical'*_se[{v}]) \"|\" %24.16g (_b[{v}]+`critical'*_se[{v}]) _n"]
    lines += ["file close `out'","frame change `event_original_frame'",f'frame drop {frame}','display "EVENT_STUDY_COMPLETED"']
    return '\n'.join(lines)+'\n'

def parse_event_study(text,s):
    def number(x):
        if re.fullmatch(r'\.[a-z]?',x.strip(),re.I):return None
        v=float(x);return v if math.isfinite(v) else None
    meta=None;points={}
    for line in text.splitlines():
        p=line.split('|')
        if p[0]=='M' and len(p)==6:meta=[number(v) for v in p[1:]]
        elif p[0]=='B' and len(p)==6:points[int(p[1])]=[number(v) for v in p[2:]]
        elif line.strip():raise ValueError('事件研究结果格式无效。')
    expected=set(range(s['min_period'],s['max_period']+1))-{s['reference_period']}
    if meta is None or set(points)!=expected or any(any(v is None for v in row) for row in points.values()):raise ValueError('事件研究结果不完整。')
    values=[{'period':k,'coefficient':0,'lower':None,'upper':None,'reference':True} if k==s['reference_period'] else {'period':k,'coefficient':points[k][0],'se':points[k][1],'lower':points[k][2],'upper':points[k][3],'reference':False} for k in range(s['min_period'],s['max_period']+1)]
    return {**s,'n':meta[0],'pre_p':meta[1],'pre_f':meta[2],'pre_df':meta[3],'pre_df_r':meta[4],'points':values}
