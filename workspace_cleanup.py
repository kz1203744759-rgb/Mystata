"""Delete only this workspace's uploaded data and generated run files."""
import argparse
import json
import os
from pathlib import Path
import re
import stat

TARGETS=('runs','datasets','.stata-tmp')
SNAPSHOT=re.compile(r'^upgrade-session-[0-9a-f]{32}\.json$')


def _reparse(path):
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400))


def _checked_path(path,root):
    if _reparse(path):raise ValueError(f'清理目录包含链接或重解析点：{path}')
    resolved=path.resolve(strict=True)
    if not resolved.is_relative_to(root):raise ValueError(f'清理路径超出项目目录：{path}')
    return resolved


def _snapshot(root,value):
    if not value:return None
    path=Path(value)
    try:
        if _reparse(path):raise ValueError('snapshot link')
        path=path.resolve(strict=True)
        runs=(root/'runs').resolve(strict=True)
        if path.parent!=runs or not SNAPSHOT.fullmatch(path.name):raise ValueError('snapshot path')
        if path.stat().st_size>10*1024*1024:raise ValueError('snapshot size')
        saved=json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(saved,dict):raise ValueError('snapshot data')
        if not isinstance(saved.get('messages'),list):raise ValueError('snapshot data')
        saved.update(dataset=None,active_path=None,events=[],artifacts=[])
        return path,saved
    except (OSError,ValueError,TypeError):
        return None


def cleanup_project(project, *, preserve_snapshot=None):
    """Preflight all targets, then unlink files and remove empty subdirectories."""
    root=Path(project)
    if not root.is_absolute() or not root.is_dir() or _reparse(root):raise ValueError('项目目录无效或为链接。')
    root=root.resolve(strict=True)
    snapshot=_snapshot(root,preserve_snapshot) if preserve_snapshot else None
    preserved=snapshot[0] if snapshot else None
    files=[];directories=[]
    for name in TARGETS:
        target=root/name
        if not target.exists() and not target.is_symlink():continue
        _checked_path(target,root)
        if not target.is_dir():raise ValueError(f'预期的清理目录不是文件夹：{target}')
        stack=[target]
        while stack:
            directory=stack.pop()
            _checked_path(directory,root)
            for entry in directory.iterdir():
                checked=_checked_path(entry,root)
                if entry.is_dir():
                    stack.append(entry);directories.append(entry)
                elif entry.is_file():
                    if checked!=preserved:files.append(entry)
                else:raise ValueError(f'不支持清理的文件类型：{entry}')
    if snapshot:
        _checked_path(snapshot[0],root)
        snapshot[0].write_text(json.dumps(snapshot[1],ensure_ascii=False),encoding='utf-8')
    removed=0
    for path in files:
        # Recheck containment and links immediately before mutation.
        _checked_path(path,root)
        path.unlink()
        removed+=1
    for directory in sorted(directories,key=lambda p:len(p.parts),reverse=True):
        _checked_path(directory,root)
        try:directory.rmdir()
        except OSError:
            if not any(directory.iterdir()):raise
    return {'removed_files':removed}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--project-dir',required=True)
    parser.add_argument('--startup',action='store_true')
    args=parser.parse_args()
    result=cleanup_project(args.project_dir,preserve_snapshot=os.environ.get('ECONAGENT_SESSION_RESTORE') if args.startup else None)
    print(json.dumps(result))


if __name__=='__main__':main()
