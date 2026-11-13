"""Prepare mediation requests across turns without guessing model settings."""
import re
from mediation_engine import validate_mediation

def redirect_mediation_code(message,recent,code):
    """Redirect a narrow supported generated pattern; preserve explicit code requests."""
    if not isinstance(code,str) or not re.search(r'(?is)\breghdfe\b.*?\bpredict\b.*?\breghdfe\b',code):return False
    if re.search(r'```|\breghdfe\b|\brun_stata\b|执行(?:我|以下|这段|上述).{0,8}代码',message,re.I):return False
    if not re.search(r'中介|机制|mediation|mediator',message+' '+recent,re.I):return False
    if re.search(r'\b(?:ivreghdfe|ivregress|bootstrap|nlcom|suest|heckman)\b|\[(?:pw|aw|fw|iw|pweight|aweight|fweight|iweight)\s*=',code,re.I):return False
    if re.search(r'(?im)^\s*reghdfe\b[^\r\n]*\s(?:if|in)\s+[^,\r\n]+',code):return False
    clusters=re.findall(r'vce\s*\(\s*cluster\s+([^)]*)\)',code,re.I)
    if any(len(c.strip().split())!=1 for c in clusters):return False
    return True

def prepare_mediation(args,dataset,previous=None):
    if not isinstance(args,dict) or args.get('intent') not in ('run','preview','cancel'):raise ValueError('中介任务类型无效。')
    if args['intent']=='cancel':return None,[]
    for key in ('method','outcome','exposure','se_type','cluster'):
        if not isinstance(args.get(key),str):raise ValueError('中介任务字段格式无效。')
    for key in ('mediators','controls','fixed_effects'):
        if not isinstance(args.get(key),list):raise ValueError('中介任务字段格式无效。')
    if type(args.get('controls_specified')) is not bool or type(args.get('continue_previous')) is not bool:raise ValueError('中介任务状态无效。')
    old=(previous or {}) if args['continue_previous'] else {}
    plan={k:args[k] for k in ('method','outcome','exposure','mediators','controls','fixed_effects','se_type','cluster','controls_specified','intent')}
    for k in ('method','outcome','exposure','se_type','cluster'):
        if plan[k] in ('','unspecified') and old.get(k) not in (None,'','unspecified'):plan[k]=old[k]
    for k in ('mediators','fixed_effects'):
        if not plan[k] and old.get(k):plan[k]=old[k]
    if not plan['controls_specified'] and old.get('controls_specified'):
        plan['controls'],plan['controls_specified']=old['controls'],True
    if plan['se_type']!='cluster':plan['cluster']=''
    missing=[]
    if plan['method'] not in ('three_step','jiang','fitted_two_stage'):missing.append('中介方法')
    if not plan['outcome']:missing.append('被解释变量 Y')
    if not plan['exposure']:missing.append('解释变量 X')
    if not plan['mediators']:missing.append('中介变量')
    if not plan['controls_specified']:missing.append('控制变量（也可以指定不加）')
    if not plan['fixed_effects']:missing.append('固定效应')
    if plan['se_type'] not in ('cluster','robust','conventional'):missing.append('标准误方式')
    elif plan['se_type']=='cluster' and not plan['cluster']:missing.append('聚类字段')
    if not missing:
        spec={k:plan[k] for k in ('method','outcome','exposure','mediators','controls','fixed_effects','se_type','cluster')}
        validate_mediation(spec,dataset)
    return plan,missing

def execution_spec(plan):
    return {k:plan[k] for k in ('method','outcome','exposure','mediators','controls','fixed_effects','se_type','cluster')}
