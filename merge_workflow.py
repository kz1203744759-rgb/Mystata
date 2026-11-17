"""Route explicit multi-file merge tasks through the verified ETL workflow."""
import re


def resolve_year_filter(text, proposed):
    """Honor an explicit inclusive year range; never guess an excluded range."""
    pattern=r'(?<!\d)((?:1|2)\d{3})\s*年?\s*(?:-|–|—|~|～|至|到)\s*((?:1|2)\d{3})\s*年?'
    matches=list(re.finditer(pattern,text))
    if not matches:
        if proposed is None and re.search(r'(?<!\d)(?:1|2)\d{3}\s*年?\s*(?:以后|之后|及以后|以前|之前|及以前)',text):
            raise ValueError('检测到年份筛选要求，但年份边界未能确认，请明确筛选范围。')
        return proposed
    candidates=[]
    for match in matches:
        prefix=text[max(0,match.start()-24):match.start()]
        if re.search(r'(?:排除|剔除|不要|去掉|不包括)\s*$',prefix):
            raise ValueError('检测到排除年份范围的要求；当前只支持保留范围，请明确样本筛选方式。')
        if re.search(r'(?:保留|筛选|限定|限制|选取|只要|样本(?:期|范围)?|年份范围|年度范围|从)\s*[^，。；;]{0,12}$',prefix):
            candidates.append(match)
    if len(candidates)!=1:
        raise ValueError('检测到年份范围，但无法确定需要保留的区间，请明确筛选条件。')
    match=candidates[0]
    start,end=map(int,match.groups())
    if start>end: raise ValueError('年份起点不能晚于终点。')
    field=proposed.get('field') if isinstance(proposed,dict) and proposed.get('field') else 'year'
    return {'field':field,'start':start,'end':end}


def merge_preparation_request(text, selected_ids):
    if len(set(selected_ids)) < 2:
        return False
    lower=text.casefold()
    if re.search(r'合并后(?:的(?:数据|结果|样本|主分析集))?(?:做|进行|开展|分析|回归|统计)', lower):
        return False
    return bool(re.search(r'合并|整合|\bmerge\b', lower))


def preview_only_request(text):
    text=text.casefold()
    if re.search(r'(?:不|别|暂不|不要|无需|不需要).{0,8}(?:执行|合并|挂载|生成)',text): return True
    if re.search(r'(?:只|仅|单独).{0,6}(?:预检|检查|查看|展示|给出|生成方案)',text): return True
    asks_execution=re.search(r'(?:再|然后|通过后|之后).{0,8}(?:执行|合并|挂载)',text)
    if re.search(r'先.{0,4}(?:预检|检查|查看)',text) and not asks_execution: return True
    if re.search(r'(?:合并|整合).{0,5}预检',text) and not asks_execution and not re.search(r'(?:执行|挂载)',text): return True
    return False


def preview_message(details):
    keys='、'.join(details['keys'])
    if not details['ok']:
        return f'合并预检未通过（键：{keys}）。请在数据整合页面查看错误并调整方案；尚未执行合并，也未挂载新数据。'
    metrics=details['metrics']; lines=[f'合并预检通过，合并键：{keys}，关系：{details["cardinality"]}。']
    if details.get('year_filter'):
        f=details['year_filter'];lines.append(f"- 年份筛选：{f['field']}，{f['start'] if f['start'] is not None else '不限'} 至 {f['end'] if f['end'] is not None else '不限'}（含端点）")
    if 'YEAR_FILTER_DROPPED' in metrics: lines.append(f"- 年份筛选剔除：{metrics['YEAR_FILTER_DROPPED']:,} 行")
    for key,label in [('FINAL_BEFORE_MISSING','删除缺失前的匹配行'),('ANALYSIS_MISSING_ROWS','因缺失删除的行'),('FINAL_ROWS','预计最终行')]:
        if key in metrics: lines.append(f'- {label}：{metrics[key]:,}')
    lines.append('本次仅预检，尚未正式合并或挂载。')
    return '\n'.join(lines)
