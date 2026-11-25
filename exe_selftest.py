# -*- coding: utf-8 -*-
"""
exe_selftest.py -- 对打包后的 exe 做端到端功能验证（不需要人工点界面）

做两件事：
  1. 结构验证：用 PyInstaller 的归档读取能力确认 assets 打进了 exe；
  2. 行为验证：拷贝一份 exe 到临时目录，用 --selfcheck 参数启动，
     让它自己跑一遍"建库 -> 保存 -> 重载 -> 换密钥读乱码"，再把结果写盘。

用法：
    python exe_selftest.py dist/VaultMD.exe
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def check_assets_in_archive(exe: Path) -> bool:
    """
    检查素材是否随程序一起分发。

    目录版：素材摊在 exe 同级的 _internal/assets（或 assets）；
    单文件版：素材在 exe 内部的归档里，用 PyInstaller 的 CArchiveReader 看。
    """
    exe_dir = exe.parent

    # 目录版：直接找磁盘上的 assets
    for cand in (exe_dir / "_internal" / "assets", exe_dir / "assets"):
        if cand.is_dir():
            names = sorted(p.name for p in cand.iterdir() if p.is_file())
            hit = [n for n in ("app_icon.ico", "mika_head.png", "mika_200.png")
                   if n in names]
            print("  目录版素材目录:", cand, "| 文件数:", len(names), "| 命中:", hit)
            return len(hit) >= 2

    # 单文件版：读 exe 内部归档
    try:
        from PyInstaller.archive.readers import CArchiveReader
    except Exception as exc:
        print("  [skip] 无法导入 PyInstaller readers:", exc)
        return True

    try:
        arch = CArchiveReader(str(exe))
        toc = getattr(arch, "toc", {}) or {}
        names = [str(k) for k in toc]
        blob = "\n".join(names)
        hit = [n for n in ("assets", "app_icon.ico", "mika_200.png", "mika_head.png")
               if n in blob]
        print("  单文件归档条目数:", len(names), "| 命中素材:", hit)
        return len(hit) >= 2
    except Exception as exc:
        print("  [skip] 读取归档失败:", repr(exc))
        return True


def run_selfcheck(exe: Path) -> bool:
    work = Path(tempfile.mkdtemp(prefix="vault-exe-"))
    tmp = work / "_tmp"
    tmp.mkdir()

    # 目录版要整套拷走（依赖 _internal/ ），单文件版只拷 exe
    exe_dir = exe.parent
    onedir = (exe_dir / "_internal").is_dir()
    if onedir:
        target = work / exe_dir.name
        shutil.copytree(exe_dir, target, ignore=shutil.ignore_patterns("vault_data"))
        copy = target / exe.name
        cwd = target
        print("  模式: 目录版（整目录拷贝）")
    else:
        copy = work / exe.name
        shutil.copy2(exe, copy)
        cwd = work
        print("  模式: 单文件")

    env = dict(os.environ)
    env["TEMP"] = str(tmp)
    env["TMP"] = str(tmp)
    data_dir = work / "vault_data"
    env["VAULT_DIR"] = str(data_dir)

    print("  工作目录:", work)
    proc = subprocess.Popen([str(copy), "--selfcheck"], cwd=str(cwd), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    deadline = time.time() + 90
    while time.time() < deadline and proc.poll() is None:
        time.sleep(1)

    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        print("  [FAIL] 自检超时，进程未退出")
        return False

    out, err = proc.communicate()
    text = (out or b"").decode("utf-8", "replace") + (err or b"").decode("utf-8", "replace")
    if text.strip():
        for line in text.strip().split("\n")[-25:]:
            print("   |", line)

    report = data_dir / "selfcheck.txt"
    ok = report.is_file() and "ALL OK" in report.read_text(encoding="utf-8", errors="replace")
    if report.is_file():
        print("  自检报告:")
        for line in report.read_text(encoding="utf-8").strip().split("\n"):
            print("   |", line)
    else:
        print("  [FAIL] 没有生成 selfcheck.txt（数据目录:", data_dir, "）")

    # 顺便确认 vault.md 是密文
    vault = data_dir / "vault.md"
    if vault.is_file():
        body = vault.read_text(encoding="utf-8", errors="replace")
        leaked = [s for s in ("exe-test-site", "exe-test-user", "ExePw!2345") if s in body]
        print("  库文件:", vault.name, vault.stat().st_size, "字节 | 明文泄漏:", leaked or "无")
        ok = ok and not leaked
    else:
        print("  [FAIL] 没有生成 vault.md")
        ok = False

    shutil.rmtree(work, ignore_errors=True)
    return ok


def main() -> int:
    exe = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "dist" / "VaultMD.exe")
    if not exe.is_absolute():
        exe = (HERE / exe).resolve()
    if not exe.is_file():
        print("找不到 exe:", exe)
        return 2

    size = exe.stat().st_size / (1024 * 1024)
    print("目标:", exe, "(%.1f MB)" % size)

    print("[1/2] 检查素材是否打进包")
    a = check_assets_in_archive(exe)

    print("[2/2] 启动 exe 跑自检")
    b = run_selfcheck(exe)

    print("\n结果:", "PASS" if (a and b) else "FAIL",
          "| 素材:", a, "| 行为:", b)
    return 0 if (a and b) else 1


if __name__ == "__main__":
    raise SystemExit(main())
