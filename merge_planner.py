"""Build a preview-only ETL plan from an explicit field mapping."""
from etl_engine import validate_plan


def build_preview_plan(files, args):
    ids=args.get('file_ids')
    rows=args.get('mappings')
    keys=args.get('keys')
    if not isinstance(ids,list) or not 2<=len(ids)<=20 or len(ids)!=len(set(ids)) or any(fid not in files for fid in ids):
        raise ValueError('请选择 2 至 20 个不同的有效原始文件。')
    if not isinstance(rows,list) or not rows or not isinstance(keys,list) or not keys:
        raise ValueError('请提供完整字段映射和至少一个合并键。')
    seen={fid:set() for fid in ids};mapped=[];role_counts={'security_code':0,'year':0}
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'target','role','sources'}:
            raise ValueError('字段映射格式无效。')
        target,role,sources=row['target'],row['role'],row['sources']
        if not isinstance(target,str) or not target.strip() or role not in {'security_code','year','company_name','other'} or not isinstance(sources,list) or not sources:
            raise ValueError('每行需提供目标名、字段角色和来源。')
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
    for fid in ids:
        if seen[fid]!=set(range(len(files[fid]['variables']))):
            raise ValueError(f'{files[fid]["filename"]} 的字段映射不完整；其余字段应保留，企业名称须明确标记。')
    plan={'file_ids':ids,'mode':'merge','cardinality':args.get('cardinality','1:1'),
          'keys':keys,'mappings':mapped,'drop_missing_keys':True,'drop_missing':[],
          'drop_all_missing':True,'sample_retention':'matched','conflict_policy':'stop'}
    validate_plan(plan,files)
    return plan
