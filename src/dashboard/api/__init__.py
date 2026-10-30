#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP 处理器：只做「解析参数 → 调 view / 数据源 → 返回 (status, body)」。

不直接碰 socket，也不拼 JSON —— 传输层在 dashboard.http。
服务函数（配置、数据源、代理请求）一律通过 ctx 取得，见 dashboard.http.RequestContext。
"""
