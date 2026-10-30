#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务函数的延迟绑定。

看板是单进程管理台：`dashboard.server` 是唯一的装配点，数据源模块
（dashboard.api.support / sources / flowlog）之间互调时也经由这里取值。

拆分前所有函数同处 server.py，测试里 `monkeypatch.setattr(dashboard.server,
'butler_config_path', ...)` 对内部调用同样生效；经由本模块取值可以保持这一行为，
而不必让内部调用全都绕一层参数。
"""
import sys

SERVER_MODULE = 'dashboard.server'


def get(name, fallback=None):
    """取 server 命名空间里的实现；没有（或尚未装配）则用 fallback。"""
    module = sys.modules.get(SERVER_MODULE)
    if module is not None:
        return getattr(module, name, fallback)
    return fallback
