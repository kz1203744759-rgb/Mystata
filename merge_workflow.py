"""Route explicit multi-file merge tasks through the verified ETL workflow."""
import re


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
    for key,label in [('FINAL_BEFORE_MISSING','删除缺失前的匹配行'),('ANALYSIS_MISSING_ROWS','因缺失删除的行'),('FINAL_ROWS','预计最终行')]:
        if key in metrics: lines.append(f'- {label}：{metrics[key]:,}')
    lines.append('本次仅预检，尚未正式合并或挂载。')
    return '\n'.join(lines)
