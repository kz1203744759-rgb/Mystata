"""Validate and compile a user-specified winsor2 operation."""
import math
import re
from pathlib import Path


def validate_winsor(spec, dataset):
    variables=spec.get('variables')
    if not isinstance(variables,list) or not 1<=len(variables)<=50 or any(not isinstance(name,str) for name in variables) or len(set(variables))!=len(variables):
        raise ValueError('请选择 1 至 50 个不重复的连续变量。')
    available={v['name'] for v in dataset.get('variables',[])}
    canonical=[]
    for name in variables:
        if not name.isidentifier() or len(name.encode('utf-8'))>32:
            raise ValueError(f'变量 {name!r} 不存在或名称不受支持。')
        if name not in available:
            candidates=[v for v in available if v.casefold()==name.casefold()]
            if len(candidates)!=1:raise ValueError(f'变量 {name!r} 不存在或大小写存在歧义。')
            name=candidates[0]
        if name.casefold() in {'id','year','stock_code','stkcd','证券代码','年份'}:
            raise ValueError(f'{name} 是标识或年份字段，不能作为连续变量缩尾。')
        canonical.append(name)
    variables=canonical
    if len(set(variables))!=len(variables):raise ValueError('请选择不重复的连续变量。')
    low,high=spec.get('lower'),spec.get('upper')
    if isinstance(low,bool) or isinstance(high,bool) or not isinstance(low,(int,float)) or not isinstance(high,(int,float)) or not math.isfinite(low) or not math.isfinite(high) or not (0<=low<high<=100) or (low==0 and high==100):
        raise ValueError('请指定有效的上下分位点：0 ≤ 下限 < 上限 ≤ 100，且不能同时为 0 和 100。')
    mode=spec.get('mode')
    if mode not in {'new','replace'}:raise ValueError('请指定生成新变量或覆盖原变量。')
    suffix=spec.get('suffix','_w')
    if mode=='new':
        if not isinstance(suffix,str) or not re.fullmatch(r'_[A-Za-z0-9_]{1,20}',suffix):raise ValueError('新变量后缀须以下划线开头，只能包含英文字母、数字和下划线。')
        for name in variables:
            target=name+suffix
            if len(target.encode('utf-8'))>32:raise ValueError(f'生成变量 {target} 的名称超过 Stata 长度限制。')
            if target in available:raise ValueError(f'变量 {target} 已存在，请更换后缀。')
    return {'variables':variables,'lower':float(low),'upper':float(high),'mode':mode,'suffix':suffix if mode=='new' else ''}


def prepare_agent_winsor(args, dataset):
    """Turn the model's structured intent into validated Stata percentiles."""
    if not isinstance(args, dict):
        raise ValueError('缩尾参数格式无效。')
    if args.get('scope') != 'all':
        raise ValueError('目前仅支持全样本缩尾，暂不支持分组缩尾。')
    kind = args.get('cut_kind')
    if kind == 'unspecified' or not kind:
        raise ValueError('请指定本次缩尾的比例或上下分位点。')
    first, second = args.get('p1'), args.get('p2')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (first, second)):
        raise ValueError('缩尾比例和分位点必须为有效数字。')
    if kind == 'symmetric':
        low, high = first, 100 - first
    elif kind == 'percentiles':
        low, high = first, second
    elif kind == 'lower_tail':
        low, high = first, 100
    elif kind == 'upper_tail':
        low, high = 0, 100 - first
    else:
        raise ValueError('无法识别缩尾方式，请说明缩尾比例或上下分位点。')
    spec = validate_winsor({'variables': args.get('variables'), 'lower': low, 'upper': high,
                            'mode': args.get('mode'), 'suffix': args.get('suffix') or '_w'}, dataset)
    excluded = args.get('excluded_variables', [])
    if not isinstance(excluded, list) or any(not isinstance(v, str) for v in excluded):
        raise ValueError('排除的变量格式无效。')
    if {v.casefold() for v in excluded} & {v.casefold() for v in spec['variables']}:
        raise ValueError('所选变量与排除变量有冲突，请明确需要处理的变量。')
    return spec


def compile_winsor(spec, previous, frame, output, readable=False):
    low,high=format(spec['lower'],'.12g'),format(spec['upper'],'.12g')
    variables=spec['variables'];mode=spec['mode'];suffix=spec['suffix']
    lines=['* 对用户指定的连续变量进行缩尾。',
           '* 输入为当前已挂载的主分析集；在副本上处理，原始文件不变。']
    if readable:
        lines += ['* 本可读脚本根据实际参数生成，运行前请加载对应主分析集。',
                  'local original_frame = c(frame)','tempname winsor_frame',"frame copy `original_frame' `winsor_frame'", "frame change `winsor_frame'"]
    else:lines += [f'frame copy {previous} {frame}',f'frame change {frame}']
    lines += ['capture which winsor2','if _rc {', '    display as error "winsor2 未安装，请先安装 winsor2。"', '    exit 499','}']
    for i,var in enumerate(variables,1):
        lines += [f'* 检查变量 {var}',f'confirm numeric variable {var}',
                  f'quietly count if !missing({var})', 'if r(N) < 2 {', f'    display as error "{var} 的非缺失观测不足两条。"','    exit 2000','}',
                  f'quietly count if !missing({var}) & !inlist({var}, 0, 1)', 'if r(N) == 0 {',f'    display as error "{var} 仅包含 0/1，不作为连续变量缩尾。"','    exit 459','}',
                  f'local original_type_{i} : type {var}',f'tempvar before_{i}',f'quietly generate double `before_{i}\' = {var}',f'recast double {var}']
    option='replace' if mode=='replace' else f'suffix({suffix})'
    lines += ['',f'* 上下分位点：{low} 和 {high}',f'winsor2 {" ".join(variables)}, cuts({low} {high}) {option}']
    for i,var in enumerate(variables,1):
        target=var if mode=='replace' else var+suffix
        if mode=='new': lines.append(f"recast `original_type_{i}' {var}")
        lines += [f"quietly count if !missing(`before_{i}') & `before_{i}' != {target}",f'display "WINSOR_CHANGED_{i}=" r(N)']
    lines.append('drop '+' '.join(f"`before_{i}'" for i in range(1,len(variables)+1)))
    lines += ['',f'save "{Path(output).as_posix()}", replace','display "WINSOR_COMPLETED"']
    return '\n'.join(lines)+'\n'
