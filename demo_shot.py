# -*- coding: utf-8 -*-
"""
demo_shot.py -- 生成主窗截图 _demo.png

只截应用窗口本身：用 shot_tool.grab_window，按 winfo_rootx/rooty 裁矩形，
桌面、任务栏、其他窗口一概不进图。

用的是临时目录里的演示库（密钥 demo-key），不会碰真正的 vault_data/。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TMP = Path(tempfile.mkdtemp(prefix="vaultdemo-"))
os.environ["VAULT_DIR"] = str(TMP)

import shot_tool                # noqa: E402
import vault_app                # noqa: E402
import vault_crypto as vc       # noqa: E402
import vault_store as vs        # noqa: E402

DEMO_KEY = "demo-key"

OK = {"ok": True, "foreign": False, "newly_encrypted": True, "plain": ""}

DEMO_DATA = [
    {"record": {"site": "github.com", "username": "alice",
                "password": "Gh!7xQ2p#Lm9", "url": "https://github.com/login",
                "policy": "默认(强)"}, **OK},
    {"record": {"site": "工商银行", "username": "alice_bank",
                "password": "B4nk#2024xQz!W", "url": "https://mybank.example",
                "policy": "银行/金融(24位)"}, **OK},
    {"record": {"site": "淘宝", "username": "alice_tao",
                "password": "tao@123456", "url": "", "policy": ""}, **OK},
    {"record": {"site": "公司 VPN", "username": "corp\\alice",
                "password": "Vpn!2024abcd", "url": "https://vpn.example",
                "policy": "默认(强)"}, **OK},
]


def build_app(key: str):
    class _Fake:
        def __init__(self, master):
            self.passphrase = key

    original = vault_app.UnlockDialog
    vault_app.UnlockDialog = _Fake
    try:
        return vault_app.VaultApp()
    finally:
        vault_app.UnlockDialog = original


def main() -> int:
    vs.ensure_dirs()
    vs.write_vault_text(vc.encrypt_vault(DEMO_DATA, DEMO_KEY))

    app = build_app(DEMO_KEY)
    app.geometry("1180x680+80+60")
    app._on_resize(type("E", (), {"widget": app})())
    shot_tool.settle(app, times=8)

    out = HERE / "_demo.png"
    img = shot_tool.grab_with_titlebar(app)
    ok = shot_tool.save(img, out)
    if img is not None:
        print("窗口区域:", img.size)
    print("saved:", out, ok)

    app.passphrase = ""
    app.destroy()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
