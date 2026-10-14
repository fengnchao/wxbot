"""读取 config.toml，其他模块只从这里取配置。"""
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.wxbot.toml"
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件 {path}，请先复制 config.wxbot.example.toml 为 config.wxbot.toml")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    bot = cfg.setdefault("bot", {})
    users = bot.get("bound_users", [])
    groups = bot.get("bound_groups", [])
    if not users and not groups:
        raise ValueError("config.wxbot.toml 里 [bot].bound_users 和 [bot].bound_groups 不能同时为空")
    overlap = set(users) & set(groups)
    if overlap:
        raise ValueError(f"聊天不能同时配置为联系人和群聊：{', '.join(sorted(overlap))}")
    if groups and not bot.get("mention_names"):
        raise ValueError("配置了 [bot].bound_groups 时，必须在 [bot].mention_names 配置机器人在微信里的昵称")
    return cfg
