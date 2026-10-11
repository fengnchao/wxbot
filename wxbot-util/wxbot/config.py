"""读取 config.toml，其他模块只从这里取配置。"""
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    path = Path(path) if path else ROOT / "config.toml"
    if not path.exists():
        raise FileNotFoundError(f"找不到配置文件 {path}，请先复制 config.example.toml 为 config.toml")
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    if not cfg.get("bot", {}).get("bound_users"):
        raise ValueError("config.toml 里 [bot].bound_users 不能为空")
    return cfg
