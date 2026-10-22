"""Encode structured overrides as TOML without shell interpolation."""
import json


def sdk_overrides(values):
    def toml(value):
        if isinstance(value,dict):
            return '{'+','.join(json.dumps(str(k))+ '='+toml(v) for k,v in value.items())+'}'
        if isinstance(value,list):
            return '['+','.join(toml(v) for v in value)+']'
        return json.dumps(value,ensure_ascii=False)
    return tuple(key+'='+toml(value) for key,value in values.items())
