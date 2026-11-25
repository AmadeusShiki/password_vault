# -*- coding: utf-8 -*-
"""
shot_tool.py -- 只截应用窗口本身，绝不截桌面

全屏截图会把任务栏、聊天窗口、桌面图标、游戏画面一起拍进去。
这里统一用"按窗口坐标裁"的方式：

    grab_window(win) -> PIL.Image
        x = win.winfo_rootx(), y = win.winfo_rooty()
        w,h = win.winfo_width(), win.winfo_height()
        只截这块矩形，其余一律丢弃

于是产出的图里只有应用窗口，不含任何桌面内容。
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from typing import Optional


def grab_window(win: tk.Misc, pad: int = 0) -> Optional["object"]:
    """
    截取窗口自身区域（含标题栏以外的客户区）。

    返回 PIL.Image；失败返回 None。
    """
    try:
        from PIL import ImageGrab
    except Exception:
        return None

    try:
        win.update_idletasks()
        win.update()
    except Exception:
        pass

    x = win.winfo_rootx()
    y = win.winfo_rooty()
    w = win.winfo_width()
    h = win.winfo_height()
    if w <= 1 or h <= 1:
        return None

    box = (x - pad, y - pad, x + w + pad, y + h + pad)
    try:
        return ImageGrab.grab(bbox=box, all_screens=True)
    except TypeError:
        # 老版本 Pillow 没有 all_screens
        return ImageGrab.grab(bbox=box)
    except Exception:
        return None


def grab_with_titlebar(win: tk.Misc, extra_top: int = 30, inset: int = 6) -> Optional["object"]:
    """
    连带标题栏一起截，但严格限制在窗口矩形内。

    winfo_rooty 给的是客户区顶端，标题栏在它上面约 30px；
    底部和右侧各往里收 inset 像素，防止把窗口边框外的东西带进来
    （截图 API 有取整误差，很容易多拍一两行桌面）。
    """
    try:
        from PIL import ImageGrab
    except Exception:
        return None

    try:
        win.update_idletasks()
        win.update()
    except Exception:
        pass

    x = win.winfo_rootx()
    y = win.winfo_rooty()
    w = win.winfo_width()
    h = win.winfo_height()
    if w <= 1 or h <= 1:
        return None

    left = x
    top = max(0, y - extra_top)
    right = x + w
    bottom = y + h - inset      # 底部收进来，绝不吃到窗口外面
    if right <= left or bottom <= top:
        return None

    box = (left, top, right, bottom)
    try:
        return ImageGrab.grab(bbox=box, all_screens=True)
    except TypeError:
        return ImageGrab.grab(bbox=box)
    except Exception:
        return None


def save(img, path: Path, scale: int = 1) -> bool:
    """保存截图；scale>1 时先放大（小图放 README 里更清楚）。"""
    if img is None:
        return False
    try:
        if scale > 1:
            from PIL import Image
            img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
        img.save(path)
        return path.is_file()
    except Exception:
        return False


def settle(win: tk.Misc, times: int = 6, delay: float = 0.12) -> None:
    """让窗口把布局、重绘、after 回调都跑完再截。"""
    for _ in range(times):
        try:
            win.update_idletasks()
            win.update()
        except Exception:
            break
        time.sleep(delay)
