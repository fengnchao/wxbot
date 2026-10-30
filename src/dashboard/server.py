#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""微信管家看板进程入口（组装层）。

三层分工：
    dashboard.http      传输：解析请求、鉴权确认、静态文件、异常包装
    dashboard.routes    路由单张表
    dashboard.api.*     每个域：解析参数 → 调 view / 数据源 → 返回 (status, body)

本模块只做组装：把服务函数放进本模块命名空间（测试按名 monkeypatch 本模块仍然生效），
再用 ThreadingHTTPServer 起进程。旧的调用点（`from dashboard.server import ...`）保持可用。

用法:
    python -m dashboard.server                  # http://127.0.0.1:8788/app/
    python -m dashboard.server --port 9000 --open
"""
import argparse
import os
import threading
import tomllib
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

from butler.channels.telegram.relay.settings import SettingsConflict
from common import news_config
from common.paths import REPO_ROOT
from dashboard.api.support import (EXPORT_DIR, HERMES_HOME, WXBOT_CHANNEL,
                                   _HEARTBEAT_CONFIG_LOCK, _load_butler_config,
                                   butler_config_path, dashboard_mode,
                                   effective_heartbeat_policies, fetch_butler_data,
                                   fetch_hermes_skills, heartbeat_audit_path,
                                   heartbeat_config_path, heartbeat_state_path,
                                   is_butler_role_skill, load_butler_contacts,
                                   load_heartbeat_config, load_heartbeat_events,
                                   load_heartbeat_status, save_heartbeat_config,
                                   trigger_butler_heartbeat, unified_contact_store,
                                   validate_policy_skills, wxbot_config_path)
from dashboard.config_editor import ConfigConflict, ConfigEditor, config_lock
from dashboard.config_view import ConfigView
from dashboard.flow_view import FlowView
from dashboard.flowlog import (_iso_to_epoch, build_groups_payload, collect_wxbot,
                               group_file_path, load_groups_file, load_wxbot_contacts,
                               merge_outbound, parse_wxbot_log, read_message_flow,
                               save_groups_file)
from dashboard.http import BaseHandler, RequestContext
from dashboard.queue_actions import QueueActions
from dashboard.queue_view import QueueView
from dashboard.settings import config_path as log_config_path, load_settings
from dashboard.sources import (_as_pos_int, bare_uid, build_users, collect_inbound,
                               collect_jobs, collect_outbound, connect, discover_dbs,
                               display_of, display_of_ci, jobs_ui_state, load_directory,
                               load_wxbot_profile_map, safe_query)
from dashboard.telegram_relay_admin import (TelegramRelayAdmin,
                                            request_resolution as request_relay_resolution)
from dashboard.telegram_view import ISSUES as TELEGRAM_ISSUES, TERMINAL as TELEGRAM_TERMINAL
from dashboard.telegram_view import TelegramView
from dashboard.user_admin import request_user_admin
from dashboard.workflow_view import WorkflowView

_LOG_SETTINGS = load_settings()


class Handler(BaseHandler):
    """服务函数的解析命名空间 = 本模块 globals（见 dashboard.http.RequestContext）。"""

    def _service_namespace(self):
        return globals()


def build_server(host, port, home=None):
    """构造管理台 server（不启动）；home 默认沿用 HERMES_HOME。"""
    if home:
        Handler.home = home
    return ThreadingHTTPServer((host, port), Handler)


def main():
    ap = argparse.ArgumentParser(description="微信管家日志（wxbot 通道流水 + 定时任务 + 用户分组）")
    ap.add_argument("--host", default=_LOG_SETTINGS['server']['host'])
    ap.add_argument("--port", type=int, default=_LOG_SETTINGS['server']['port'])
    ap.add_argument("--home", default=HERMES_HOME)
    ap.add_argument("--open", action='store_true', help='启动后打开浏览器')
    args = ap.parse_args()

    Handler.home = args.home
    print(f"[wechat-inbox] HERMES_HOME = {args.home}")
    for pr, path in discover_dbs(args.home):
        print(f"  - {pr:<42} {path}")
    print(f"[wechat-inbox] 页面: http://{args.host}:{args.port}/app/   (Ctrl+C 退出)")
    try:
        server = build_server(args.host, args.port)
        if args.open:
            import webbrowser
            host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
            webbrowser.open(f'http://{host}:{server.server_port}/app/')
        try:
            server.serve_forever()
        finally:
            server.server_close()
    except KeyboardInterrupt:
        print("\n[wechat-inbox] 已停止")


if __name__ == "__main__":
    main()
