"""Generate reviewable Stata scripts without changing the executed code."""
from pathlib import Path
from etl_engine import compile_plan


def readable_etl(plan, files, directory, token):
    directory=Path(directory)
    code,_=compile_plan(plan,files,directory,directory/'reproduced.dta',token,readable=True)
    return code


def readable_step(code, raw_index, success):
    lines=['* 可读脚本：与本次发送给 Stata 的分析代码一致。',
           '* 此步骤可能依赖此前步骤的 Stata 内存数据、变量或估计结果。',
           '* 本次执行状态：'+('成功' if success else '失败；请检查日志后修正。')]
    body=code
    for item in raw_index:
        macro=item['stata_macro']
        path=Path(item['path']).as_posix()
        name=str(item['file']).replace('\r',' ').replace('\n',' ')
        used=f"`{macro}'" in body
        literal=f'"{path}"'
        if used or literal in body:
            lines.append(f'* 原始文件：{name}')
        if used:
            lines.append(f'local {macro} "{path}"')
    return '\n'.join(lines)+'\n\n'+body.rstrip()+'\n'
