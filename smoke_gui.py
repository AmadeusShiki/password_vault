# -*- coding: utf-8 -*-
"""
smoke_gui.py -- GUI 冒烟测试

不依赖人工看窗口：真的把 Tk 窗口建起来，用 after() 自动驱动一遍
"解锁 -> 新增 -> 保存 -> 重载 -> 换密钥打开 -> 锁屏" 的流程，
跑完自动截图（如果环境支持）并退出。

用法：
    python smoke_gui.py                 # 建真窗口跑一遍
    python smoke_gui.py --screenshot    # 额外存一张窗口截图到 vault_data/smoke*.png
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="vaultgui-"))
os.environ["VAULT_DIR"] = str(TMP)

import vault_crypto as vc  # noqa: E402
import vault_store as vs   # noqa: E402

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print("  [ok]  %s" % name)
    else:
        FAILS.append(name)
        print("  [FAIL] %s %s" % (name, detail))


def build_app_with_key(passphrase: str):
    """
    绕开 UnlockDialog（模态窗会阻塞），直接构造 VaultApp 并注入密钥。

    做法：临时把 UnlockDialog 替换成一个假类，它直接把 passphrase 交出去。
    """
    import vault_app

    state: dict[str, object] = {}

    class FakeDialog:
        """假装是解锁窗：记录此刻主窗的可见状态，然后直接交出密钥。"""

        def __init__(self, master):
            state["app"] = master
            try:
                state["state_during_unlock"] = master.state()
                state["viewable_during_unlock"] = master.winfo_viewable()
            except Exception:
                pass
            self.passphrase = passphrase

    original = vault_app.UnlockDialog
    vault_app.UnlockDialog = FakeDialog
    try:
        app = vault_app.VaultApp()
    finally:
        vault_app.UnlockDialog = original

    setattr(app, "_unlock_probe", state)
    return app


def main() -> int:
    vs.ensure_dirs()

    # 准备一个已有 2 条记录的库，用 key-A 加密
    seed = [
        {"record": {"site": "github.com", "username": "alice", "password": "Gh!7xQ2p",
                    "url": "", "policy": "默认(强)"},
         "ok": True, "foreign": False, "newly_encrypted": True, "plain": ""},
        {"record": {"site": "工商银行", "username": "alice_bank", "password": "B4nk#2024x",
                    "url": "", "policy": "银行/金融(24位)"},
         "ok": True, "foreign": False, "newly_encrypted": True, "plain": ""},
    ]
    vs.write_vault_text(vc.encrypt_vault(seed, "key-A"))

    print("data dir:", TMP)
    print("--- 用 key-A 打开 ---")
    app = build_app_with_key("key-A")
    app.update()

    # 解锁期间主窗必须完全藏起来，否则解锁窗背后会露出一个空白密码库
    probe = getattr(app, "_unlock_probe", {})
    check("解锁期间主窗被隐藏（withdrawn）",
          probe.get("state_during_unlock") == "withdrawn",
          str(probe.get("state_during_unlock")))
    check("解锁期间主窗不可见",
          probe.get("viewable_during_unlock") == 0,
          str(probe.get("viewable_during_unlock")))
    check("解锁后主窗正常显示",
          app.state() == "normal" and app.winfo_viewable() == 1,
          "%s / %s" % (app.state(), app.winfo_viewable()))

    check("窗口标题", app.title() == "密码库 · VaultMD", app.title())
    check("表格渲染 2 行", len(app.tree.get_children()) == 2,
          str(len(app.tree.get_children())))
    check("密码明文直显（无掩码）",
          app.tree.item(app.tree.get_children()[0], "values")[2] == "Gh!7xQ2p",
          str(app.tree.item(app.tree.get_children()[0], "values")))
    check("状态栏显示条数", "共 2 条" in app.status.cget("text"), app.status.cget("text"))

    # 表格里不该有"状态/备注"这类会提示给旁观者的列
    check("表格只有 4 列", len(app.tree["columns"]) == 4, str(app.tree["columns"]))
    check("没有备注列", "note" not in app.tree["columns"], str(app.tree["columns"]))
    check("没有状态列", "status" not in app.tree["columns"], str(app.tree["columns"]))
    check("工具栏没有导出按钮",
          not hasattr(app, "export_plain"))

    # 模拟"配置模式新增一条"：直接走 app 的保存路径
    app.entries.append({
        "record": {"site": "新增站点", "username": "bob", "password": "NewPw!9z",
                   "url": "https://example.com", "policy": ""},
        "ok": True, "foreign": False, "newly_encrypted": True, "plain": "",
    })
    app.save_to_disk()
    app._refresh_table()
    app.update()
    check("保存后 3 行", len(app.tree.get_children()) == 3)

    raw = vs.VAULT_FILE.read_text(encoding="utf-8")
    check("新增的明文没落盘", "NewPw!9z" not in raw and "新增站点" not in raw)

    # 搜索过滤
    app.filter_text.set("github")
    app.update()
    check("搜索 github 命中 1 行", len(app.tree.get_children()) == 1,
          str(len(app.tree.get_children())))
    app.filter_text.set("")
    app.update()

    # 在同一个 app 里换密钥重新解（等价于锁屏后重进）
    print("--- 同一文件换 key-B 打开 ---")
    app.passphrase = "key-B"
    app.reload_from_disk()
    app.update()
    check("key-B 下仍显示 3 行（都是乱码）", len(app.tree.get_children()) == 3)
    vals = app.tree.item(app.tree.get_children()[0], "values")
    check("key-B 下密码列不是真密码", vals[2] != "Gh!7xQ2p", str(vals[2]))
    check("key-B 下界面没有任何提示性文字",
          not any(h in " ".join(str(v) for v in vals)
                  for h in ("其他密钥", "无法解读", "乱码", "由其他")),
          str(vals))
    check("key-B 下状态栏也不提示乱码",
          not any(h in app.status.cget("text") for h in ("乱码", "可读", "其他密钥")),
          app.status.cget("text"))

    # 用 key-B 新增一条，保存，再验证 key-A 的条目没被破坏
    app.entries.append({
        "record": {"site": "B站点", "username": "carol", "password": "Cpw#77",
                   "url": "", "policy": ""},
        "ok": True, "foreign": False, "newly_encrypted": True, "plain": "",
    })
    app.save_to_disk()

    text = vs.read_vault_text()
    ea = vc.decrypt_vault(text, "key-A")
    eb = vc.decrypt_vault(text, "key-B")
    count_a = sum(1 for e in ea if e["ok"])
    count_b = sum(1 for e in eb if e["ok"])
    check("key-A 仍有 3 条可读", count_a == 3, str(count_a))
    check("key-B 有 1 条可读", count_b == 1, str(count_b))

    # 截图（可选）
    if "--screenshot" in sys.argv:
        try:
            app.update()
            import subprocess
            shot = TMP / "smoke.png"
            ps = (
                "$ErrorActionPreference='Stop';Add-Type -AssemblyName System.Windows.Forms;"
                "Add-Type -AssemblyName System.Drawing;"
                "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
                "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
                "$g=[System.Drawing.Graphics]::FromImage($bmp);"
                "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
                "$bmp.Save('%s');" % str(shot).replace("'", "''")
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], timeout=60)
            print("screenshot:", shot, shot.exists())
            dest = vs.DATA_DIR / "smoke.png"
            if shot.exists():
                dest.write_bytes(shot.read_bytes())
                print("copied to:", dest)
        except Exception:
            traceback.print_exc()

    app.passphrase = ""
    app.destroy()

    print("\n%s" % ("ALL GUI SMOKE TESTS PASSED" if not FAILS else "FAILED: %s" % FAILS))
    print("tmp:", TMP)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
