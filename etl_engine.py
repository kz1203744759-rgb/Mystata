"""Validate a confirmed multi-file plan and compile reproducible Stata code."""
import re
from pathlib import Path

IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,31}$')
RESERVED = {'_all','_n','_N','_b','_se','_cons','if','in','using','_merge'}


def validate_plan(plan, files):
    ids = plan['file_ids']
    if len(ids) < 2 or len(ids) != len(set(ids)):
        raise ValueError('请选择至少两个不同的原始文件。')
    if any(fid not in files for fid in ids):
        raise ValueError('原始文件不存在或已移除，请重新选择。')
    if plan['mode'] not in {'merge', 'append'}:
        raise ValueError('不支持的整合方式。')
    if plan['mode'] == 'merge' and plan['cardinality'] not in {'1:1','m:1','1:m'}:
        raise ValueError('请选择合法的合并关系。')
    if plan.get('conflict_policy','stop') not in {'stop','master','using'}:
        raise ValueError('不支持的冲突处理方式。')
    if plan.get('sample_retention','matched') not in {'matched','master','all'}:
        raise ValueError('不支持的样本保留方式。')
    rows = [row for row in plan['mappings'] if row['keep']]
    if not rows: raise ValueError('请至少保留一个字段。')
    names, used = set(), {fid:set() for fid in ids}
    for row in rows:
        name = row['target']
        if not IDENTIFIER.fullmatch(name) or name in RESERVED:
            raise ValueError(f'目标字段名 {name!r} 无效：请使用不超过 32 位的英文字母、数字或下划线，且不能以数字开头。')
        if name.lower() in names: raise ValueError(f'目标字段 {name} 重复。')
        names.add(name.lower())
        if row['convert'] not in {'none','numeric','string'}: raise ValueError('不支持的类型转换。')
        if row.get('normalize', 'none') not in {'none','stock','year','date_ymd','date_mdy','date_dmy','date_stata','region'}:
            raise ValueError('不支持的标准化规则。')
        if row.get('normalize', 'none') != 'none' and row['convert'] != 'none':
            raise ValueError(f'字段 {name} 已选择标准化规则，请将类型转换设为保持原类型。')
        present = False
        for fid in ids:
            index = row['sources'].get(fid)
            if index is None: continue
            if isinstance(index, bool) or not isinstance(index, int) or index < 0 or index >= len(files[fid]['variables']):
                raise ValueError(f'{name} 的源字段无效。')
            if index in used[fid]: raise ValueError(f'文件 {files[fid]["filename"]} 的同一个字段被映射多次。')
            used[fid].add(index)
            present = True
        if not present: raise ValueError(f'目标字段 {name} 未选择任何来源。')
    if plan['mode'] == 'merge':
        if not plan['keys'] or len(plan['keys']) != len(set(plan['keys'])):
            raise ValueError('合并需要至少一个不重复的主键。')
        lookup = {row['target']:row for row in rows}
        for key in plan['keys']:
            if key not in lookup: raise ValueError(f'主键 {key} 不在保留字段中。')
            if any(lookup[key]['sources'].get(fid) is None for fid in ids):
                raise ValueError(f'主键 {key} 在每个文件中都需要指定来源字段。')
    if any(name not in names for name in [x.lower() for x in plan.get('drop_missing', [])]):
        raise ValueError('缺失值检查字段必须是保留的目标字段。')
    year_filter=plan.get('year_filter')
    if year_filter is not None:
        if not isinstance(year_filter,dict) or set(year_filter)!={'field','start','end'}: raise ValueError('年份筛选格式无效。')
        field=year_filter['field']; start=year_filter['start']; end=year_filter['end']
        if not isinstance(field,str) or field not in {row['target'] for row in rows}: raise ValueError('年份筛选字段必须是保留的目标字段。')
        if any(v is not None and (type(v) is not int or v < 1000 or v > 9999) for v in (start,end)) or (start is None and end is None) or (start is not None and end is not None and start>end):
            raise ValueError('请输入有效的年份起止范围。')
    for fid in ids:
        if not used[fid]: raise ValueError(f'文件 {files[fid]["filename"]} 未映射任何字段。')
    return rows


