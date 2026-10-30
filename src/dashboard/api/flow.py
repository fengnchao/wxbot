#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""消息流转与 wxbot 通道流水（只读日志/库）。"""


def read(ctx):
    """队列事实 + 按 contact / msg_id 关联的服务阶段。"""
    return 200, ctx.read_message_flow(ctx.home, contact=ctx.one('contact'),
                                      limit=ctx.num('limit', 50), offset=ctx.num('offset', 0),
                                      order=ctx.one('order', 'desc'))


def wxbot(ctx):
    """wxbot 主循环流水：收到 / 回复 / 外发 + agent 耗时 + 任务归属。"""
    return 200, ctx.collect_wxbot(ctx.home, ctx.load_directory(ctx.home),
                                  flow_contact=ctx.one('flow_contact'),
                                  flow_offset=ctx.num('flow_offset', 0),
                                  flow_order=ctx.one('flow_order', 'desc'))
