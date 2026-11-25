# -*- coding: utf-8 -*-
"""
vault_app.py -- 密码库 GUI（Python + tkinter + cryptography）

界面结构：
  ┌ 解锁窗：看板娘头像 + 密钥输入，无任何说明性文字
  └ 主窗
      ├ 顶部深蓝栏：看板娘站位（右侧）+ 标题 + 工具栏
      ├ 搜索行：浅蓝底、聚焦时描边变蓝
      ├ 表格：站点 / 用户名 / 密码（明文直显）/ 登录地址
      └ 状态栏：文件路径、条目数

行为契约：
  1) 不做密钥校验。解密失败不报错，把确定性乱码照样显示出来，界面不做任何区分标记。
  2) 一行 = 一条记录 = 一份独立密文。同一文件可混用不同密钥加密的行。
  3) 编辑/新增时用当前会话密钥加密；解不开的行默认原样保留，不会被本轮保存破坏。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

import vault_crypto as vc
import vault_store as vs
import vault_theme as th

APP_TITLE = "密码库 · VaultMD"


# ---------------------------------------------------------------------------
# 解锁窗
# ---------------------------------------------------------------------------

class UnlockDialog(tk.Toplevel):
    """启动时的密钥输入框。看板娘头像 + 输入框，没有别的话。"""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("解锁")
        self.resizable(False, False)
        self.passphrase: str | None = None
        self.show = tk.BooleanVar(value=False)

        th.apply_icon(self)

        card = ttk.Frame(self, style="Card.TFrame", padding=24)
        card.pack(fill="both", expand=True)

        # --- 头像 ---
        head = th.face_photo(self, 96)
        head_row = ttk.Frame(card, style="Card.TFrame")
        head_row.pack(fill="x", pady=(0, 16))
        if head is not None:
            lbl = ttk.Label(head_row, image=head, style="Card.TLabel")
            lbl.image = head
            lbl.pack()

        # --- 输入 ---
        ttk.Label(card, text="密钥", style="Field.TLabel").pack(anchor="w")
        self.entry = ttk.Entry(card, width=38, show="•", font=th.FONT_MONO)
        self.entry.pack(fill="x", pady=(6, 10))
        self.entry.focus_set()

        ttk.Checkbutton(card, text="显示密钥", variable=self.show,
                        command=self._toggle).pack(anchor="w")

        btns = ttk.Frame(card, style="Card.TFrame")
        btns.pack(fill="x", pady=(18, 0))
        ttk.Button(btns, text="解锁", style="Primary.TButton",
                   command=self._ok).pack(side="right")
        ttk.Button(btns, text="取消", style="Ghost.TButton",
                   command=self._cancel).pack(side="right", padx=(0, 8))

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        # 不要用 transient(master)：主窗在解锁期间是 withdrawn 的，
        # 一旦绑定成 transient，Tk 会把解锁窗跟着藏起来，用户看不到任何窗口。
        # 只要模态行为的话，grab_set + wait_window 就够了。
        self.grab_set()
        self.deiconify()
        self.lift()
        self.update_idletasks()
        self._center()
        self.entry.focus_force()
        self.wait_window(self)

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        # 解锁窗没有父窗口可依，就老老实实放屏幕中央偏上
        self.geometry("+%d+%d" % ((sw - w) // 2, (sh - h) // 3))

    def _toggle(self) -> None:
        self.entry.configure(show="" if self.show.get() else "•")

    def _ok(self) -> None:
        self.passphrase = self.entry.get()
        self.destroy()

    def _cancel(self) -> None:
        self.passphrase = None
        self.destroy()


# ---------------------------------------------------------------------------
# 条目编辑窗
# ---------------------------------------------------------------------------

class EntryDialog(tk.Toplevel):
    """新增 / 编辑一条记录。带密码生成器与站点规则模板。"""

    FIELDS = [
        ("site", "站点 / App 名"),
        ("username", "用户名"),
        ("password", "密码"),
        ("url", "登录地址（可选）"),
    ]

    def __init__(self, master: tk.Misc, cfg: dict[str, Any],
                 record: dict[str, str] | None = None) -> None:
        super().__init__(master)
        self.title("编辑" if record else "新增")
        self.resizable(False, False)
        self.cfg = cfg
        self.result: dict[str, str] | None = None

        th.apply_icon(self)

        rec = dict(vc.default_record())
        if record:
            rec.update({k: v for k, v in record.items() if v is not None})

        card = ttk.Frame(self, style="Card.TFrame", padding=22)
        card.pack(fill="both", expand=True)

        self.vars: dict[str, tk.StringVar] = {k: tk.StringVar(value=rec.get(k, ""))
                                             for k in vc.default_record()}
        self.policy_var = tk.StringVar(value=rec.get("policy", ""))
        self.show_pw = tk.BooleanVar(value=True)

        for row, (key, label) in enumerate(self.FIELDS):
            ttk.Label(card, text=label, style="Field.TLabel").grid(
                row=row, column=0, sticky="w", pady=(0 if row == 0 else 10, 4))
            show = "•" if key == "password" and not self.show_pw.get() else ""
            font = th.FONT_MONO if key in ("password", "url") else th.FONT_BODY
            entry = ttk.Entry(card, textvariable=self.vars[key], width=46,
                              show=show, font=font)
            entry.grid(row=row, column=1, sticky="we", pady=(0 if row == 0 else 10, 4),
                       padx=(12, 0))
            if key == "password":
                ttk.Checkbutton(card, text="显示", variable=self.show_pw,
                                command=lambda e=entry: e.configure(
                                    show="" if self.show_pw.get() else "•")
                                ).grid(row=row, column=2, sticky="w",
                                       padx=(8, 0), pady=(0 if row == 0 else 10, 4))
                self.pw_entry = entry

        # --- 密码生成器 / 本站规则 ---
        pf = ttk.LabelFrame(card, text=" 密码生成器 ", padding=14,
                            style="Card.TLabelframe")
        pf.grid(row=len(self.FIELDS), column=0, columnspan=3, sticky="we",
                pady=(18, 0))

        ttk.Label(pf, text="规则模板", style="Field.TLabel").grid(row=0, column=0, sticky="w")
        self.policy_combo = ttk.Combobox(
            pf, textvariable=self.policy_var, state="readonly", width=24,
            values=list(cfg.get("policies", {}).keys()),
        )
        self.policy_combo.grid(row=0, column=1, sticky="w", padx=10)

        self.len_var = tk.IntVar(value=vc.PasswordPolicy().length)
        ttk.Label(pf, text="长度", style="Field.TLabel").grid(row=0, column=2,
                                                             sticky="e", padx=(16, 6))
        ttk.Spinbox(pf, from_=4, to=128, textvariable=self.len_var, width=5
                    ).grid(row=0, column=3, sticky="w")

        ttk.Button(pf, text="按模板生成", style="Primary.TButton",
                   command=self._gen).grid(row=1, column=0, columnspan=4,
                                           sticky="we", pady=(12, 0))

        # --- 底部按钮 ---
        btns = ttk.Frame(card, style="Card.TFrame")
        btns.grid(row=len(self.FIELDS) + 1, column=0, columnspan=3,
                  sticky="we", pady=(18, 0))
        ttk.Button(btns, text="保存", style="Primary.TButton",
                   command=self._save).pack(side="right")
        ttk.Button(btns, text="取消", style="Ghost.TButton",
                   command=self.destroy).pack(side="right", padx=(0, 8))

        card.columnconfigure(1, weight=1)

        self.bind("<Return>", lambda e: self._save())
        self.bind("<Escape>", lambda e: self.destroy())
        self.transient(master)
        self.grab_set()
        self.update_idletasks()
        self._center()
        self.wait_window(self)

    def _center(self) -> None:
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry("+%d+%d" % ((sw - w) // 2, max(60, (sh - h) // 3)))

    def _gen(self) -> None:
        policy = vs.policy_by_name(self.cfg, self.policy_var.get())
        try:
            policy.length = max(4, min(int(self.len_var.get() or 20), 128))
        except Exception:
            policy.length = 20
        self.vars["password"].set(policy.generate())
        self.pw_entry.configure(show="" if self.show_pw.get() else "•")

    def _save(self) -> None:
        rec = {k: self.vars[k].get().strip() for k in vc.default_record()}
        rec["policy"] = self.policy_var.get().strip()
        if not rec["site"]:
            messagebox.showwarning("缺少站点名",
                                   "至少填一个站点 / App 名，否则以后找不到这条。",
                                   parent=self)
            return
        self.result = rec
        self.destroy()


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class VaultApp(tk.Tk):

    HERO_MIN = 140          # 顶部栏最小高度
    HERO_MAX = 300          # 顶部栏最大高度（再大就太占地方）

    def __init__(self) -> None:
        super().__init__()

        # 关键：主窗口一建成就是可见的，解锁窗弹出来时背后会露出一个
        # 空白的密码库窗口，很难看。所以先彻底藏起来，解锁成功再显示。
        self.withdraw()

        self.title(APP_TITLE)
        self.cfg = vs.load_config()

        th.apply_theme(self)
        th.apply_icon(self)

        size = self.cfg.get("window", {})
        self.geometry("%dx%d" % (int(size.get("width", 1120)),
                                 int(size.get("height", 700))))
        self.minsize(900, 520)

        self.passphrase: str = ""
        self.entries: list[dict[str, Any]] = []
        self.tree_items: dict[str, int] = {}      # iid -> entries 下标
        self.filter_text = tk.StringVar()
        self._clip_after: str | None = None
        self._mascot_img = None
        self._mascot_path = None
        self._mascot_size = 0

        if not self._unlock_once():
            self.destroy()
            return

        self._build_ui()
        self._refresh_table()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-f>", lambda e: self.search_entry.focus_set())
        self.bind("<Control-n>", lambda e: self.add_entry())
        self.bind("<F5>", lambda e: self.reload_from_disk())
        self.bind("<Configure>", self._on_resize)

        # 解锁成功后才露面（放在 build 之后，避免闪一下未布局的窗口）
        self._show_main()
        self.after(30, lambda: self._on_resize(
            type("E", (), {"widget": self})()))

    def _show_main(self) -> None:
        """把主窗口显示出来并居中。"""
        self.deiconify()
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _hide_main(self) -> None:
        self.withdraw()

    # ---------------- 解锁 ----------------

    def _unlock_once(self) -> bool:
        # 解锁期间主窗口必须不可见；重新解锁（锁定）时也一样
        self._hide_main()
        dlg = UnlockDialog(self)
        if dlg.passphrase is None:
            return False
        self.passphrase = dlg.passphrase
        self.reload_from_disk(silent=True)
        return True

    def lock_and_relock(self) -> None:
        """锁屏：清掉密钥，藏起主窗口，重新弹解锁窗。"""
        self.passphrase = ""
        self.entries = []
        self._refresh_table()
        self._hide_main()
        if not self._unlock_once():
            # 解锁窗被取消 -> 直接退出程序
            self.destroy()
            return
        self._refresh_table()
        self._show_main()

    # ---------------- UI ----------------

    def _build_ui(self) -> None:
        self._build_hero()
        self._build_searchbar()
        self._build_table()
        self._build_statusbar()

    # --- 顶部栏：深蓝 + 看板娘 ---
    def _build_hero(self) -> None:
        hero = ttk.Frame(self, style="Hero.TFrame")
        hero.pack(fill="x", side="top")
        self.hero = hero

        # 底部一条金色细线，呼应女仆裙摆的金线
        gold_bar = tk.Frame(hero, bg=th.GOLD, height=2)
        gold_bar.pack(side="bottom", fill="x")

        # 右侧立绘：先占位，尺寸由 _on_resize 决定
        self.mascot = ttk.Label(hero, style="Hero.TLabel", text="")
        self.mascot.pack(side="right", padx=(0, 28), pady=6)

        left = ttk.Frame(hero, style="Hero.TFrame", padding=(28, 14, 10, 12))
        left.pack(side="left", fill="both", expand=True)

        title = ttk.Frame(left, style="Hero.TFrame")
        title.pack(anchor="w")
        tk.Label(title, text="密码库", bg=th.NAVY, fg=th.PEARL,
                 font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        tk.Label(title, text="  VaultMD", bg=th.NAVY, fg=th.BLUE_LIGHT,
                 font=("Microsoft YaHei UI", 10)).pack(side="left", pady=(5, 0))

        ttk.Label(left, text="本地加密存储 · 全部在你本机",
                  style="HeroSoft.TLabel").pack(anchor="w", pady=(2, 12))
        bar = ttk.Frame(left, style="Hero.TFrame")
        bar.pack(anchor="w")

        def hero_btn(text: str, cmd, pad=(0, 0)) -> None:
            b = ttk.Button(bar, text=text, command=cmd, style="Hero.TButton")
            b.pack(side="left", padx=pad)
            return b

        hero_btn("＋ 新增", self.add_entry, (0, 6))
        hero_btn("编辑", self.edit_entry, (0, 6))
        hero_btn("删除", self.delete_entry, (0, 18))
        hero_btn("复制密码", lambda: self.copy_field("password"), (0, 6))
        hero_btn("复制用户名", lambda: self.copy_field("username"), (0, 18))
        hero_btn("重载", self.reload_from_disk, (0, 6))
        hero_btn("锁定", self.lock_and_relock)

    # --- 搜索行 ---
    def _build_searchbar(self) -> None:
        wrap = ttk.Frame(self, style="Bar.TFrame", padding=(22, 12, 22, 6))
        wrap.pack(fill="x")

        ttk.Label(wrap, text="搜索", style="Soft.TLabel").pack(side="left", padx=(0, 8))
        self.search_entry = ttk.Entry(wrap, textvariable=self.filter_text,
                                      width=36, font=th.FONT_BODY)
        self.search_entry.pack(side="left")
        self.filter_text.trace_add("write", lambda *a: self._refresh_table())

        ttk.Label(wrap, text="Ctrl+N 新增 · Ctrl+F 搜索 · F5 重载 · 双击编辑",
                  style="Soft.TLabel").pack(side="right")

    # --- 表格 ---
    def _build_table(self) -> None:
        card = ttk.Frame(self, style="Card.TFrame", padding=(2, 2))
        card.pack(fill="both", expand=True, padx=22, pady=(6, 0))

        cols = ("site", "username", "password", "url")
        heads = {"site": ("站点 / App", 220), "username": ("用户名", 200),
                 "password": ("密码", 260), "url": ("登录地址", 300)}

        self.tree = ttk.Treeview(card, columns=cols, show="headings",
                                 selectmode="browse", style="Vault.Treeview")
        for c in cols:
            text, width = heads[c]
            self.tree.heading(c, text=text, anchor="w")
            self.tree.column(c, width=width, anchor="w", stretch=True)

        ysb = ttk.Scrollbar(card, orient="vertical", command=self.tree.yview,
                            style="Vertical.TScrollbar")
        xsb = ttk.Scrollbar(card, orient="horizontal", command=self.tree.xview,
                            style="Horizontal.TScrollbar")
        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        card.rowconfigure(0, weight=1)
        card.columnconfigure(0, weight=1)

        # 斑马纹
        self.tree.tag_configure("odd", background="#FFFFFF")
        self.tree.tag_configure("even", background=th.ZEBRA)

        self.tree.bind("<Double-1>", lambda e: self.edit_entry())
        self.tree.bind("<Delete>", lambda e: self.delete_entry())
        self.tree.bind("<Control-c>", self._on_ctrl_c)

    # --- 状态栏 ---
    def _build_statusbar(self) -> None:
        bar = ttk.Frame(self, style="Bar.TFrame", padding=(22, 8, 22, 10))
        bar.pack(fill="x", side="bottom")
        self.status = ttk.Label(bar, text="", style="Soft.TLabel", anchor="w")
        self.status.pack(side="left")
        self._update_status()

    def _on_resize(self, event: tk.Event) -> None:
        """
        窗口变大时换更大的立绘；顶部栏高度跟着立绘走。

        只在"选中的素材文件变了"时才重建图片 —— 既避免每次 Configure 都
        重新解码 PNG，又保证不会因为阈值判重把该换的档位吞掉。
        """
        if event.widget is not self:
            return
        budget = int(self.winfo_height() * 0.26)
        budget = max(self.HERO_MIN + 30, min(self.HERO_MAX, budget))
        target = budget - 20                     # 给上下留白

        path = th.pick_mascot(target)
        if path is not None and path == self._mascot_path:
            return
        self._mascot_path = path
        self._mascot_size = target

        img = th.mascot_photo(self, path)
        if img is None:
            return
        self._mascot_img = img                   # 防 GC
        try:
            h, w = img.height(), img.width()
        except Exception:
            h, w = target, target // 2

        self.hero.configure(height=max(self.HERO_MIN, h + 12))
        self.hero.pack_propagate(False)
        self.mascot.configure(image=img, text="")
        self.mascot.pack_configure(padx=(0, max(20, min(80, w // 3))))

    # ---------------- 数据刷新 ----------------

    def reload_from_disk(self, silent: bool = False) -> None:
        text = vs.read_vault_text()
        self.entries = vc.decrypt_vault(text, self.passphrase)
        self._refresh_table()
        if not silent:
            self._update_status("已从磁盘重载")

    def _visible(self) -> list[tuple[int, dict[str, Any]]]:
        needle = self.filter_text.get().strip().lower()
        out: list[tuple[int, dict[str, Any]]] = []
        for idx, entry in enumerate(self.entries):
            rec = entry["record"]
            if needle:
                hay = " ".join(str(rec.get(k, "")) for k in rec).lower()
                if needle not in hay:
                    continue
            out.append((idx, entry))
        return out

    def _refresh_table(self) -> None:
        if not hasattr(self, "tree"):
            return
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.tree_items.clear()

        for n, (idx, entry) in enumerate(self._visible()):
            rec = entry["record"]
            vals = (rec.get("site", ""), rec.get("username", ""),
                    rec.get("password", ""), rec.get("url", ""))
            iid = self.tree.insert("", "end", values=vals,
                                   tags=("even" if n % 2 else "odd",))
            self.tree_items[iid] = idx

        self._update_status()

    def _update_status(self, extra: str = "") -> None:
        if not hasattr(self, "status"):
            return
        parts = [
            "文件  %s" % vs.VAULT_FILE,
            "共 %d 条" % len(self.entries),
        ]
        if extra:
            parts.append(extra)
        self.status.configure(text="     ·     ".join(parts))

    def _selected_index(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree_items.get(sel[0])

    # ---------------- 编辑操作 ----------------

    def add_entry(self) -> None:
        dlg = EntryDialog(self, self.cfg)
        if dlg.result is None:
            return
        self.entries.append({
            "record": dlg.result,
            "ok": True,
            "foreign": False,
            "newly_encrypted": True,
            "plain": "",
        })
        self.save_to_disk()
        self._refresh_table()

    def edit_entry(self) -> None:
        idx = self._selected_index()
        if idx is None:
            messagebox.showinfo("未选中", "先在表格里选一条记录。", parent=self)
            return
        entry = self.entries[idx]

        dlg = EntryDialog(self, self.cfg, record=entry["record"])
        if dlg.result is None:
            return

        entry["record"] = dlg.result
        entry["ok"] = True
        entry["foreign"] = False
        entry["newly_encrypted"] = True
        self.save_to_disk()
        self._refresh_table()

    def delete_entry(self) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        name = self.entries[idx]["record"].get("site") or "(未命名)"
        if not messagebox.askyesno("确认删除",
                                    "删除「%s」？\n保存后不可恢复。" % name,
                                    parent=self):
            return
        del self.entries[idx]
        self.save_to_disk()
        self._refresh_table()

    def _on_ctrl_c(self, event: tk.Event) -> str:
        """Ctrl+C：没选中文字时，复制选中行的密码。"""
        if self.tree.selection():
            self.copy_field("password")
            return "break"
        return ""

    def copy_field(self, key: str) -> None:
        idx = self._selected_index()
        if idx is None:
            return
        value = self.entries[idx]["record"].get(key, "")
        if not value:
            return
        self.clipboard_clear()
        self.clipboard_append(value)
        seconds = int(self.cfg.get("clipboard_clear_seconds", 30) or 0)
        if self._clip_after:
            try:
                self.after_cancel(self._clip_after)
            except Exception:
                pass
        if seconds > 0:
            self._clip_after = self.after(seconds * 1000, self._clear_clipboard)
            self._update_status("%s 已复制，%d 秒后自动清空剪贴板" % (key, seconds))
        else:
            self._update_status("%s 已复制" % key)

    def _clear_clipboard(self) -> None:
        try:
            self.clipboard_clear()
            self.clipboard_append("")
        except Exception:
            pass
        self._clip_after = None
        self._update_status("剪贴板已清空")

    # ---------------- 保存 ----------------

    def save_to_disk(self) -> None:
        if not self.passphrase:
            messagebox.showwarning("未解锁", "当前没有密钥，无法保存。", parent=self)
            return
        if not vs.vault_exists():
            vs.ensure_dirs()
        text = vc.encrypt_vault(self.entries, self.passphrase)
        vs.write_vault_text(text)
        for e in self.entries:
            if e.get("newly_encrypted"):
                e["foreign"] = False
            e["newly_encrypted"] = False
        self._update_status("已保存")

    # ---------------- 生命周期 ----------------

    def _on_close(self) -> None:
        self.passphrase = "\x00" * 32
        self.passphrase = ""
        self.entries = []
        self.destroy()


def selfcheck() -> int:
    """
    无界面自检：验证打包后的整条链路（素材、加解密、落盘、多密钥）。

    由 exe_selftest.py 用 `VaultMD.exe --selfcheck` 触发，
    结果写到 <数据目录>/selfcheck.txt，同时打印到 stdout。
    """
    import sys

    lines: list[str] = []
    ok = True

    def rec(name: str, cond: bool, extra: str = "") -> None:
        nonlocal ok
        ok = ok and bool(cond)
        lines.append(("  [ok]   " if cond else "  [FAIL] ") + name + ((" " + extra) if extra else ""))

    vs.ensure_dirs()

    # 1) 素材能不能在打包环境里找到并解码
    rec("素材目录存在", th.ASSETS.is_dir(), str(th.ASSETS))
    paths = th.mascot_paths()
    rec("立绘文件可枚举", len(paths) >= 1, "共 %d 张" % len(paths))

    root = tk.Tk()
    root.withdraw()
    th.apply_theme(root)
    photo = th.mascot_photo(root, paths[0] if paths else None)
    rec("立绘可解码为图片", photo is not None,
        "%dx%d" % (photo.width(), photo.height()) if photo is not None else "None")
    face = th.face_photo(root, 96)
    rec("解锁窗头像可加载", face is not None)
    root.destroy()

    # 2) 加解密往返
    entries = [{
        "record": {"site": "exe-test-site", "username": "exe-test-user",
                   "password": "ExePw!2345", "url": "", "policy": ""},
        "ok": True, "foreign": False, "newly_encrypted": True, "plain": "",
    }]
    text = vc.encrypt_vault(entries, "exe-key")
    rec("加密产出非空", bool(text.strip()))

    # 3) 落盘 + 重载
    vs.write_vault_text(text)
    rec("vault.md 已写入", vs.vault_exists(), str(vs.VAULT_FILE))

    back = vc.decrypt_vault(vs.read_vault_text(), "exe-key")
    rec("正确密钥可读回", len(back) == 1 and back[0]["ok"]
        and back[0]["record"]["password"] == "ExePw!2345")

    # 4) 错密钥 -> 乱码但有条目，且不泄露密码
    wrong = vc.decrypt_vault(vs.read_vault_text(), "other-key")
    rec("错密钥仍显示条目", len(wrong) == 1 and not wrong[0]["ok"])
    rec("错密钥不泄露明文密码", wrong[0]["record"]["password"] != "ExePw!2345")

    # 5) 磁盘上不能有明文
    raw = vs.read_vault_text()
    rec("磁盘无明文", not any(s in raw for s in
                              ("exe-test-site", "exe-test-user", "ExePw!2345")))

    report = vs.DATA_DIR / "selfcheck.txt"
    body = "\n".join(lines + (["", "ALL OK"] if ok else ["", "FAILED"]))
    report.write_text(body, encoding="utf-8")
    print(body)
    print("report:", report)
    return 0 if ok else 1


def main() -> None:
    import sys

    vs.ensure_dirs()
    if not vs.CONFIG_FILE.is_file():
        vs.save_config(vs.DEFAULT_CONFIG)

    if "--selfcheck" in sys.argv:
        raise SystemExit(selfcheck())

    app = VaultApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
