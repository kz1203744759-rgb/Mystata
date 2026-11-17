"""Build a preview-only ETL plan from an explicit field mapping."""
import re
from etl_engine import IDENTIFIER, RESERVED, validate_plan


def _safe_name(value, used, fallback):
    name = re.sub(r'[^A-Za-z0-9_]', '_', value).strip('_')
    if not name or name[0].isdigit(): name = fallback
    name = name[:32]
    if name.lower() in {x.lower() for x in RESERVED}: name = fallback
    candidate = name
    number = 2
    while candidate.lower() in used:
        suffix = f'_{number}'
        candidate = name[:32-len(suffix)] + suffix
        number += 1
    used.add(candidate.lower())
    return candidate


def build_preview_plan(files, args):
    ids=args.get('file_ids')
    rows=args.get('mappings')
    keys=args.get('keys')
    if not isinstance(ids,list) or not 2<=len(ids)<=20 or len(ids)!=len(set(ids)) or any(fid not in files for fid in ids):
        raise ValueError('请选择 2 至 20 个不同的有效原始文件。')
    if not isinstance(rows,list) or not rows or not isinstance(keys,list) or not keys:
        raise ValueError('请提供完整字段映射和至少一个合并键。')
    seen={fid:set() for fid in ids};mapped=[];role_counts={'security_code':0,'year':0};used=set();adjustments=[]
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'target','role','sources'}:
            raise ValueError('字段映射格式无效。')
        target,role,sources=row['target'],row['role'],row['sources']
        if not isinstance(target,str) or not target.strip() or role not in {'security_code','year','company_name','other'} or not isinstance(sources,list) or not sources:
            raise ValueError('每行需提供目标名、字段角色和来源。')
        target=target.strip()
        if target in keys and (not IDENTIFIER.fullmatch(target) or target in RESERVED):
            raise ValueError(f'合并键 {target!r} 不是有效目标字段，请明确指定。')
        if role in {'security_code','year'}:
            if target.lower() in used: raise ValueError(f'目标字段 {target} 重复。')
            used.add(target.lower())
        else:
            original=target
            target=_safe_name(target,used,f'field_{len(mapped)+1}')
            if original in keys and target != original: raise ValueError(f'合并键 {original} 存在重名冲突，请先明确映射。')
            if target!=original: adjustments.append({'original':original,'target':target,'reason':'目标名规范化或避免重名'})
        if target=='id' and role!='security_code':raise ValueError('id 是证券代码目标字段，请先确认字段语义并选择证券代码角色。')
        if target=='year' and role!='year':raise ValueError('year 是年份目标字段，请先确认时间口径并选择年份角色。')
        if role=='security_code':
            if target!='id':raise ValueError('证券代码的目标字段必须是 id。')
            role_counts['security_code']+=1
        if role=='year':
            if target!='year':raise ValueError('已确认的年份目标字段必须是 year。')
            role_counts['year']+=1
        mapping={}
        for source in sources:
            if not isinstance(source,dict) or set(source)!={'file_id','column_index'}:
                raise ValueError('字段来源格式无效。')
            fid,index=source['file_id'],source['column_index']
            if fid not in seen or isinstance(index,bool) or not isinstance(index,int) or index<0 or index>=len(files[fid]['variables']):
                raise ValueError('来源字段不存在，请重新检查字段清单。')
            if index in seen[fid] or fid in mapping:raise ValueError('同一个来源字段不能映射多次。')
            seen[fid].add(index);mapping[fid]=index
        mapped.append({'target':target,'sources':mapping,'convert':'none',
                       'normalize':{'security_code':'stock','year':'year'}.get(role,'none'),
                       'keep':role!='company_name'})
    if role_counts['security_code']>1 or role_counts['year']>1:
        raise ValueError('证券代码或年份存在多个目标，请先确认各字段的含义。')
    for file_no,fid in enumerate(ids,1):
        for index,variable in enumerate(files[fid]['variables']):
            if index in seen[fid]: continue
            original=str(variable.get('name',''))
            name=original.strip().lower()
            if name in {'id','year','stkcd','stock_code','stockcode','证券代码','股票代码','企业代码','公司代码','年份','年度','fiscal_year','apply_year'}:
                raise ValueError(f'{files[fid]["filename"]} 的关键候选字段 {original} 未映射，请确认字段含义。')
            company=name in {'name','company_name','companyname','企业名称','公司名称','证券简称','股票简称'}
            target=_safe_name(original,used,f'field_{file_no}_{index+1}')
            mapped.append({'target':target,'sources':{fid:index},'convert':'none','normalize':'none','keep':not company})
            adjustments.append({'file':files[fid]['filename'],'column':original,'target':target,'reason':'企业名称按默认规则排除' if company else '自动保留未映射字段，未推断跨表同义'})
    plan={'file_ids':ids,'mode':'merge','cardinality':args.get('cardinality','1:1'),
          'keys':keys,'mappings':mapped,'drop_missing_keys':True,'drop_missing':[],
          'drop_all_missing':True,'sample_retention':'matched','conflict_policy':'stop',
          'year_filter':args.get('year_filter'),'mapping_adjustments':adjustments}
    validate_plan(plan,files)
    return plan
