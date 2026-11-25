# -*- coding: utf-8 -*-
"""
vault_theme.py -- 界面主题：配色、字体、ttk 样式、看板娘素材

看板娘：Q 版 DeepSeek 鲸鱼娘（三头身、蓝色渐变卷发、鲸鳍耳、白女仆头箍）。
  形象来源：上善无形（原角色）/ ZipZipPipe（DeepSeek 女仆形象改编）
  设定图整理：鲸鱼娘开源资产库 · TreapGoGo
  参考页：https://genderswapai.com/zh-CN/ai-gijinka/deepseek/chibi

这里只负责"长什么样"，不含任何加密或存储逻辑。
"""

from __future__ import annotations

import tkinter as tk
import sys
from pathlib import Path
from tkinter import ttk
from typing import Any


def _assets_dir() -> Path:
    """
    素材目录（只读资源，跟着程序走）。

    三种情况都要覆盖：
      - 源码运行：<本文件目录>/assets
      - onefile：<解包临时目录>/assets —— 由 sys._MEIPASS 给出
      - onedir ：<exe 同级>/assets —— 没有 _MEIPASS，用 sys.executable 的父目录
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        p = Path(bundle) / "assets"
        if p.is_dir():
            return p

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        for cand in (exe_dir / "assets", exe_dir / "_internal" / "assets"):
            if cand.is_dir():
                return cand

    return Path(__file__).resolve().parent / "assets"


ASSETS = _assets_dir()

# ---------------------------------------------------------------------------
# 配色：取自立绘本身（藏青女仆裙 + 蓝色渐变发 + 珍珠白围裙 + 金线）
# ---------------------------------------------------------------------------

INK = "#1B2A4A"        # 主文字：深藏青
INK_SOFT = "#5A6B88"   # 次文字
NAVY = "#232D5C"       # 女仆裙藏青
NAVY_DEEP = "#161C3A"
BLUE = "#3D6FE0"       # 立绘亮蓝
BLUE_LIGHT = "#7FA8F5"
BLUE_PALE = "#EAF1FF"  # 浅蓝底
GOLD = "#C9A227"       # 裙摆金线
PEARL = "#FDFDFB"      # 围裙白
MIST = "#F6F8FD"       # 窗体底
LINE = "#D8E2F5"       # 分隔线
ZEBRA = "#F2F6FF"      # 斑马纹

# 字体：优先 Windows 自带、对中文友好的几套
FONT_UI = ("Microsoft YaHei UI", 10)
FONT_BODY = ("Microsoft YaHei UI", 10)
FONT_SMALL = ("Microsoft YaHei UI", 9)
FONT_TINY = ("Microsoft YaHei UI", 8)
FONT_TITLE = ("Microsoft YaHei UI", 12, "bold")
FONT_HERO = ("Microsoft YaHei UI", 13, "bold")
FONT_MONO = ("Cascadia Mono", 10)


# ---------------------------------------------------------------------------
# 看板娘素材
# ---------------------------------------------------------------------------

def mascot_paths() -> list[Path]:
    """按大->小列出立绘。GUI 会挑第一个放得下的。"""
    out = []
    for size in (380, 320, 260, 200, 176, 128):
        p = ASSETS / ("mika_%d.png" % size)
        if p.is_file():
            out.append(p)
    return out


def pick_mascot(max_height: int) -> Path | None:
    """挑一张高度不超过 max_height 的立绘；都放不下就挑最小的。"""
    best: Path | None = None
    best_h = -1
    for p in mascot_paths():                    # 已经是大 -> 小
        try:
            from PIL import Image
            with Image.open(p) as im:
                h = im.size[1]
        except Exception:
            try:
                h = int(p.stem.split("_")[1])
            except Exception:
                continue
        if h <= max_height and h > best_h:
            best, best_h = p, h
    if best is None:
        paths = mascot_paths()
        best = paths[-1] if paths else None
    return best


def face_photo(master: tk.Misc, size: int = 48) -> Any:
    """圆形头像（解锁窗用）。没有 Pillow 就返回 None，调用方跳过。"""
    src = ASSETS / "mika_head.png"
    if not src.is_file():
        return None
    try:
        from PIL import Image, ImageDraw, ImageTk
    except Exception:
        return None

    with Image.open(src) as im:
        # mika_head.png 在 make_assets.py 里已经按脸居中裁好并套过圆形蒙版，
        # 这里只做缩放 —— 再套一次椭圆会把圆边缘裁歪、留下毛边。
        im = im.convert("RGBA")

        # 透明边去掉一点，让头像在卡片上更饱满
        bbox = im.getbbox()
        if bbox:
            pad = max(1, int((bbox[2] - bbox[0]) * 0.02))
            im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                          min(im.size[0], bbox[2] + pad),
                          min(im.size[1], bbox[3] + pad)))

        im = im.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(im, master=master)


def mascot_photo(master: tk.Misc, path: Path | None) -> Any:
    """加载立绘为 PhotoImage。没有 Pillow 时退化为 tk.PhotoImage。"""
    if path is None or not path.is_file():
        return None
    try:
        from PIL import Image, ImageTk
        with Image.open(path) as im:
            return ImageTk.PhotoImage(im.convert("RGBA"), master=master)
    except Exception:
        pass
    try:
        return tk.PhotoImage(file=str(path), master=master)
    except Exception:
        return None


def apply_icon(win: tk.Wm) -> None:
    """窗口 + 任务栏图标。"""
    ico = ASSETS / "app_icon.ico"
    png = ASSETS / "app_icon.png"
    try:
        if ico.is_file():
            win.iconbitmap(default=str(ico))
    except Exception:
        pass
    try:
        if png.is_file():
            img = tk.PhotoImage(file=str(png), master=win)
            win.iconphoto(True, img)
            setattr(win, "_icon_ref", img)      # 防止被 GC 掉
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ttk 样式
# ---------------------------------------------------------------------------

def apply_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")     # clam 才能让我们自由改配色
    except tk.TclError:
        pass

    root.configure(bg=MIST)
    root.option_add("*Font", FONT_BODY)
    root.option_add("*TearOff", False)

    # --- 基本容器 ---
    style.configure(".", background=MIST, foreground=INK, font=FONT_BODY)
    style.configure("TFrame", background=MIST)
    style.configure("Card.TFrame", background=PEARL, relief="flat")
    style.configure("Hero.TFrame", background=NAVY, relief="flat")
    style.configure("Bar.TFrame", background=MIST)

    style.configure("TLabel", background=MIST, foreground=INK, font=FONT_BODY)
    style.configure("Card.TLabel", background=PEARL, foreground=INK)
    style.configure("Soft.TLabel", background=MIST, foreground=INK_SOFT, font=FONT_SMALL)
    style.configure("CardSoft.TLabel", background=PEARL, foreground=INK_SOFT,
                    font=FONT_SMALL)
    style.configure("Title.TLabel", background=PEARL, foreground=NAVY, font=FONT_TITLE)
    style.configure("Hero.TLabel", background=NAVY, foreground=PEARL, font=FONT_HERO)
    style.configure("HeroSoft.TLabel", background=NAVY, foreground=BLUE_LIGHT,
                    font=FONT_SMALL)
    style.configure("Field.TLabel", background=PEARL, foreground=INK_SOFT,
                    font=FONT_SMALL)

    # --- 按钮 ---
    style.configure("TButton", padding=(14, 7), relief="flat", borderwidth=0,
                    background=BLUE_PALE, foreground=INK, font=FONT_BODY)
    style.map("TButton",
              background=[("pressed", BLUE_LIGHT), ("active", "#DCE8FF")],
              foreground=[("disabled", "#9AA8C0")])

    style.configure("Primary.TButton", background=BLUE, foreground="#FFFFFF",
                    font=("Microsoft YaHei UI", 10, "bold"), padding=(20, 8))
    style.map("Primary.TButton",
              background=[("pressed", NAVY), ("active", "#4E7FEF")],
              foreground=[("disabled", "#AEBEE0")])

    style.configure("Ghost.TButton", background=MIST, foreground=INK_SOFT,
                    padding=(12, 6))
    style.map("Ghost.TButton", background=[("active", BLUE_PALE)])

    style.configure("Danger.TButton", background="#FBECEF", foreground="#A33349",
                    padding=(12, 6))
    style.map("Danger.TButton", background=[("active", "#F6DCE2")])

    style.configure("Hero.TButton", background="#2E3D6E", foreground=PEARL,
                    padding=(14, 7), borderwidth=0)
    style.map("Hero.TButton", background=[("active", "#3A4C86")])

    # --- 输入框 ---
    style.configure("TEntry", fieldbackground="#FFFFFF", foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE,
                    insertcolor=BLUE, padding=7)
    style.map("TEntry", bordercolor=[("focus", BLUE)],
              lightcolor=[("focus", BLUE)], darkcolor=[("focus", BLUE)])

    style.configure("TCombobox", fieldbackground="#FFFFFF", background="#FFFFFF",
                    foreground=INK, arrowcolor=BLUE, bordercolor=LINE, padding=5)
    style.map("TCombobox", fieldbackground=[("readonly", "#FFFFFF")],
              bordercolor=[("focus", BLUE)])

    style.configure("TSpinbox", fieldbackground="#FFFFFF", foreground=INK,
                    bordercolor=LINE, arrowcolor=BLUE, padding=5)

    style.configure("TCheckbutton", background=PEARL, foreground=INK_SOFT,
                    font=FONT_SMALL)
    style.map("TCheckbutton", background=[("active", PEARL)])

    style.configure("TSeparator", background=LINE)

    # --- 卡片与分组 ---
    style.configure("Card.TLabelframe", background=PEARL, bordercolor=LINE,
                    relief="solid", borderwidth=1)
    style.configure("Card.TLabelframe.Label", background=PEARL, foreground=NAVY,
                    font=("Microsoft YaHei UI", 9, "bold"))

    # --- 表格 ---
    style.configure("Vault.Treeview",
                    background="#FFFFFF", fieldbackground="#FFFFFF",
                    foreground=INK, rowheight=34, borderwidth=0, font=FONT_BODY)
    style.map("Vault.Treeview",
              background=[("selected", "#D9E7FF")],
              foreground=[("selected", NAVY)])
    style.configure("Vault.Treeview.Heading",
                    background=BLUE_PALE, foreground=NAVY,
                    font=("Microsoft YaHei UI", 9, "bold"),
                    relief="flat", padding=(10, 8))
    style.map("Vault.Treeview.Heading",
              background=[("active", "#DCE8FF")])

    # --- 滚动条 ---
    style.configure("Vertical.TScrollbar", background="#DCE4F5",
                    troughcolor=MIST, bordercolor=MIST, arrowcolor=BLUE,
                    relief="flat", width=12)
    style.configure("Horizontal.TScrollbar", background="#DCE4F5",
                    troughcolor=MIST, bordercolor=MIST, arrowcolor=BLUE,
                    relief="flat")
    style.map("Vertical.TScrollbar", background=[("active", BLUE_LIGHT)])
    style.map("Horizontal.TScrollbar", background=[("active", BLUE_LIGHT)])

    # --- 进度条（解锁时的忙碌提示）---
    style.configure("Gold.Horizontal.TProgressbar", background=GOLD,
                    troughcolor="#E8EDF9", bordercolor="#E8EDF9",
                    lightcolor=GOLD, darkcolor=GOLD, thickness=4)

    return style
