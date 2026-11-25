# -*- coding: utf-8 -*-
"""
make_assets.py -- 生成界面用的素材（看板娘立绘的多种尺寸 + 圆角图标）

为什么需要这一步：
  tkinter 的 PhotoImage 只能原样显示 PNG，不能缩放（缩放会糊，且 PNG 缩放要
  zoom/subsample 整数倍）。Pillow 有的话就用它做高质量 LANCZOS 缩放；
  没有 Pillow 时程序仍能跑，只是不显示立绘（不是崩溃）。

产物（全部放进 assets/）：
  mika_128.png / mika_200.png / mika_260.png   去白底、带柔和阴影的立绘
  mika_320.png                                 大窗模式用的
  app_icon.ico                                 窗口/任务栏图标
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"

SOURCE = ASSETS / "deepseek-front.png"

#: 立绘尺寸池。GUI 会按窗口高度挑一个够用的
SIZES = (128, 176, 200, 260, 320, 380)


def _load():
    from PIL import Image
    return Image


def cutout(im):
    """
    白底 -> 透明底（边界洪水填充法）。

    早期版本用的是"越接近白越透明"，结果把围裙、头箍、脸这些**内部白色**
    也一起抠掉了，人物只剩深色轮廓，看起来像骷髅。

    正确做法：只把"从画面四边可以连通到的浅色区域"判定为背景，
    被角色包围起来的白色（围裙、荷叶边、脸）必须保留。
    """
    from PIL import Image, ImageFilter
    import numpy as np
    from collections import deque

    rgb = im.convert("RGB")
    arr = np.asarray(rgb).astype(np.int16)
    h, w = arr.shape[:2]

    # 1) 标记"接近白"的像素。白底实测约 (252,252,252)，边缘有轻微渐变。
    near_white = (np.abs(arr - 252).max(axis=2) <= 14)

    # 2) 从四边向内做 BFS，连通到的才是真背景
    is_bg = np.zeros((h, w), dtype=bool)
    dq: deque[tuple[int, int]] = deque()

    def seed(y: int, x: int) -> None:
        if near_white[y, x] and not is_bg[y, x]:
            is_bg[y, x] = True
            dq.append((y, x))

    for x in range(w):
        seed(0, x)
        seed(h - 1, x)
    for y in range(h):
        seed(y, 0)
        seed(y, w - 1)

    while dq:
        y, x = dq.popleft()
        if y > 0:
            seed(y - 1, x)
        if y + 1 < h:
            seed(y + 1, x)
        if x > 0:
            seed(y, x - 1)
        if x + 1 < w:
            seed(y, x + 1)

    # 3) 生成 alpha：背景 0，其余 255。边界再羽化一点，避免锯齿。
    alpha = np.where(is_bg, 0, 255).astype(np.uint8)
    out = np.dstack([arr.astype(np.uint8), alpha])
    img = Image.fromarray(out, mode="RGBA")

    a = img.getchannel("A")
    a = a.filter(ImageFilter.GaussianBlur(0.8))
    img.putalpha(a)

    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def find_face(cut, fallback_w: int, fallback_h: int) -> tuple[int, int, int]:
    """
    找出脸部方块 (left, top, side)。

    定位依据是**眼睛连线**，而不是"整体重心"——
    肤色重心会把下巴、脖子、领口都算进去，明显偏低；虹膜高光又会掺进头发高光，
    偏高。只有瞳孔最稳：它是最暗的那一小块深蓝。

    做法：在脸的中段范围内取"暗 + 偏蓝"的像素，按左右两半分别算重心，
    两个重心连线的中点就是眼睛连线的中点。

    找不到（或换角色）就退回几何估计，至少不会崩。
    """
    import numpy as np

    w, h = cut.size
    arr = np.asarray(cut).astype(int)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    alpha = arr[..., 3]
    mx = arr[..., :3].max(axis=2)

    # 瞳孔：暗、偏蓝、不透明。范围要卡紧 ——
    # 立绘里头发阴影、领结、裙子都是"暗蓝"，只有 25%~45% 这条带里才是眼睛。
    pupil = (mx < 110) & (b > r + 10) & (alpha > 128)
    band = np.zeros_like(pupil)
    band[int(h * 0.25):int(h * 0.45), :] = True
    pupil = pupil & band

    ys, xs = np.where(pupil)
    if len(xs) < 100:
        cx, cy = fallback_w, fallback_h
    else:
        left_sel = xs < w / 2
        ly = int(np.median(ys[left_sel])) if left_sel.any() else int(np.median(ys))
        ry = int(np.median(ys[~left_sel])) if (~left_sel).any() else ly
        lx = int(np.median(xs[left_sel])) if left_sel.any() else int(np.median(xs))
        rx = int(np.median(xs[~left_sel])) if (~left_sel).any() else lx

        cx = (lx + rx) // 2
        cy = (ly + ry) // 2          # 眼睛连线的中点

    # 取景边长：含头箍、蝴蝶结和一点肩膀
    side = int(min(w, h * 0.36))

    # 眼睛连线中点 = 圆形中心，不做任何上下偏移
    left = max(0, min(w - side, cx - side // 2))
    top = max(0, min(h - side, cy - side // 2))
    return left, top, side


def make_avatar(cut, size: int = 256):
    """把立绘裁成正方形头像（眼睛连线中点 = 圆心）。"""
    from PIL import Image, ImageDraw, ImageFilter

    left, top, side = find_face(cut, cut.size[0] // 2, int(cut.size[1] * 0.36))

    # 严格正方形直接裁，不再外扩 pad。
    # 之前用 pad 四边等量外扩，一旦某边顶到画面边界（max(0, ...)）就会被截短，
    # 结果贴到 canvas 上时内容整体偏移 —— 眼睛就不在圆心了。
    head = cut.crop((left, top, left + side, top + side))
    if head.size[0] != head.size[1]:
        sq = max(head.size)
        canvas = Image.new("RGBA", (sq, sq), (0, 0, 0, 0))
        canvas.paste(head, ((sq - head.size[0]) // 2, (sq - head.size[1]) // 2), head)
        head = canvas

    head = head.resize((size, size), Image.LANCZOS)

    # 圆形蒙版（轻微羽化，避免锯齿）
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(0.6))
    head.putalpha(Image.composite(head.getchannel("A"), Image.new("L", (size, size), 0), mask))
    return head


def add_soft_shadow(img, pad: int = 10):
    """加一圈柔和投影 + 浅色光晕，贴在深蓝底上不至于糊成一团。"""
    from PIL import Image, ImageFilter, ImageEnhance

    # 深色背景上小图会显脏：先轻微提亮+加饱和
    img = ImageEnhance.Brightness(img).enhance(1.14)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.10)

    w, h = img.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))

    # 1) 背后一圈冷白/浅蓝光晕，把轮廓从深蓝底上"托"起来
    halo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    glow = Image.new("RGBA", (w, h), (176, 205, 255, 120))
    halo.paste(glow, (pad, pad), img.getchannel("A"))
    halo = halo.filter(ImageFilter.GaussianBlur(pad * 1.5))
    canvas = Image.alpha_composite(canvas, halo)

    # 2) 再叠一层很淡的深色落影，增加厚度
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sil = Image.new("RGBA", (w, h), (10, 20, 50, 80))
    shadow.paste(sil, (pad, pad + 4), img.getchannel("A"))
    shadow = shadow.filter(ImageFilter.GaussianBlur(pad * 0.6))
    canvas = Image.alpha_composite(canvas, shadow)

    # 3) 主体
    canvas.paste(img, (pad, pad), img)
    return canvas


def main() -> int:
    if not SOURCE.is_file():
        print("找不到立绘:", SOURCE)
        return 2

    Image = _load()
    im = Image.open(SOURCE)
    cut = add_soft_shadow(cutout(im), pad=16)

    cut.save(ASSETS / "mika_src.png")

    for size in SIZES:
        w, h = cut.size
        scale = size / max(w, h)
        resized = cut.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                             Image.LANCZOS)
        out = ASSETS / ("mika_%d.png" % size)
        resized.save(out)
        print("wrote", out.name, resized.size)

    # 窗口图标 / 解锁窗头像：按脸部位置裁，圆形蒙版
    head = make_avatar(cut, 256)
    head.save(ASSETS / "mika_head.png")
    head.save(ASSETS / "app_icon.png")
    try:
        head.save(ASSETS / "app_icon.ico",
                  sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print("wrote app_icon.ico")
    except Exception as exc:
        print("ico 生成失败（可以忽略）:", exc)

    return 0


if __name__ == "__main__":
    sys.exit(main())
