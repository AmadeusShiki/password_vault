# -*- coding: utf-8 -*-
"""
crop_shot.py -- 把整屏截图裁成"只含应用窗口"的图，方便放到 README / 对比。

用法：
    python crop_shot.py _demo.png _demo_win.png            # 自动找非背景区域
    python crop_shot.py _demo.png out.png 60 40 1080 700   # 手动给框
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    src, dst = Path(sys.argv[1]), Path(sys.argv[2])

    from PIL import Image
    im = Image.open(src).convert("RGB")

    if len(sys.argv) >= 7:
        box = tuple(int(v) for v in sys.argv[3:7])
    else:
        # 自动：取"明显不是纯黑桌面"的区域
        import numpy as np
        a = np.asarray(im).astype(int)
        mask = a.sum(axis=2) > 120        # 亮于纯黑
        ys, xs = np.where(mask)
        if len(xs) == 0:
            print("没找到内容")
            return 1
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)

    out = im.crop(box)
    out.save(dst)
    print("wrote", dst, out.size, "box", box)
    return 0


if __name__ == "__main__":
    sys.exit(main())
