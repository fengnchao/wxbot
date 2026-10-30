"""Explicit local installation upgrade, preserving connection and authentication."""
import os
from pathlib import Path

import tomlkit

from butler.runtime.migration import migrate_installation, _replace
from common.config_lock import config_lock


def clean_legacy_locks(root):
    root=Path(root).resolve()
    report={'removed':[], 'busy':[]}
    for path in root.glob('config.*.toml.edit.lock'):
        if path.is_symlink() or path.resolve().parent!=root:continue
        try:
            with path.open('r+b') as fh:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
                    fh.seek(0);msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    fcntl.flock(fh,fcntl.LOCK_UN)
            path.unlink()
            report['removed'].append(path.name)
        except OSError:
            report['busy'].append(path.name)
    return report


def relative_log_sources(root):
    path=Path(root).resolve()/'config.log.toml'
    if not path.exists():return False
    with config_lock(path):
        original=path.read_bytes()
        doc=tomlkit.parse(original.decode('utf-8-sig'))
        changed=False
        for key,value in doc.get('sources',{}).items():
            if not value:continue
            target=Path(value).expanduser()
            if not target.is_absolute():continue
            try:relative=os.path.relpath(target,path.parent).replace('\\','/')
            except ValueError:continue  # Different Windows drive: keep equivalent absolute path.
            doc['sources'][key]=relative;changed=True
        if changed:
            text=tomlkit.dumps(doc)
            if original.startswith(b'\xef\xbb\xbf'):text='\ufeff'+text
            _replace(path,text)
        return changed


def upgrade_installation(root):
    root=Path(root).resolve()
    from butler.identity.contact_store import ContactStore, is_unified
    from butler.identity.directory import directory_path
    database=directory_path(root/'config.butler.toml')
    if is_unified(database):
        result=dict(database=str(database),version=ContactStore(database).snapshot()['version'],cleaned=[],contacts_active=True)
    else:
        result=migrate_installation(root)
        result['contacts_next']='python -m butler contacts-preview --directory "'+str(root)+'"'
    result.update(ok=True, log_sources_updated=relative_log_sources(root),locks=clean_legacy_locks(root))
    return result
