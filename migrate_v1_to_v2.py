# -*- coding: utf-8 -*-
"""
migrate_v1_to_v2.py -- 把旧版（块式 v1）数据迁移成新版（行式 v2）

v1：一条记录 = 一个 `---BEGIN-ENTRY--- salt/nonce/body ---END-ENTRY---` 块，
    明文是 base64 字段拼成的 JSON。
v2：一条记录 = 一行 `salt.nonce.body`，明文是 `VPMD2<US>k=v<US>...`。

迁移方式：**用你自己的密钥解密再重新加密**（所以必须给密钥）。
好处是 v1 的明文格式和 v2 不一样也能干净转换，成文里不含任何 v1 残留；
代价是用错密钥的那些条目迁移后依然是乱码（它们本来就是别的密钥加密的，
密钥对了再跑一次同样的命令不影响已迁移的行 —— 已迁移的行会被当作 v2 识别出来）。

用法：
    python migrate_v1_to_v2.py                 # 就地迁移 vault_data/vault.md，运行时会问密钥
    python migrate_v1_to_v2.py -k mysecret     # 直接给密钥（注意命令行历史会留痕）
    python migrate_v1_to_v2.py --in a.md --out b.md -k mysecret
    python migrate_v1_to_v2.py --dry-run -k mysecret
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import sys
from pathlib import Path

import vault_crypto as vc
import vault_store as vs

V1_BEGIN = "---BEGIN-ENTRY---"
V1_END = "---END-ENTRY---"


# ---------------------------------------------------------------------------
# v1 解析
# ---------------------------------------------------------------------------

def _parse_v1_blocks(text: str) -> list[dict[str, str]] | None:
    if V1_BEGIN not in text:
        return None

    blocks: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if line == V1_BEGIN:
            current = {}
            continue
        if line == V1_END:
            if current is not None:
                blocks.append(current)
            current = None
            continue
        if current is not None and ":" in line:
            k, _, v = line.partition(":")
            k = k.strip()
            if k in ("salt", "nonce", "body"):
                current[k] = v.strip()

    if current is not None:      # 末尾缺 END 行也救回来
        blocks.append(current)
    return blocks


def _v1_open(block: dict[str, str], passphrase: str) -> tuple[str, bool]:
    """解一个 v1 块。返回 (明文, 是否真的成功)。"""
    try:
        salt = base64.b64decode(block.get("salt", ""))
        nonce = base64.b64decode(block.get("nonce", ""))
        body = base64.b64decode(block.get("body", ""))
    except Exception:
        return "", False
    if not salt or len(nonce) != vc.NONCE_LEN or len(body) < 16:
        return "", False

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = vc.derive_key(passphrase, salt)
        return AESGCM(key).decrypt(nonce, body, None).decode("utf-8"), True
    except Exception:
        return "", False


def _v1_plaintext_to_record(text: str) -> dict[str, str]:
    """v1 明文是 {"site": "<b64>", ...} 的 JSON。"""
    out = vc.default_record()
    try:
        payload = json.loads(text)
    except Exception:
        return out
    if not isinstance(payload, dict):
        return out
    for k, v in payload.items():
        if k == "__v":
            continue
        try:
            out[str(k)] = base64.b64decode(str(v)).decode("utf-8")
        except Exception:
            out[str(k)] = ""
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def convert(text: str, passphrase: str) -> tuple[str, int, int, int]:
    """
    v1 全文 -> v2 全文。

    返回 (新文本, 成功转换数, 用该密钥解不开而原样保留的数, 损坏丢弃的数)

    "解不开"的块保留原来的 salt/nonce/body，直接丢到 v2 里当一行 ——
    因为加密单元没变（salt+nonce+GCM 密文），换成密钥后照样能解开。
    """
    blocks = _parse_v1_blocks(text)
    if blocks is None:
        raise SystemExit("这个文件里没有 ---BEGIN-ENTRY---，不是 v1 格式，无需迁移。")

    lines: list[str] = list(vc.HEADER_LINES)
    lines.append("")

    converted = kept = dropped = 0
    for block in blocks:
        salt, nonce, body = (block.get("salt", ""), block.get("nonce", ""),
                             block.get("body", ""))
        try:
            for part in (salt, nonce, body):
                base64.b64decode(part, validate=True)
        except Exception:
            dropped += 1
            continue
        if not salt or not nonce or not body:
            dropped += 1
            continue

        plain, ok = _v1_open(block, passphrase)
        if ok:
            rec = _v1_plaintext_to_record(plain)
            lines.append(vc.seal_line(vc.record_to_plaintext(rec), passphrase))
            converted += 1
        else:
            # 别的密钥加密的块：密文原样搬过去，只是换个行格式
            lines.append("%s.%s.%s" % (salt, nonce, body))
            kept += 1

    return "\n".join(lines) + "\n", converted, kept, dropped


def main() -> int:
    ap = argparse.ArgumentParser(description="v1 块式数据 -> v2 行式数据")
    ap.add_argument("--in", dest="src", default=None, help="源文件，默认 vault_data/vault.md")
    ap.add_argument("--out", dest="dst", default=None, help="目标文件，默认就地覆盖源文件")
    ap.add_argument("-k", "--key", dest="key", default=None, help="解密密钥（不给就交互输入）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    args = ap.parse_args()

    src = Path(args.src) if args.src else vs.VAULT_FILE
    dst = Path(args.dst) if args.dst else src

    if not src.is_file():
        print("找不到源文件:", src)
        return 2

    text = src.read_text(encoding="utf-8", errors="replace")
    if V1_BEGIN not in text:
        print("这个文件里没有 v1 块标记，看起来已经是 v2 行式格式，无需迁移。")
        return 0

    key = args.key
    if key is None and not args.dry_run:
        key = getpass.getpass("解密密钥（输入不显示）: ")
    if key is None:
        key = ""

    new_text, converted, kept, dropped = convert(text, key)

    print("源文件     :", src)
    print("已重新加密 :", converted)
    print("原样搬运   :", kept, "（该密钥解不开，密文原样保留，换密钥仍可读）")
    if dropped:
        print("损坏丢弃   :", dropped)
    print("目标格式   : v2（一行一条密文）")

    if args.dry_run:
        print("\n--- 预览 ---")
        for line in new_text.split("\n")[:6]:
            print(line[:100] + ("..." if len(line) > 100 else ""))
        print("\n[dry-run] 未写盘")
        return 0

    if dst == src:
        # 迁移是不可逆的（明文格式变了），就地覆盖前先自己存一份原文件。
        # 这里不用 vs 的任何备份功能 —— 程序整体不提供自动备份。
        keep = src.with_suffix(src.suffix + ".v1.bak")
        if not keep.exists():
            keep.write_bytes(src.read_bytes())
            print("原文件备份 :", keep)
    dst.write_text(new_text, encoding="utf-8", newline="\n")
    print("\n已写入     :", dst)

    # 迁移后自检
    check = vc.decrypt_vault(new_text, key)
    ok = sum(1 for e in check if e["ok"])
    print("校验       : 用该密钥读回 %d 条 / 共 %d 行" % (ok, len(check)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
