"""Build two portable archives from an explicit source allowlist, without Git state."""
import argparse
import json
from pathlib import Path
import re
import zipfile

ROOT=Path(__file__).resolve().parents[1]
VERSION='1.0.0'
ROOT_FILES={'README.md','AGENTS.md','pyproject.toml','requirements.txt','uv.lock','.gitignore',
            'config.butler.codex.example.toml','config.wxbot.example.toml','config.log.example.toml','config.telegram.example.toml'}
SOURCE_DIRS={'butler','wxbot','log','common','tests','plugins'}
SPECIAL={'.agents/plugins/marketplace.json','scripts/setup.ps1','tools/probe_codex.py','tools/release.py',
         'docs/CODEX_INSTALL.md','docs/CODEX_PROTOCOL.md','docs/CODEX_VERIFICATION.md','docs/NEWS_DELIVERY.md','docs/TELEGRAM_NEWS.md','README.wxbot.md'}
FORBIDDEN_PARTS={'.venv','__pycache__','.git','.idea','.pytest_cache','data','cache','dist','.superpowers'}


def source_files():
    out=[]
    for path in ROOT.rglob('*'):
        if not path.is_file():continue
        rel=path.relative_to(ROOT)
        if set(rel.parts)&FORBIDDEN_PARTS or path.is_symlink():continue
        if not path.resolve().is_relative_to(ROOT):continue
        if path.name=='auth.json' or path.name.startswith('.env') or path.suffix in ('.pyc','.db','.sqlite3'):
            continue
        if path.name.endswith('.session') or '.session-' in path.name or path.name.endswith('.session.relay.lock'):
            continue
        if rel.parts[0] not in SOURCE_DIRS and rel.as_posix() not in ROOT_FILES|SPECIAL:continue
        if path.name.startswith('config.') and path.suffix=='.toml' and not path.name.endswith('.example.toml'):continue
        if '.config-backup-' in path.name or path.name.endswith('.edit.lock'):continue
        if rel.parts[0]=='log' and path.name in ('wechat_inbox_restart.py','wechat_inbox_startup.bat'):continue
        if rel.parts[0]=='log' and 'launchers' in rel.parts:continue
        out.append(path)
    return sorted(out)


def audit(files):
    findings=[]
    patterns=[re.compile(r'\bsk-(?!test|example|fake)[A-Za-z0-9_-]{24,}\b'),
              re.compile(r'\bgh[pousr]_[A-Za-z0-9]{30,}\b'),
              re.compile(r'^-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----$',re.M)]
    for path in files:
        if path.suffix.lower() not in ('.py','.md','.json','.toml','.txt','.html','.ps1','.js','.css'):continue
        text=path.read_text(encoding='utf-8-sig')
        if any(pattern.search(text) for pattern in patterns):
            findings.append({'file':path.relative_to(ROOT).as_posix(),'kind':'credential-shaped literal'})
    return findings


def build_release(output=None):
    output=Path(output or ROOT/'dist').resolve();output.mkdir(parents=True,exist_ok=True)
    files=source_files()
    findings=audit(files)
    if findings:raise ValueError('Release audit rejected files: '+json.dumps(findings))
    app=output/f'butler-wxbot-{VERSION}.zip';plugin=output/f'butler-wechat-{VERSION}.zip'
    plugin_root=ROOT/'plugins'/'butler-wechat'
    with zipfile.ZipFile(app,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files:archive.write(path,path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(plugin,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_relative_to(plugin_root):archive.write(path,path.relative_to(plugin_root).as_posix())
    return {'application':str(app),'plugin':str(plugin),'source_files':len(files),'audit_findings':findings}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output')
    args=parser.parse_args()
    print(json.dumps(build_release(args.output),ensure_ascii=False,indent=2))
