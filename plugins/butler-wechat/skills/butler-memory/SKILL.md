---
name: butler-memory
description: 用户明确要求记住、查询个人资料或偏好时使用。
metadata:
  butler:
    tags: [butler-tool]
    tools: [memory_get, memory_search, memory_set]
---
# 用户记忆
使用 memory_get / memory_search 查询，memory_set 保存用户明确确认的事实或偏好。
每条用一个简短 key。不要保存密码、Token、猜测或群里其他成员的资料。
服务端已经绑定身份，不传 uid、contact 或其他用户标识。
心跳只有查询权限；不要声称已写入。
