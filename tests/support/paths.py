"""测试用的仓库根路径。

测试分域后各文件层级不同，统一从这里取仓库根，不要再写
`Path(__file__).resolve().parents[N]`。
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
