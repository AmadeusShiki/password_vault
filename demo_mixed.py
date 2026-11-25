# -*- coding: utf-8 -*-
"""
demo_mixed.py -- 生成"混合密钥"截图 _demo_mixed.png

同一个 vault.md 里 3 条用 key-a 加密、1 条用 key-b 加密，
用 key-a 打开 → 前 3 条正常，第 4 条是乱码且没有任何提示标记。

只截应用窗口本身，不含桌面。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="vaultmix-"))
os.environ["VAULT_DIR"] = str(TMP)

HERE = Path(__file__).resolve().parent

import shot_tool               # noqa: E402
import vault_app               # noqa: E402
import vault_crypto as vc     # noqa: E402
import vault_store as vs      # noqa: E402

OK = {"ok": True, "foreign": False, "newly_encrypted": True, "plain": ""}


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

    a_group = [
        {"record": {"site": "github.com", "username": "alice",
                    "password": "Gh!7xQ2p#Lm9", "url": "https://github.com/login",
                    "policy": "默认(强)"}, **OK},
        {"record": {"site": "工商银行", "username": "alice_bank",
                    "password": "B4nk#2024xQz!W", "url": "https://mybank.example",
                    "policy": "银行/金融(24位)"}, **OK},
        {"record": {"site": "淘宝", "username": "alice_tao",
                    "password": "tao@123456", "url": "", "policy": ""}, **OK},
    ]
    b_group = [
        {"record": {"site": "公司 VPN", "username": "corp\\alice",
                    "password": "Vpn!2024abcd", "url": "https://vpn.example",
                    "policy": "默认(强)"}, **OK},
    ]

    text_a = vc.encrypt_vault(a_group, "key-a")
    text_b = vc.encrypt_vault(b_group, "key-b")
    b_lines = [ln for ln in text_b.split("\n") if ln.strip() and not ln.startswith("#")]
    vs.write_vault_text(text_a.rstrip("\n") + "\n" + "\n".join(b_lines) + "\n")

    app = build_app("key-a")
    app.geometry("1180x640+80+60")
    app._on_resize(type("E", (), {"widget": app})())
    shot_tool.settle(app, times=8)

    rows = [app.tree.item(i, "values") for i in app.tree.get_children()]
    print("用 key-a 打开，表格共 %d 行：" % len(rows))
    for r in rows:
        print("  ", str(r[0])[:40].replace("\n", " "), "|", r[1], "|", r[2])

    out = HERE / "_demo_mixed.png"
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
