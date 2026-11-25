# -*- coding: utf-8 -*-
"""
vault_store.py -- vault.md 的磁盘读写层

职责：
  - 定位数据文件（默认 ./vault_data/vault.md，可用环境变量覆盖）
  - 原子写入
  - 站点密码策略模板的持久化（config.json）

不做任何加密逻辑，加密全在 vault_crypto.py。
不做任何备份 —— 程序只维护一个 vault.md，历史版本由用户自己管理。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import vault_crypto as vc


def _app_dir() -> Path:
    """
    程序所在目录（数据落在这里）。

    - 源码运行：本文件所在目录
    - PyInstaller onefile：exe 所在目录（__file__ 会指向 %TEMP% 下的解包目录，
      绝不能用它，否则数据会在程序退出时被清掉）
    - PyInstaller onedir：同上，exe 所在目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _app_dir()

#: 数据目录：优先环境变量 VAULT_DIR，否则 <程序目录>/vault_data
DATA_DIR = Path(os.environ.get("VAULT_DIR", APP_DIR / "vault_data"))

VAULT_FILE = DATA_DIR / "vault.md"
CONFIG_FILE = DATA_DIR / "config.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# vault.md 读写
# ---------------------------------------------------------------------------

def vault_exists() -> bool:
    return VAULT_FILE.is_file()


def read_vault_text() -> str:
    if not VAULT_FILE.is_file():
        return ""
    return VAULT_FILE.read_text(encoding="utf-8", errors="replace")


def write_vault_text(text: str) -> None:
    """
    原子写：先写临时文件 fsync，再 os.replace 覆盖，避免断电写坏。

    不做任何备份 —— 程序不保留历史副本。要备份请自己复制 vault.md。
    """
    ensure_dirs()

    tmp = VAULT_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, VAULT_FILE)


# ---------------------------------------------------------------------------
# 配置 / 密码策略模板
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "clipboard_clear_seconds": 30,
    "window": {"width": 1180, "height": 720},
    "policies": {
        # 名字 -> 规则 dict
        "默认(强)": vc.PasswordPolicy(length=20).to_dict(),
        "兼容老站(无特殊字符)": vc.PasswordPolicy(length=16, symbols=False).to_dict(),
        "纯数字PIN": vc.PasswordPolicy(length=6, upper=False, lower=False,
                                     digits=True, symbols=False).to_dict(),
        "银行/金融(24位)": vc.PasswordPolicy(length=24,
                                          symbols_set="!@#$%^&*").to_dict(),
    },
}


def load_config() -> dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # 深拷贝
    if CONFIG_FILE.is_file():
        try:
            user = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                for k, v in user.items():
                    if k == "policies" and isinstance(v, dict):
                        cfg["policies"].update(v)
                    elif k == "window" and isinstance(v, dict):
                        cfg["window"].update(v)
                    else:
                        cfg[k] = v
        except Exception:
            pass
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    ensure_dirs()
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, CONFIG_FILE)


def policy_by_name(cfg: dict[str, Any], name: str) -> vc.PasswordPolicy:
    raw = cfg.get("policies", {}).get(name)
    if not isinstance(raw, dict):
        return vc.PasswordPolicy()
    return vc.PasswordPolicy.from_dict(raw)
