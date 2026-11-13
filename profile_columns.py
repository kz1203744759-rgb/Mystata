"""Read-only profiles of uploaded data; duplicate checks require a user request."""
from pathlib import Path
import math
import re
import pandas as pd
from pandas.io.stata import StataMissingValue

ROLES={'stock_code','year','province','city','district','other'}
ALIASES={
    'stock_code':{'stkcd','stockcode','stock_code','证券代码','股票代码','公司代码','企业代码'},
    'year':{'year','年份','年度','会计年度','报告年度'},
    'province':{'province','省','省份','省名称'},
    'city':{'city','市','城市','市名称'},
    'district':{'district','区','区县','区名称'},
}


def dta_header(path):
    """Read the Stata file header without loading observations or modifying Stata."""
    codes={'b':'byte','h':'int','l':'long','f':'float','d':'double','Q':'strL'}
    with pd.io.stata.StataReader(path,convert_categoricals=False) as reader:
        labels=reader.variable_labels()  # Ensures the header is read.
        names=reader._varlist
        types=reader._typlist
        formats=reader._fmtlist
        if not (len(names)==len(types)==len(formats)):
            raise ValueError('Stata 文件头变量信息不完整。')
        columns=[]
        for name,kind,fmt in zip(names,types,formats):
            storage=f'str{kind}' if isinstance(kind,int) else codes.get(kind)
            if not storage:raise ValueError(f'不支持的 Stata 存储类型：{kind}')
            columns.append({'name':str(name),'type':storage,'storage_type':storage,
                            'display_format':str(fmt or ''),'label':str(labels.get(name,'') or ''),
                            'candidate_role':candidate_role(name)})
        return {'observations':int(reader._nobs),'columns':columns}


def candidate_role(name):
    key=str(name).strip().lower().replace(' ','_')
    return next((role for role,names in ALIASES.items() if key in names),None)


def user_requested_duplicates(message, columns, roles):
    """Require a positive, explicit request and identified columns in this turn."""
    text=message.casefold()
    without_id_label=text.replace('唯一标识','标识')
    positive=(re.search(r'重复|去重|查重|duplicat|\bisid\b|\bunique\b',text) or
              re.search(r'(?:是否|能否|检查|检验|核对|验证|判断|确认)[^，,。；;！!\n]{0,60}唯一',without_id_label) or
              re.search(r'唯一(?:的)?键(?:吗|么|\?|？)',without_id_label))
    if not positive:return False
    if re.search(r'(?:不要|不用|不必|不需要|无需|禁止|别|暂不|无须|不)\s*(?:检查|查看|统计|检测|做|进行)[^，,。；;！!\n]{0,80}(?:重复|查重|去重|唯一|duplicat|\bisid\b|\bunique\b)',text):
        return False
    if re.search(r'(?:不要|不用|不必|不需要|无需|禁止|别|暂不|无须)\s*(?:查重|去重|重复)',text):
        return False
    if re.search(r"(?:do not|don't|never|without)\s+(?:check|detect|test|look for)?[^,.!;\n]{0,80}(?:duplicat|\bunique\b)",text):
        return False
    named={}
    for item in roles:
        named[(item['file_id'],item['column'])]=item['role']
    semantic={'stock_code':r'证券代码|股票代码|公司代码|企业代码',
              'year':r'年份|年度|会计年度|报告年度',
              'province':r'省份|省名称', 'city':r'城市|市名称', 'district':r'区县|区名称'}
    for check in columns:
        for name in check['columns']:
            escaped=re.escape(name.casefold())
            pattern=(r'(?<![a-z0-9_])'+escaped+r'(?![a-z0-9_])') if re.fullmatch(r'[a-z0-9_]+',name.casefold()) else escaped
            role=named.get((check['file_id'],name)) or candidate_role(name)
            if not re.search(pattern,text) and not (role in semantic and re.search(semantic[role],text)):
                return False
    return True


def read_frame(path):
    path=Path(path)
    if path.suffix.lower()=='.dta': frame=pd.read_stata(path,convert_categoricals=False,convert_missing=True)
    elif path.suffix.lower()=='.csv': frame=pd.read_csv(path,dtype=str,encoding='utf-8-sig',keep_default_na=False)
    elif path.suffix.lower()=='.xlsx': frame=pd.read_excel(path,dtype=object,sheet_name=0)
    else: raise ValueError('不支持的原始文件格式。')
    frame.columns=frame.columns.map(str)
    return frame


def _usable_values(series):
    # Exclude empty/null cells solely while assessing formats; do not compute or report missingness.
    return series[series.map(lambda v:not isinstance(v,StataMissingValue) and pd.notna(v) and str(v).strip() not in {'','.'})]


def format_profile(series,role):
    values=_usable_values(series)
    result={'role':role,'basis':'由用户或模型指定，字段含义仍需结合数据说明核实。'}
    if role in {'stock_code','year'}:
        text=values.astype(str).str.strip()
        numbers=pd.to_numeric(text,errors='coerce')
        valid=numbers.notna()
        fractional=valid & ((numbers % 1)!=0)
        lower,upper=(0,2147483620) if role=='stock_code' else (1000,9999)
        outside=valid & ~numbers.between(lower,upper)
        result.update(non_numeric=int((~valid).sum()),non_integer=int(fractional.sum()),out_of_range=int(outside.sum()),
                      suggested_rule='转 Stata long，必要时六位显示' if role=='stock_code' else '转 Stata float 年份')
        if role=='stock_code':
            result['leading_zero_strings']=int(text.str.match(r'^0+\d+$').sum())
        if role=='year' and int((~valid).sum()+outside.sum())>0:
            result['note']='可能包含日期或其他格式；不得自行猜测日期口径。'
    elif role in {'province','city','district'}:
        text=values.astype(str)
        normalized=text.str.replace(r'[　 ]+',' ',regex=True).str.strip()
        non_strings=int(values.map(lambda value:not isinstance(value,str)).sum())
        result.update(space_variants=int((text!=normalized).sum()),non_string_values=non_strings,
                      suggested_rule='检查首尾、连续及全角空格；地区别名或行政区划须另行核实')
        if non_strings:result['note']='含非字符串值，可能是地区编码；应先核实编码体系，不自动转为地区名称。'
    return result


