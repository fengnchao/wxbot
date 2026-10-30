"""读取 config.toml，其他模块只从这里取配置。"""
import math
import os
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def validate_model_concurrency(value):
    if type(value) is not int or value < 1:
        raise ValueError('queue.max_model_requests 必须是正整数（不能是布尔值）')


def validate_typing_mode(wcfg):
    if not isinstance(wcfg, dict):
        raise ValueError('wechat 必须是配置表')
    typing = wcfg.get('typing', {})
    if not isinstance(typing, dict):
        raise ValueError('wechat.typing 必须是配置表')
    mode = typing.get('mode', 'chunked')
    if mode not in ('full', 'chunked', 'streaming'):
        raise ValueError('wechat.typing.mode 必须是 full/chunked/streaming')
    return mode


def validate_typing_config(wcfg):
    validate_typing_mode(wcfg)
    if not isinstance(wcfg, dict):
        raise ValueError('wechat 必须是配置表')
    typing = wcfg.get('typing', {})
    if not isinstance(typing, dict):
        raise ValueError('wechat.typing 必须是配置表')
    chunk_size = typing.get('chunk_size', 5)
    if type(chunk_size) is not int or not 1 <= chunk_size <= 100:
        raise ValueError('wechat.typing.chunk_size 必须是 1–100 的整数（不能是布尔值）')
    chunk_interval = typing.get('chunk_interval', .25)
    if (type(chunk_interval) not in (int, float) or not .05 <= chunk_interval <= 10
            or not math.isfinite(chunk_interval)):
        raise ValueError('wechat.typing.chunk_interval 必须是 0.05–10 的有限数值（秒）')
    return chunk_size, float(chunk_interval)


def validate_failure_timeout(value):
    if (type(value) not in (int, float) or not 1 <= value <= 86400
            or not math.isfinite(value)):
        raise ValueError('queue.failure_discard_seconds 必须是 1–86400 的有限数值（秒）')
    return value


def validate_retry_delay(value):
    if (type(value) not in (int, float) or not 5 <= value <= 600
            or not math.isfinite(value)):
        raise ValueError('queue.retry_delay_seconds 必须是 5–600 的有限数值（秒）')
    return float(value)


def validate_max_delivery_retries(value):
    if type(value) is not int or not 0 <= value <= 10:
        raise ValueError('queue.max_delivery_retries 必须是 0–10 的整数（不能是布尔值）')
    return value


def validate_group_reply_chance(value):
    if (type(value) not in (int, float) or isinstance(value, bool)
            or not 0 <= value <= 1 or not math.isfinite(value)):
        raise ValueError('bot.group_reply_chance 必须是 0–1 的有限数值（不能是布尔值）')
    return float(value)


def validate_emoji_chance(value):
    if (type(value) not in (int, float) or isinstance(value, bool)
            or not 0 <= value <= 1 or not math.isfinite(value)):
        raise ValueError('bot.emoji_chance 必须是 0–1 的有限数值（不能是布尔值）')
    return float(value)


def validate_runtime_config(cfg):
    bot = cfg.get('bot', {})
    if not isinstance(bot, dict):
        raise ValueError('bot 必须是配置表')
    for key, default, low, high in (
        ('group_reply_cooldown_seconds', 30, 0, 86400),
        ('group_reply_budget_window_seconds', 600, 1, 86400),
        ('group_continuation_seconds', 120, 0, 3600),
    ):
        value = bot.get(key, default)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'bot.{key} 必须是 {low}–{high} 的有限数值')
    budget = bot.get('group_reply_budget', 10)
    if type(budget) is not int or not 0 <= budget <= 10000:
        raise ValueError('bot.group_reply_budget 必须是 0–10000 的整数')
    validate_typing_config(cfg.get('wechat', {}))
    qcfg = cfg.get('queue', {})
    if not isinstance(qcfg, dict):
        raise ValueError('queue 必须是配置表')
    if qcfg.get('restart_chat_policy', 'discard') not in {'discard', 'resume'}:
        raise ValueError('queue.restart_chat_policy 必须为 discard 或 resume')
    validate_failure_timeout(qcfg.get('failure_discard_seconds', 180))
    validate_retry_delay(qcfg.get('retry_delay_seconds', 20))
    validate_max_delivery_retries(qcfg.get('max_delivery_retries', 2))


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path or os.environ.get('WXBOT_CONFIG') or ROOT / "config.wxbot.toml")
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件 {path}，请先运行 python -m butler setup 安装引导")
    with open(path, "r", encoding="utf-8-sig") as f:
        cfg = tomllib.loads(f.read())
    cfg['_config_path'] = str(path.resolve())
    cfg['_config_dir'] = str(path.resolve().parent)
    from butler.directory import DirectoryStore, directory_path, directory_enabled
    if directory_enabled(path, cfg):
        shared = DirectoryStore(directory_path(path, cfg))
        projection = shared.channel_projection()
        cfg['_directory_path'] = str(shared.path)
        for section, values in projection.items():
            target = cfg.setdefault(section, {})
            for key, value in values.items():
                if isinstance(value, dict):
                    target.setdefault(key, {}).update(value)
                else:
                    target[key] = value
        cfg.setdefault('wechat', {})['_directory_path'] = str(shared.path)
    validate_runtime_config(cfg)
    bot = cfg.setdefault("bot", {})
    qcfg = cfg.setdefault('queue', {})
    validate_model_concurrency(qcfg.setdefault('max_model_requests', 2))
    qcfg.setdefault('failure_discard_seconds', 180)
    qcfg.setdefault('retry_delay_seconds', 20)
    qcfg.setdefault('max_delivery_retries', 2)
    bot.setdefault("group_reply_chance", 0.1)
    bot.setdefault("emoji_chance", 0.2)
    bot.setdefault('group_reply_cooldown_seconds', 30)
    bot.setdefault('group_reply_budget', 10)
    bot.setdefault('group_reply_budget_window_seconds', 600)
    bot.setdefault('group_continuation_seconds', 120)
    validate_group_reply_chance(bot["group_reply_chance"])
    validate_emoji_chance(bot["emoji_chance"])
    wechat = cfg.setdefault("wechat", {})
    wechat.setdefault('window_class', 'mmui::ChatSingleWindow')
    for key,default in {
        'message_list': {'control_type':'ListControl','automation_id':'chat_message_list'},
        'input': {'control_type':'EditControl','automation_id':'chat_input_field'},
        'text_item': {'class_name':'mmui::ChatTextItemView'},
    }.items():
        # An explicit selector replaces the default as a whole; mixing selector
        # fields could make a valid custom WeChat version impossible to match.
        wechat.setdefault(key,default)
    mode = wechat.setdefault("mode", "main")
    if mode not in {"main", "independent"}:
        raise ValueError("[wechat].mode 必须是 main 或 independent")
    users = bot.get("bound_users", [])
    groups = bot.get("bound_groups", [])
    if mode == "independent" and not users and not groups:
        raise ValueError("config.wxbot.toml 里 [bot].bound_users 和 [bot].bound_groups 不能同时为空")
    overlap = set(users) & set(groups)
    if overlap:
        raise ValueError(f"聊天不能同时配置为联系人和群聊：{', '.join(sorted(overlap))}")
    if groups and not bot.get("mention_names"):
        raise ValueError("配置了 [bot].bound_groups 时，必须在 [bot].mention_names 配置机器人在微信里的昵称")
    return cfg
