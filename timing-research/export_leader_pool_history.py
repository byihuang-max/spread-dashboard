#!/usr/bin/env python3
"""桥接执行 quant-backtest 的龙头观察池历史导出脚本（增量模式）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    Path.home() / "Desktop" / "quant-backtest" / "timing_model" / "export_leader_pool_history.py",
    Path.home() / "quant-backtest" / "timing_model" / "export_leader_pool_history.py",
]


def resolve_target() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(f"script not found: {CANDIDATES}")


if __name__ == "__main__":
    target = resolve_target()
    # 用 subprocess 而不是 runpy，因为脚本依赖同目录下的模块
    result = subprocess.run(
        [sys.executable, str(target)],
        cwd=str(target.parent),
    )
    sys.exit(result.returncode)
