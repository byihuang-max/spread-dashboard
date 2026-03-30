#!/usr/bin/env python3
"""桥接执行 quant-backtest 的盘后复盘页面生成脚本。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    Path.home() / "Desktop" / "quant-backtest" / "timing_model" / "narrative" / "generate_replay_page.py",
    Path.home() / "quant-backtest" / "timing_model" / "narrative" / "generate_replay_page.py",
]


def resolve_target() -> Path:
    for path in CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(f"script not found: {CANDIDATES}")


if __name__ == "__main__":
    target = resolve_target()
    result = subprocess.run(
        [sys.executable, str(target)],
        cwd=str(target.parent),
    )
    sys.exit(result.returncode)
