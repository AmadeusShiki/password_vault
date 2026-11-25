# -*- coding: utf-8 -*-
"""
build.py -- 用 PyInstaller 打包

用法：
    python build.py              # 目录版 dist/VaultMD/（默认，推荐）
    python build.py --onefile    # 单文件 dist/VaultMD.exe

为什么默认改成目录版：
  onefile 启动时要先把自身解包到 %TEMP% 下的 _MEIxxxxxx 目录，这一步会被
  杀毒软件 / 终端防护 / 受限账户策略拦截，直接抛
      [PYI-xxxx:ERROR] Could not create temporary directory!
  而且每次启动都解包 20MB，慢且占空间。
  目录版把这些文件摊在 dist/VaultMD/ 里，启动不解包、不碰临时目录，
  兼容性最好。

两种模式的路径规则：
  - 素材：打进包，运行时从 sys._MEIPASS（onefile）或 exe 同级读取；
  - 数据：一律落在 exe 所在目录的 vault_data/，不会跑到 %TEMP%。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTRY = HERE / "vault_app.py"
NAME = "VaultMD"

#: 这些模块只服务于开发/测试，不打包
EXCLUDES = (
    "test_vault", "smoke_gui", "demo_shot", "demo_mixed", "demo_unlock",
    "make_assets", "crop_shot", "migrate_v1_to_v2", "exe_selftest",
    "run_exe_check", "build",
    "numpy", "pytest", "matplotlib", "IPython", "pandas", "scipy",
)


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("缺少 pyinstaller，先跑： python -m pip install pyinstaller")
        return 2

    for f in ("vault_app.py", "vault_crypto.py", "vault_store.py", "vault_theme.py"):
        if not (HERE / f).is_file():
            print("缺少模块:", f)
            return 2

    icon = HERE / "assets" / "app_icon.ico"
    onefile = "--onefile" in sys.argv          # 默认目录版

    args = [
        sys.executable, "-m", "PyInstaller",
        str(ENTRY),
        "--name", NAME,
        "--noconfirm",
        "--clean",
        "--noconsole" if "--console" not in sys.argv else "--console",
        "--onefile" if onefile else "--onedir",
        "--hidden-import", "cryptography.hazmat.primitives.kdf.scrypt",
        "--hidden-import", "cryptography.hazmat.primitives.ciphers.aead",
        "--collect-submodules", "cryptography",
        # 看板娘素材（vault_theme.py 从 _MEIPASS/assets 或 exe 同级 assets 读）
        "--add-data", "%s%s%s" % (HERE / "assets", os.pathsep, "assets"),
    ]

    if icon.is_file():
        args += ["--icon", str(icon)]

    for mod in EXCLUDES:
        args += ["--exclude-module", mod]

    print("模式:", "单文件" if onefile else "目录版")
    print("running:", " ".join(args))
    rc = subprocess.call(args, cwd=str(HERE))
    if rc != 0:
        print("打包失败 rc=", rc)
        return rc

    dist = HERE / "dist"
    if onefile:
        target = dist / (NAME + ".exe")
        runnable = NAME + ".exe"
        hint = ("⚠ 单文件版启动时会解包到 %%TEMP%%，若被安全软件拦截会报\n"
                "   'Could not create temporary directory!'，此时请改用目录版。\n")
    else:
        target = dist / NAME / (NAME + ".exe")
        runnable = NAME + "\\" + NAME + ".exe"
        hint = ""

    print("\n产物:", target)
    if not target.exists():
        print("没找到产物，检查 dist/ 目录")
        return 1

    folder = target.parent
    total = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
    print("大小: %.1f MB（整目录）" % (total / (1024 * 1024)))

    # 顺手把示例数据目录建好，首次运行就有 config.json
    data_dir = folder / "vault_data"
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)

    readme = folder / "使用说明.txt"
    readme.write_text(
        "VaultMD · 本地密码库\n"
        "=====================\n\n"
        "1. 双击 %s 启动。\n"
        "2. 首次运行会在同目录生成 vault_data\\vault.md（加密后的库）\n"
        "   和 vault_data\\config.json（窗口尺寸、剪贴板超时、密码规则模板）。\n"
        "3. 想换机器：把整个文件夹（含 vault_data）复制过去即可。\n"
        "4. 程序不做自动备份，磁盘上只有一个 vault_data\\vault.md。\n"
        "   需要留历史版本请自己复制该文件，它永远是密文。\n"
        "5. 忘记密钥无法恢复，请自行保管。\n\n"
        "%s" % (runnable, hint),
        encoding="utf-8",
    )
    print("说明:", readme)
    return 0


if __name__ == "__main__":
    sys.exit(main())
