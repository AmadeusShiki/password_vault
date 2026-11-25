# -*- coding: utf-8 -*-
"""
verify_unlock_only.py -- 验证"启动时只显示解锁窗，主窗口不可见"

做法：
  1. 用源码方式启动 vault_app（子进程，不自动填密钥）；
  2. 等 2 秒，外部截屏；
  3. 用 pygetwindow/PIL 无法枚举窗口，就再截一张并人工看两张图；
  4. 结论靠两件事判断：截图里只有解锁窗、并且没有空白表格。

用法：
    python verify_unlock_only.py
产物：
    _verify_1_unlock.png   启动后 2 秒
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def grab(path: Path) -> bool:
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(path)
        return path.is_file()
    except Exception as exc:
        print("截图失败:", repr(exc))
        return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="vault-unlock-check-"))
    env = dict(os.environ)
    env["VAULT_DIR"] = str(tmp / "vault_data")
    env["PYTHONIOENCODING"] = "utf-8"

    print("启动 vault_app（源码模式，等待人工/自动看图）")
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "vault_app.py")],
        cwd=str(HERE), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    time.sleep(3.0)
    alive = proc.poll() is None
    print("进程存活:", alive)

    out = HERE / "_verify_1_unlock.png"
    ok = grab(out)
    print("截图:", out, ok)

    if alive:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
