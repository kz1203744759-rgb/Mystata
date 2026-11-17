"""Recoverable, file-level undo for DTA column operations in the workspace."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from uuid import uuid4

from workspace_cleanup import _reparse


class MutationUncertain(RuntimeError):
    """The file changed but recording the action did not complete."""


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''): h.update(block)
    return h.hexdigest()


def checked_target(root, value):
    root=Path(root).resolve(strict=True)
    path=Path(value)
    if not path.is_absolute() or path.suffix.lower()!='.dta': raise ValueError('只支持工作台内的 DTA 文件。')
    target=path.resolve(strict=True)
    if not target.is_relative_to(root) or not any(target.is_relative_to((root/n).resolve()) for n in ('runs','datasets')):
        raise ValueError('目标文件不在工作台数据目录中。')
    current=path
    while current != root:
        if _reparse(current): raise ValueError('文件路径包含链接或重解析点。')
        if current.parent==current: raise ValueError('文件路径无效。')
        current=current.parent
    if not target.is_file(): raise ValueError('目标文件不存在。')
    return target


def validate_columns(existing, requested):
    if not isinstance(requested,list) or not requested or len(requested)>100:
        raise ValueError('请明确指定要删除的字段。')
    if any(not isinstance(x,str) or not x or not x.isidentifier() for x in requested):
        raise ValueError('字段名无效。')
    if len(set(requested)) != len(requested): raise ValueError('字段名称不能重复。')
    if any(x not in existing for x in requested): raise ValueError('字段不存在或大小写不一致，请核对字段目录。')
    if len(requested)>=len(existing): raise ValueError('不能删除所有字段。')
    return requested


def columns_to_drop(existing, requested, mode):
    if mode=='drop':return validate_columns(existing,requested)
    if mode!='keep' or not isinstance(requested,list) or not requested or len(requested)>100:
        raise ValueError('请明确指定需要保留的字段。')
    if any(not isinstance(x,str) or not x or not x.isidentifier() for x in requested):raise ValueError('字段名无效。')
    if len(set(requested))!=len(requested):raise ValueError('字段名称不能重复。')
    if any(x not in existing for x in requested):raise ValueError('需要保留的字段不存在或大小写不一致。')
    keep=set(requested)
    return [name for name in existing if name not in keep]


def _write_record(path, record):
    temp=path.with_name('record.tmp')
    with temp.open('w',encoding='utf8',newline='\n') as f:
        json.dump(record,f,ensure_ascii=False,indent=2)
        f.flush();os.fsync(f.fileno())
    os.replace(temp,path)


def create_backup(root, target, columns):
    target=checked_target(root,target)
    before=digest(target)
    parent=Path(root)/'runs'/'field-undo'
    parent.mkdir(parents=True,exist_ok=True)
    if _reparse(parent) or not parent.resolve().is_relative_to(Path(root).resolve()): raise ValueError('回滚目录不安全。')
    ident=uuid4().hex; directory=parent/ident;directory.mkdir()
    backup=directory/'before.dta'
    with target.open('rb') as src,backup.open('xb') as dst:
        shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
    if digest(backup)!=before or digest(target)!=before: raise ValueError('备份期间文件已变化，未修改原文件。')
    return {'id':ident,'time_ns':time.time_ns(),'path':str(target),'before_sha256':before,
            'columns':columns,'status':'backed_up'},directory


def commit_drop(root,target,candidate,record,directory):
    target=checked_target(root,target);candidate=Path(candidate)
    if candidate.parent.resolve()!=target.parent or not candidate.is_file() or _reparse(candidate): raise ValueError('临时数据文件无效。')
    if digest(target)!=record['before_sha256']: raise ValueError('文件已被其他操作修改，未执行删除。')
    record.update(after_sha256=digest(candidate),status='prepared')
    _write_record(directory/'record.json',record)
    os.replace(candidate,target)
    record['status']='applied'
    try:_write_record(directory/'record.json',record)
    except OSError as exc:raise MutationUncertain('文件已修改，但操作记录写入失败；请检查文件和备份后再继续。') from exc
    return record


def latest(root,target):
    target=checked_target(root,target);parent=Path(root)/'runs'/'field-undo'
    if not parent.is_dir(): raise ValueError('这个文件没有可回滚的删列记录。')
    if _reparse(parent) or not parent.resolve().is_relative_to(Path(root).resolve()): raise ValueError('回滚目录不安全。')
    records=[]
    for directory in parent.iterdir():
        if not directory.is_dir() or _reparse(directory):continue
        try:
            path=directory/'record.json'
            if _reparse(path) or path.stat().st_size>65536:continue
            item=json.loads(path.read_text(encoding='utf8'))
            if item.get('path')==str(target) and item.get('status') in ('applied','prepared'):
                records.append((int(item['time_ns']),directory,item))
        except (OSError,ValueError,KeyError,TypeError):continue
    current=digest(target)
    for _,directory,item in sorted(records,reverse=True,key=lambda x:x[0]):
        if item['status']=='prepared' and current==item.get('before_sha256'): continue
        if current!=item.get('after_sha256'):
            raise ValueError('文件在删列后发生其他修改，无法安全回滚；请先检查文件。')
        backup=directory/'before.dta'
        if not backup.is_file() or _reparse(backup) or digest(backup)!=item.get('before_sha256'):
            raise ValueError('回滚备份不存在或校验失败。')
        return directory,item,backup
    raise ValueError('这个文件没有可回滚的删列记录。')


def undo(root,target):
    target=checked_target(root,target);directory,record,backup=latest(root,target)
    temp=target.parent/('.field-restore-'+uuid4().hex+'.dta')
    try:
        with backup.open('rb') as src,temp.open('xb') as dst:
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        if digest(temp)!=record['before_sha256'] or digest(target)!=record['after_sha256']:
            raise ValueError('文件在回滚期间发生变化，未执行回滚。')
        os.replace(temp,target)
        record['status']='undone'
        try:_write_record(directory/'record.json',record)
        except OSError as exc:raise MutationUncertain('文件已回滚，但操作记录写入失败；请检查文件和备份后再继续。') from exc
        return record
    finally:
        if temp.exists():temp.unlink()
