"""Run the dashboard script against an in-memory DOM; no browser/network/WeChat."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_monitor_rendering_request_races_and_navigation():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node.js is needed for the optional dashboard script checks')
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([node,str(root/'tests'/'log_frontend_checks.js')],cwd=root,
                          capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0, result.stderr
    assert 'frontend checks passed' in result.stdout
