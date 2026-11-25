# -*- coding: utf-8 -*-
"""
demo_unlock.py -- 生成解锁窗截图 _demo_unlock.png

解锁窗是模态的，直接构造会卡在 wait_window 上。这里替换掉 wait_window，
让它不阻塞、由 mainloop 驱动，等窗口画好再按窗口矩形截图。

只截解锁窗本身，不含主窗、桌面、任务栏。
"""

from __future__ import annotations

import os
import tempfile
import tkinter as tk
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="vaultunlock-"))
os.environ["VAULT_DIR"] = str(TMP)

HERE = Path(__file__).resolve().parent

import shot_tool           # noqa: E402
import vault_app           # noqa: E402
import vault_store as vs   # noqa: E402
import vault_theme as th   # noqa: E402

SHOT = HERE / "_demo_unlock.png"


def main() -> int:
    vs.ensure_dirs()

    # 解锁窗需要一个 Tk 根窗口做 owner；根窗口本身保持不可见
    root = tk.Tk()
    th.apply_theme(root)
    root.withdraw()

    orig_wait = vault_app.UnlockDialog.wait_window
    holder: dict[str, object] = {}

    def fake_wait(self, *args, **kwargs):
        holder["dlg"] = self

    vault_app.UnlockDialog.wait_window = fake_wait
    try:
        vault_app.UnlockDialog(root)
    finally:
        vault_app.UnlockDialog.wait_window = orig_wait

    dlg = holder.get("dlg")
    if dlg is None:
        print("解锁窗没建起来")
        root.destroy()
        return 1

    state: dict[str, object] = {}

    def shoot() -> None:
        shot_tool.settle(dlg, times=5)
        img = shot_tool.grab_with_titlebar(dlg, extra_top=30)
        state["ok"] = shot_tool.save(img, SHOT)
        if img is not None:
            state["size"] = img.size
        root.quit()

    dlg.after(900, shoot)
    root.mainloop()

    try:
        dlg.destroy()
    except Exception:
        pass
    root.destroy()

    print("窗口区域:", state.get("size"))
    print("saved:", SHOT, state.get("ok"))
    return 0 if state.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