def _key_value(value):
    if isinstance(value,StataMissingValue): return ('stata_missing',str(value))
    if pd.isna(value): return ('null',None)
    return ('value',value)


def _sample_value(value):
    if isinstance(value,StataMissingValue):return str(value)
    if pd.isna(value):return None
    if hasattr(value,'isoformat'):return value.isoformat()
    if hasattr(value,'item'):value=value.item()
    if isinstance(value,float) and not math.isfinite(value):return str(value)
    if isinstance(value,str) and len(value)>100:return value[:100]+'…'
    return value if isinstance(value,(str,int,float,bool)) else str(value)


def duplicate_profile(frame,columns):
    # Type-tag values so Stata extended missing codes do not collapse or collide with strings.
    keys=pd.DataFrame({col:frame[col].map(_key_value) for col in columns})
    duplicate=keys.duplicated(keep=False)
    rows=int(duplicate.sum())
    unique=keys.loc[duplicate].drop_duplicates()
    groups=int(len(unique))
    examples=[{col:_sample_value(frame.loc[index,col]) for col in columns} for index in unique.head(5).index]
    return {'columns':columns,'duplicate_groups':groups,'rows_in_duplicate_groups':rows,
            'surplus_rows':rows-groups,'examples':examples,'scope':'全量原始字段值；未标准化、未删除记录',
            'equality_note':'按原始字段值精确比较；空值参与比较，未进行空值统计。'}


def profile_files(files, file_ids, roles, checks, offset, page_size, message):
    if not file_ids or len(file_ids)>20 or len(file_ids)!=len(set(file_ids)):
        raise ValueError('请选择 1 至 20 个不同的原始文件。')
    if any(fid not in files for fid in file_ids):raise ValueError('文件不存在，请重新选择。')
    if not isinstance(offset,int) or isinstance(offset,bool) or offset<0 or not isinstance(page_size,int) or isinstance(page_size,bool) or not 1<=page_size<=30:
        raise ValueError('字段分页参数无效。')
    by_id={fid:{v['name']:v for v in files[fid].get('variables',[])} for fid in file_ids}
    seen=set()
    for item in roles:
        fid,name,role=item.get('file_id'),item.get('column'),item.get('role')
        if fid not in by_id or name not in by_id[fid] or role not in ROLES:raise ValueError('字段角色无效，请先核对字段目录。')
        if (fid,name) in seen:raise ValueError('同一文件字段不能设置多个角色。')
        seen.add((fid,name))
    check_ids=set()
    for check in checks:
        fid,columns=check.get('file_id'),check.get('columns')
        if fid not in by_id or not isinstance(columns,list) or not columns or len(columns)>30 or len(columns)!=len(set(columns)) or any(c not in by_id[fid] for c in columns):
            raise ValueError('重复检查需要指定存在的字段组合。')
        if fid in check_ids:raise ValueError('每个文件每次只能指定一个重复字段组合。')
        check_ids.add(fid)
    duplicates_allowed=bool(checks) and user_requested_duplicates(message,checks,roles)
    results=[]
    for fid in file_ids:
        entry=files[fid];variables=entry.get('variables',[])
        observations=entry.get('observations')
        if entry.get('format')=='dta':
            header=dta_header(entry['path'])
            if [v['name'] for v in variables] != [v['name'] for v in header['columns']]:
                raise ValueError(f'{entry["filename"]} 的字段与上传目录不一致，请重新上传后检查。')
            variables=header['columns']
            observations=header['observations']
        page=variables[offset:offset+page_size]
        file_roles=[r for r in roles if r['file_id']==fid and r['role']!='other']
        wanted_checks=[c for c in checks if c['file_id']==fid] if duplicates_allowed else []
        record={'file_id':fid,'file':entry['filename'],'format':entry.get('format'),
                'observations':observations,'column_count':len(variables),
                'columns':[{'name':v['name'],'type':v.get('type',''),'label':v.get('label',''),
                            'storage_type':v.get('storage_type'),'display_format':v.get('display_format'),
                            'candidate_role':candidate_role(v['name'])} for v in page],
                'offset':offset,'next_offset':offset+len(page) if offset+len(page)<len(variables) else None}
        if file_roles or wanted_checks:
            frame=read_frame(entry['path'])
            if list(map(str,frame.columns)) != [v['name'] for v in variables]:
                raise ValueError(f'{entry["filename"]} 的字段与上传目录不一致，请重新上传后检查。')
            record['format_profiles']=[{'column':r['column'],**format_profile(frame[r['column']],r['role'])} for r in file_roles]
            if wanted_checks:record['duplicate_check']=duplicate_profile(frame,wanted_checks[0]['columns'])
        results.append(record)
    answer={'files':results,'note':'只读检查，不统计缺失值；.dta 的存储类型和显示格式读取自文件头。CSV 和 Excel 的 Stata 格式需导入后确认。'}
    if checks and not duplicates_allowed:
        answer['duplicate_request_status']='未执行重复检查：请在当前对话明确要求并指出具体字段。'
    return answer