def load_command(path):
    path = Path(path)
    filename = path.as_posix()
    if '"' in filename or '\n' in filename or '\r' in filename: raise ValueError('文件路径不受支持。')
    if path.suffix.lower() == '.dta': return f'use "{filename}", clear'
    if path.suffix.lower() == '.csv': return f'import delimited using "{filename}", clear varnames(1) stringcols(_all) encoding(utf8)'
    if path.suffix.lower() == '.xlsx': return f'import excel using "{filename}", firstrow clear'
    raise ValueError('不支持的文件类型。')


def compile_plan(plan, files, directory, output, token, preview=False, readable=False):
    rows = validate_plan(plan, files)
    directory, output = Path(directory), Path(output)
    frame = 'etlf' + token[:12]
    prefix = 'e' + token[:10] + '_'
    aliases=[]
    if readable:
        occupied={str(v['name']).lower() for f in files.values() for v in f.get('variables',[])} | {r['target'].lower() for r in rows}
        n=0
        while True:
            prefix='etl_' if n==0 else f'etl{n}_'
            if not any(name.startswith(prefix) for name in occupied):break
            n+=1
        lines=['* 可读复现脚本：基于已执行的整合方案生成，本版本未单独运行。',
               '* 源文件和输出路径可根据需要修改；运行会生成新的结果文件。']
        used_aliases=set()
        for i,fid in enumerate(plan['file_ids'],1):
            safe_name=str(files[fid]['filename']).replace('\n',' ').replace('\r',' ')
            path=Path(files[fid]['path']).as_posix()
            stem=re.sub(r'[^a-z0-9]+','_',Path(safe_name).stem.lower()).strip('_')[:18] or str(i)
            alias=stem; suffix=2
            while alias in used_aliases:
                alias=f'{stem[:15]}_{suffix}';suffix+=1
            used_aliases.add(alias);aliases.append(alias)
            lines += [f'* 文件 {i}：{safe_name}',f'local source_{alias} "{path}"']
        lines += ['* 复现结果：不会覆盖原来的主分析集',f'local result_file "{output.as_posix()}"']
        lines += ['','tempfile '+' '.join(f'clean_{alias}' for alias in aliases),
                  'tempname etl_frame',"frame create `etl_frame'","frame change `etl_frame'"]
    else:
        lines = ['* Confirmed ETL plan: original files are not modified.',
                 f'frame create {frame}', f'frame change {frame}']
    intermediates = []
    for file_no, fid in enumerate(plan['file_ids']):
        selected = [(row, row['sources'].get(fid)) for row in rows if row['sources'].get(fid) is not None]
        load=load_command(files[fid]['path'])
        if readable:
            path=Path(files[fid]['path']).as_posix()
            load=load.replace(f'"{path}"',f'"`source_{aliases[file_no]}\'"',1)
        lines += ['', f'* {"处理文件" if readable else "Source"} {file_no + 1}', load]
        src_names=[str(files[fid]['variables'][index]['name']) for _,index in selected]
        source_set={name.lower() for name in src_names}
        direct=(readable and Path(files[fid]['path']).suffix.lower()=='.dta'
                and all(IDENTIFIER.fullmatch(name) for name in src_names)
                and len(source_set)==len(src_names)
                and all(row['target'].lower()==src.lower() or row['target'].lower() not in source_set for (row,_),src in zip(selected,src_names)))
        if direct:
            lines.append('keep '+' '.join(src_names))
            for (row,_),src in zip(selected,src_names):
                if src!=row['target']: lines.append(f"rename {src} {row['target']}")
        else:
            if readable: lines.append('* 导入字段名或重命名存在冲突，按列定位以保持原方案。')
            lines.append('unab etl_original : _all')
            for i, (row, index) in enumerate(selected):
                tmp = f'{prefix}{i+1}'
                if readable:
                    original=src_names[i].replace('\n',' ').replace('\r',' ')
                    lines.append(f"* 第 {index+1} 列 {original} → {row['target']}")
                lines += [f"local etl_var : word {index+1} of `etl_original'", f"rename `etl_var' {tmp}"]
            lines.append('keep ' + ' '.join(f'{prefix}{i+1}' for i in range(len(selected))))
        for i, (row, _) in enumerate(selected):
            target = row['target']
            if not direct: lines.append(f'rename {prefix}{i+1} {target}')
            if row['convert'] == 'numeric':
                lines += [f'capture confirm numeric variable {target}', 'if _rc {', f'    destring {target}, replace', f'    confirm numeric variable {target}', '}']
            elif row['convert'] == 'string':
                lines += [f'capture confirm string variable {target}', 'if _rc {', f'    tostring {target}, replace format(%21.0g)', f'    confirm string variable {target}', '}']
            rule = row.get('normalize', 'none')
            if rule in {'stock', 'year'}:
                lines += [f'capture confirm string variable {target}', 'if !_rc {', f'    replace {target} = ustrtrim({target})', f'    destring {target}, replace', '}',
                          f'assert {target} == floor({target}) if !missing({target})']
                if rule == 'stock':
                    lines += [f'assert inrange({target}, 0, 2147483620) if !missing({target})', f'recast long {target}', f'format {target} %06.0f']
                else:
                    lines += [f'assert inrange({target}, 1000, 9999) if !missing({target})', f'recast float {target}', f'format {target} %9.0g']
            elif rule in {'date_ymd','date_mdy','date_dmy'}:
                mask = {'date_ymd':'YMD','date_mdy':'MDY','date_dmy':'DMY'}[rule]
                tmpyear = f'{prefix}date'
                lines += [f'confirm string variable {target}', f'generate double {tmpyear} = daily(ustrtrim({target}), "{mask}")',
                          f'assert !missing({tmpyear}) if !missing(ustrtrim({target}))', f'drop {target}',
                          f'generate float {target} = year({tmpyear})', f'drop {tmpyear}']
            elif rule == 'date_stata':
                lines += [f'confirm numeric variable {target}', f'replace {target} = year({target}) if !missing({target})', f'recast float {target}', f'format {target} %9.0g']
            elif rule == 'region':
                before = f'{prefix}before'
                lines += [f'confirm string variable {target}', f'clonevar {before} = {target}',
                          f'replace {target} = ustrtrim(ustrregexra({target}, "[　 ]+", " "))',
                          f'quietly count if {before} != {target}', f'display "ETL_REGION_{file_no+1}_{target}=" r(N)',
                          f'list {before} {target} if {before} != {target} & _n <= 100, noobs', f'drop {before}']
        if plan['mode'] == 'merge' and plan.get('drop_missing_keys', False):
            missing = ' | '.join(f'missing({key})' for key in plan['keys'])
            lines += [f'quietly count if {missing}', f'display "ETL_SOURCE_{file_no+1}_MISSING_KEYS=" r(N)', f'drop if {missing}']
        if plan['mode'] == 'merge':
            tag = f'{prefix}dup'
            lines += [f'quietly duplicates tag {" ".join(plan["keys"])}, generate({tag})', f'quietly count if {tag} > 0',
                      f'display "ETL_SOURCE_{file_no+1}_DUPLICATE_ROWS=" r(N)', f'drop {tag}']
        tmpfile = f"`clean_{aliases[file_no]}'" if readable else (directory / f'etl-source-{file_no+1}.dta').as_posix()
        intermediates.append(tmpfile)
        lines.append(f'save "{tmpfile}", replace')
    lines += ['', '* Combine prepared files', f'use "{intermediates[0]}", clear']
    for index, path in enumerate(intermediates[1:], 1):
        if plan['mode'] == 'append':
            lines.append(f'append using "{path}"')
        else:
            flag = f'{prefix}m{index}'
            if preview:
                earlier = set(plan['file_ids'][:index])
                later = plan['file_ids'][index]
                overlaps = [row['target'] for row in rows if row['target'] not in plan['keys']
                            and row['sources'].get(later) is not None
                            and any(row['sources'].get(fid) is not None for fid in earlier)]
                if overlaps:
                    diagpath = (directory / f'etl-diagnostic-{index}.dta').as_posix()
                    aliases = [f'{prefix}d{i}' for i in range(len(overlaps))]
                    lines += ['preserve', f'use "{path}", clear']
                    lines += [f'rename {name} {alias}' for name,alias in zip(overlaps,aliases)]
                    lines += [f'keep {" ".join(plan["keys"]+aliases)}', f'save "{diagpath}", replace', 'restore', 'preserve',
                              f'merge {plan["cardinality"]} {" ".join(plan["keys"])} using "{diagpath}", keep(match) nogen']
                    for name,alias in zip(overlaps,aliases):
                        condition=f'!missing({name}) & !missing({alias}) & {name} != {alias}'
                        tag=f'{prefix}conflict'
                        lines += [f'generate byte {tag} = ({condition})', f'quietly count if {tag}',
                                  f'display "ETL_FIELD_{index}_{name}=" r(N)', f'gsort -{tag}',
                                  f'list {" ".join(plan["keys"])} {name} {alias} if {tag} & _n <= 5, noobs', f'drop {tag}']
                    lines.append('restore')
            replace = ' replace' if plan.get('conflict_policy','stop') == 'using' else ''
            lines += [f'merge {plan["cardinality"]} {" ".join(plan["keys"])} using "{path}", update{replace} generate({flag})',
                      f'quietly count if {flag} == 1', f'display "ETL_MERGE_{index}_MASTER_ONLY=" r(N)',
                      f'quietly count if {flag} == 2', f'display "ETL_MERGE_{index}_USING_ONLY=" r(N)',
                      f'quietly count if inlist({flag}, 3, 4, 5)', f'display "ETL_MERGE_{index}_MATCHED=" r(N)',
                      f'quietly count if {flag} == 5', f'display "ETL_MERGE_{index}_CONFLICTS=" r(N)']
            if plan.get('conflict_policy','stop') == 'stop': lines.append(f'assert {flag} != 5')
            lines += [f'tabulate {flag}']
            retention=plan.get('sample_retention','matched')
            if retention=='matched': lines.append(f'keep if inlist({flag}, 3, 4, 5)')
            elif retention=='master': lines.append(f'keep if {flag} != 2')
            lines.append(f'drop {flag}')
    year_filter=plan.get('year_filter')
    if year_filter:
        field=year_filter['field']; start=year_filter['start']; end=year_filter['end']
        conditions=[f'missing({field})']
        if start is not None: conditions.append(f'{field} < {start}')
        if end is not None: conditions.append(f'{field} > {end}')
        rejected=' | '.join(conditions)
        lines += ['', '* 按用户指定的年份范围筛选', f'confirm numeric variable {field}',
                  f'quietly count if {rejected}', 'display "ETL_YEAR_FILTER_DROPPED=" r(N)',
                  f'drop if {rejected}']
        if start is not None: lines.append(f'assert {field} >= {start} if !missing({field})')
        if end is not None: lines.append(f'assert {field} <= {end} if !missing({field})')
        lines.append('display "ETL_AFTER_YEAR_FILTER=" _N')
    if plan['mode']=='merge':lines += ['display "ETL_FINAL_BEFORE_MISSING=" _N']
    missing_fields=([row['target'] for row in rows] if plan['mode']=='merge' and plan.get('drop_all_missing',True)
                    else plan.get('drop_missing',[]))
    if missing_fields:
        flag=f'{prefix}missing'
        lines += [f'generate byte {flag} = 0']
        lines += [f'quietly replace {flag} = 1 if missing({name})' for name in missing_fields]
        lines += [f'quietly count if {flag}', 'display "ETL_ANALYSIS_MISSING_ROWS=" r(N)',
                  f'drop if {flag}', f'drop {flag}']
    if plan['mode']=='merge':lines += ['display "ETL_FINAL_ROWS=" _N']
    result_path="`result_file'" if readable else output.as_posix()
    lines += ['', f'save "{result_path}", replace', 'describe', 'display "ETL_COMPLETED"']
    return '\n'.join(lines) + '\n', frame
