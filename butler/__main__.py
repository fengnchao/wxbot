"""python -m butler: setup, diagnostics, login, and service entrypoints."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from .config import load


def main(argv=None):
    parser=argparse.ArgumentParser(description='Portable Butler/wxbot')
    parser.add_argument('command',choices=['init','setup','migrate','doctor','login','serve','start'])
    parser.add_argument('--config',default=None)
    parser.add_argument('--directory',default='.')
    parser.add_argument('--no-wechat',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='init':
        from .setup import initialize
        print(json.dumps(initialize(args.directory),ensure_ascii=False,indent=2));return 0
    if args.command=='setup':
        from .install_wizard import run_wizard
        result=run_wizard(args.directory)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result.get('ok') else 1
    if args.command=='migrate':
        from .upgrade import upgrade_installation
        root=Path(args.config).resolve().parent if args.config else Path(args.directory)
        print(json.dumps(upgrade_installation(root),ensure_ascii=False,indent=2));return 0
    chosen=args.config or os.environ.get('BUTLER_CONFIG')
    if not chosen and args.directory!='.':chosen=str(Path(args.directory)/'config.butler.toml')
    cfg=load(chosen)
    from .install_wizard import installation_mode
    mode=installation_mode(cfg.config_dir or Path(__file__).resolve().parents[1])
    if args.command=='doctor':
        from .setup import doctor
        result=doctor(cfg,check_wechat=not args.no_wechat)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['ok'] else 1
    if args.command=='login':
        if mode!='local' or cfg.provider!='codex':
            parser.error('当前接入方式不使用本机 Codex 登录，请按对应服务的登录说明操作。')
        from codex_cli_bin import bundled_codex_path
        cfg.codex_home_path().mkdir(parents=True,exist_ok=True)
        env=os.environ.copy();env['CODEX_HOME']=str(cfg.codex_home_path())
        return subprocess.call([str(bundled_codex_path()),'login'],env=env)
    if args.command=='serve':
        if mode!='local':parser.error('当前接入方式不运行本机 Butler；请使用 start 启动通道与管理台。')
        from .server import serve
        return serve(cfg)
    # Explicit user-invoked start only; never stop or restart existing services.
    root=Path(__file__).resolve().parents[1]
    config_root=Path(cfg.config_dir or root).resolve()
    config_path=Path(chosen).resolve() if chosen else config_root/'config.butler.toml'
    from .setup import doctor
    report=doctor(cfg,check_wechat=False)
    port_names=['wxbot_port','log_port']+(['butler_port'] if mode=='local' else [])
    if not all(report['checks'][name]['ok'] for name in port_names):
        parser.error('A service port is already occupied. Existing services were left running.')
    env=os.environ.copy()
    env.update(BUTLER_CONFIG=str(config_path),
               WXBOT_CONFIG=str(config_root/'config.wxbot.toml'),LOG_CONFIG=str(config_root/'config.log.toml'))
    processes=[]
    commands=[['-m','butler.server','--config',str(config_path)],
              ['-m','log.server'],
              ['-m','wxbot.main']]
    if mode!='local':commands=commands[1:]
    try:
        for command in commands:
            processes.append(subprocess.Popen([sys.executable,*command],cwd=root,env=env))
        import time
        while all(process.poll() is None for process in processes):time.sleep(.5)
        return next((p.returncode for p in processes if p.poll() is not None),1)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:process.terminate()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
