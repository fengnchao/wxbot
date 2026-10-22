"""Persisted log settings; command-line arguments and environment still take precedence."""
from copy import deepcopy
import os
from pathlib import Path
import tomllib

DEFAULT_PATH=Path(__file__).resolve().parents[1]/'config.log.toml'
DEFAULTS={'server':{'host':'127.0.0.1','port':8788},
          'sources':{'home':str(DEFAULT_PATH.parent/'data'),'wxbot_config':'','butler_config':'','groups_file':''}}


def config_path():
    return Path(os.environ.get('LOG_CONFIG') or DEFAULT_PATH)


def load_settings(path=None):
    result=deepcopy(DEFAULTS)
    target=Path(path) if path else config_path()
    raw={}
    if target.exists():
        with target.open('rb') as fh:raw=tomllib.load(fh)
        for group,value in raw.items():
            if isinstance(value,dict) and isinstance(result.get(group),dict):result[group].update(value)
            else:result[group]=value
    # Preserve the legacy data source when an existing Hermes config is present;
    # fresh installations explicitly point log at Butler's own data directory.
    if not (raw.get('sources') or {}).get('home'):
        candidate=Path(result['sources'].get('butler_config') or target.parent/'config.butler.toml')
        if candidate.exists():
            with candidate.open('rb') as fh:bt=tomllib.load(fh)
            if (bt.get('agent') or {}).get('provider','hermes')=='hermes' and (bt.get('hermes') or {}).get('root'):
                result['sources']['home']=bt['hermes']['root']
    return result
