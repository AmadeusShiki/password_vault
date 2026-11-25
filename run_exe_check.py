# -*- coding: utf-8 -*-
"""
run_exe_check.py -- 启动打包后的 exe，截图，然后关掉。

为什么需要这个而不是直接 PowerShell：
  exe 是 onefile 的，启动时会把自身解包到 %TEMP%；当前沙箱不允许往默认
  %TEMP% 写，所以必须把 TEMP/TMP 指到一个可写目录再启动。

用法：
    python run_exe_check.py dist/VaultMD.exe _exe_shot.png
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    exe = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "dist" / "VaultMD.exe")
    out = Path(sys.argv[2] if len(sys.argv) > 2 else HERE / "_exe_shot.png")
    if not exe.is_absolute():
        exe = (HERE / exe).resolve()

    if not exe.is_file():
        print("找不到 exe:", exe)
        return 2

    tmp = HERE / "_runner_tmp"
    tmp.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)

    print("启动:", exe)
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(9)

    ok = proc.poll() is None
    print("进程存活:", ok, "pid:", proc.pid)

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(out)
        print("截图:", out, out.is_file())
    except Exception as exc:
        print("截图失败:", repr(exc))

    # 数据目录是否落在 exe 旁边
    data = exe.parent / "vault_data"
    print("数据目录:", data, "存在:", data.is_dir())
    if data.is_dir():
        for p in sorted(data.iterdir()):
            print("   ", p.name, p.stat().st_size if p.is_file() else "<dir>")

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    se, so = proc.communicate()
    if se:
        print("stderr:", se.decode("utf-8", "replace")[:1500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
