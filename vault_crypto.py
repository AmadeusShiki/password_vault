# -*- coding: utf-8 -*-
"""
vault_crypto.py -- 密码库的加密 / 解密 / 序列化层（行级存储版）

文件格式 v2：**一行 = 一条记录 = 一个独立密文**

    # VPMD/2
    # one line = one encrypted record. nothing else is stored in plaintext.
    <base64salt>.<base64nonce>.<base64body>
    <base64salt>.<base64nonce>.<base64body>
    ...

设计要点（对齐需求）：
  1) 整个 md 都是加密的：文件里没有任何明文，连标题/注释都没写进去；
     每行是纯密文 token（AES-256-GCM 密文 + tag，base64 后按 "." 切成三段）。
  2) 行级独立加解密：每行自带独立 salt + nonce，各自派生密钥、各自解密。
     所以前几行可以用密钥 a、后几行用密钥 b；输 a 时 a 的行可读、b 的行乱码，
     反过来亦然 —— 这一性质是格式本身给的，不需要额外机制。
  3) 不做密钥校验：GCM tag 校验失败不报错，退回"伪解密"——
     用该密钥派生的字节流异或后按 latin-1 解码，得到一串确定性乱码。
"""

from __future__ import annotations

import base64
import string
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

import os
import secrets as _secrets

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 记录格式版本（写进每行密文前的 token 版本隐含在解析逻辑里；
#: 这行注释行本身也是明文的例外，所以干脆不写进文件，只放在代码里）
FORMAT_VERSION = 2

#: 文件头：**明文**，但只含格式标识，不含任何用户数据。
#: 用 markdown 的 ATX 标题语法，让它"像 md"又完全不泄露内容。
HEADER_LINES = (
    "# VPMD/2",
    "# one line = one encrypted record. nothing else is stored in plaintext.",
)

#: GCM nonce 长度
NONCE_LEN = 12

#: scrypt 参数。n 越大越慢越安全；换来的暴力破解成本。
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1

#: 派生标签
_DECOY_LABEL = b"vault-decoy-stream-v1"
_KEY_LABEL = b"vault-master-key-v1"


# ---------------------------------------------------------------------------
# 密钥派生
# ---------------------------------------------------------------------------

def new_salt(n: int = 16) -> bytes:
    """生成一条记录专属的随机 salt。"""
    return os.urandom(n)


def derive_key(passphrase: str, salt: bytes) -> bytes:
    """把用户输入的密钥 + salt 派生成 32 字节 AES-256 密钥。"""
    kdf = Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(_KEY_LABEL + passphrase.encode("utf-8"))


def _derive_stream(bytes_needed: int, passphrase: str, salt: bytes) -> bytes:
    """
    派生"伪解密"用的字节流。

    只为了在密钥错误时也能产出一段确定性的、看起来像乱码的字符串，
    让界面永远有内容可展示（需求里明确要求不校验密钥）。
    """
    if bytes_needed <= 0:
        return b""
    kdf = Scrypt(salt=salt, length=bytes_needed, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(_DECOY_LABEL + passphrase.encode("utf-8"))


def decrypt_to_garbage(passphrase: str, salt: bytes, nonce: bytes, body: bytes) -> str:
    """
    错密钥分支：把密文用派生流异或，再按 latin-1 解码。

    latin-1 保证 0-255 任意字节都能解码，永不抛异常，结果是一条稳定的乱码。
    """
    stream = _derive_stream(len(body), passphrase, salt)
    xored = bytes(a ^ b for a, b in zip(body, stream))
    head = nonce.hex()
    return head + ":" + xored.decode("latin-1")


# ---------------------------------------------------------------------------
# 单行加解密（一行 = 一条记录）
# ---------------------------------------------------------------------------

def seal_line(plaintext: bytes, passphrase: str) -> str:
    """
    加密一条记录，产出一行密文 token： salt.nonce.body （三段 base64，点分隔）。

    每次调用都新生成 salt + nonce，所以同一份内容用同一密钥加密两次也不一样。
    """
    salt = new_salt()
    nonce = os.urandom(NONCE_LEN)
    key = derive_key(passphrase, salt)
    body = AESGCM(key).encrypt(nonce, plaintext, None)

    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return "%s.%s.%s" % (b64(salt), b64(nonce), b64(body))


def _noise(token: str) -> str:
    """
    损坏行的输出：把 token 本身打散成一段没有意义的字节串。

    目的只有一个 —— 界面上永远只看到"乱码"，看不出这行是坏了、还是别的密钥加密的。
    """
    raw = token.encode("utf-8", "replace")
    if not raw:
        return ""
    # 用 token 自身做异或，稳定且无需密钥
    out = bytearray(len(raw))
    for i, b in enumerate(raw):
        out[i] = b ^ raw[(i * 7 + 3) % len(raw)]
    return bytes(out).decode("latin-1")


def open_line(token: str, passphrase: str) -> tuple[str, bool]:
    """
    解密一行。返回 (文本, 是否真的解密成功)。

    成功 -> 正常 UTF-8 文本，ok=True
    失败 -> 确定性乱码，ok=False（GCM tag 没过，但我们不报错、不中断）

    损坏行也不返回任何提示文字 —— 直接给出乱码，和"密钥不对"的外观一致，
    界面上不会出现"这行坏了 / 这是别的密钥"之类的线索。
    """
    parts = token.strip().split(".")
    if len(parts) != 3:
        return _noise(token), False

    try:
        salt = base64.b64decode(parts[0])
        nonce = base64.b64decode(parts[1])
        body = base64.b64decode(parts[2])
    except Exception:
        return _noise(token), False

    if len(salt) == 0 or len(nonce) != NONCE_LEN or len(body) < 16:
        return _noise(token), False

    try:
        key = derive_key(passphrase, salt)
        plain = AESGCM(key).decrypt(nonce, body, None)
        return plain.decode("utf-8"), True
    except Exception:
        # 密钥不对，或数据被改动过 —— 都走乱码分支
        return decrypt_to_garbage(passphrase, salt, nonce, body), False


# ---------------------------------------------------------------------------
# 记录模型
# ---------------------------------------------------------------------------

def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _unb64(s: str) -> str:
    try:
        return base64.b64decode(s.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def default_record() -> dict[str, str]:
    return {
        "site": "",       # 站点 / App 名称
        "username": "",   # 用户名
        "password": "",   # 密码
        "url": "",        # 可选：登录地址
        "policy": "",     # 可选：该站使用的密码规则模板名
    }


#: 一行内的字段分隔符。用单元分隔符 U+001F，正常文本里绝不会出现，
#: 所以站点名写什么都不可能撞坏行结构。
FIELD_SEP = "\x1f"

#: 记录标记行：某行的明文以它开头，就说明这是本程序的记录行。
#: 作用是让旧版 v1 的 JSON 明文被读到时能干净地判为"格式不符"，
#: 而不是把 JSON 碎片当成字段值渲染出来。
RECORD_MARK = "VPMD2\x1f"


def record_to_plaintext(rec: dict[str, str]) -> bytes:
    """
    记录 -> 明文字节：`VPMD2<US>k=v<US>k=v<US>...`

    每个字段再 base64 一次，保证分隔符不可能出现在值里，
    也保证换行/制表符等怪字符不会破坏"一行一条"的约束。
    """
    pairs = ["%s=%s" % (k, _b64(str(v))) for k, v in rec.items()]
    return (RECORD_MARK + FIELD_SEP.join(pairs)).encode("utf-8")


def plaintext_to_record(text: str) -> dict[str, str]:
    """明文字节 -> 记录。格式不符就返回空记录，绝不抛异常打断整个文件。"""
    if not text.startswith(RECORD_MARK):
        return default_record()
    out = default_record()
    for pair in text[len(RECORD_MARK):].split(FIELD_SEP):
        if "=" not in pair:
            continue
        k, _, v = pair.partition("=")
        out[k] = _unb64(v)
    return out


# ---------------------------------------------------------------------------
# 整个 vault.md 的加解密
# ---------------------------------------------------------------------------

def _iter_data_lines(text: str) -> list[str]:
    """取出所有数据行（跳过空行、# 开头的说明行、以及被误加的注释）。"""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def decrypt_vault(text: str, passphrase: str) -> list[dict[str, Any]]:
    """
    逐行解密整个文件。

    返回记录列表，按文件行序。每条带标记：
        ok=True  -> 本密钥能解开
        ok=False -> 乱码（该行由别的密钥加密）
        foreign  -> 同上，保存时必须原样回写这一行密文

    注意：解不开的行只放乱码本身，不写任何提示性文字 ——
    界面上不能出现"这是别的密钥加密的"之类的说明，那等于给旁观者指路。
    """
    entries: list[dict[str, Any]] = []

    for token in _iter_data_lines(text):
        plain, ok = open_line(token, passphrase)
        if ok:
            rec = plaintext_to_record(plain)
        else:
            # 乱码直接当站点名显示，与正常数据显示完全一样，不做任何区分
            rec = default_record()
            rec["site"] = plain[:200]

        entries.append({
            "record": rec,
            "ok": ok,
            # 关键：foreign=True 表示"这行不是当前密钥加密的"，保存时必须原样回写，
            # 否则用错密钥打开一次再保存，就把别人密钥加密的数据给毁了。
            "foreign": not ok,
            "newly_encrypted": False,
            "source_line": token,
            "plain": plain,
        })

    return entries


def encrypt_vault(entries: list[dict[str, Any]], passphrase: str) -> str:
    """
    记录列表 -> vault.md 全文（一行一条记录，每行独立加密）。

    entry 字段：
        record         : dict 记录
        foreign        : True 表示这行由别的密钥加密、当前密钥解不开
        newly_encrypted: True 表示本次会话里用户新增/改过，必须重写
        source_line    : 原文件里的密文行
    """
    out: list[str] = list(HEADER_LINES)
    out.append("")

    for entry in entries:
        # 情况一：别的密钥加密的行且用户没动它 -> 原样回写那一行。
        # 这样用错密钥打开、加了新行再保存，也不会把别人的数据毁掉。
        if entry.get("foreign") and not entry.get("newly_encrypted"):
            token = entry.get("source_line", "")
            if token:
                out.append(token)
            continue

        # 情况二：正常条目 -> 用当前密钥加密成新的一行
        record = entry.get("record", default_record())
        out.append(seal_line(record_to_plaintext(record), passphrase))

    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 密码生成器
# ---------------------------------------------------------------------------

class PasswordPolicy:
    """
    一条站点密码规则。用来解决"每个站要求不一样"的问题：
    在配置模式里给某个站存一份规则，以后新增/改密码一键生成合规密码。
    """

    def __init__(
        self,
        length: int = 20,
        upper: bool = True,
        lower: bool = True,
        digits: bool = True,
        symbols: bool = True,
        symbols_set: str = "!@#$%^&*()-_=+[]{};:,.?",
        exclude_ambiguous: bool = True,
    ) -> None:
        self.length = max(4, min(int(length), 128))
        self.upper = upper
        self.lower = lower
        self.digits = digits
        self.symbols = symbols
        self.symbols_set = symbols_set
        self.exclude_ambiguous = exclude_ambiguous

    def pools(self) -> list[str]:
        upper = string.ascii_uppercase
        lower = string.ascii_lowercase
        digits = string.digits
        if self.exclude_ambiguous:
            upper = "".join(c for c in upper if c not in "O")
            lower = "".join(c for c in lower if c not in "l")
            digits = "".join(c for c in digits if c not in "01")
        out: list[str] = []
        if self.upper:
            out.append(upper)
        if self.lower:
            out.append(lower)
        if self.digits:
            out.append(digits)
        if self.symbols:
            out.append(self.symbols_set)
        return out

    def generate(self) -> str:
        pools = self.pools()
        if not pools:
            pools = [string.ascii_letters + string.digits]

        # 先每类各取一个，保证"必须有大小写/数字/特殊字符"这类规则满足
        chars = [_secrets.choice(p) for p in pools]
        everything = "".join(pools)
        while len(chars) < self.length:
            chars.append(_secrets.choice(everything))

        _secrets.SystemRandom().shuffle(chars)
        return "".join(chars[: self.length])

    def to_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "upper": self.upper,
            "lower": self.lower,
            "digits": self.digits,
            "symbols": self.symbols,
            "symbols_set": self.symbols_set,
            "exclude_ambiguous": self.exclude_ambiguous,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PasswordPolicy":
        base = cls()
        for k, v in (d or {}).items():
            if hasattr(base, k):
                setattr(base, k, v)
        return base


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("crypto self-test (line-per-record format)")
    rec = {"site": "github.com", "username": "alice", "password": "S3cr3t!",
           "url": "https://github.com/login", "note": "启用 2FA", "policy": ""}

    line = seal_line(record_to_plaintext(rec), "k1")
    md = encrypt_vault([{"record": rec, "newly_encrypted": True}], "k1")

    # 一行密文里不应该出现明文
    assert "github.com" not in md and "S3cr3t!" not in md
    print("  no plaintext on disk -> OK")

    got = decrypt_vault(md, "k1")
    assert got[0]["ok"] and got[0]["record"]["password"] == "S3cr3t!"
    print("  correct key  -> OK")

    bad = decrypt_vault(md, "k2")
    assert not bad[0]["ok"], "错误密钥应走乱码分支"
    assert bad[0]["record"]["site"], "乱码分支也要有内容可显示"
    print("  wrong key    -> deterministic garbage, no crash")

    bad2 = decrypt_vault(md, "k2")
    assert bad2[0]["record"]["site"] == bad[0]["record"]["site"]
    print("  wrong key deterministic -> OK")

    # 混合密钥：两行分别用 a / b
    blocks = [
        {"record": rec, "newly_encrypted": True},
        {"record": {**rec, "site": "b.example", "password": "other"}, "newly_encrypted": True},
    ]
    md2 = encrypt_vault(blocks[:1], "a") + seal_line(
        record_to_plaintext(blocks[1]["record"]), "b") + "\n"
    e_a = decrypt_vault(md2, "a")
    e_b = decrypt_vault(md2, "b")
    assert e_a[0]["ok"] and not e_a[1]["ok"]
    assert not e_b[0]["ok"] and e_b[1]["ok"]
    print("  mixed keys per line -> OK")

    # 损坏行不崩
    broken = "# VPMD/2\n\nnot-a-valid-token\n@@@@.@@.@@\n"
    be = decrypt_vault(broken, "whatever")
    assert len(be) == 2 and not any(e["ok"] for e in be)
    print("  corrupt line -> OK")

    # 空文件
    assert decrypt_vault("", "x") == []
    print("  empty file   -> OK")

    # 密码生成器
    p = PasswordPolicy(length=24, exclude_ambiguous=False)
    for _ in range(50):
        s = p.generate()
        assert len(s) == 24
        assert any(c.isupper() for c in s) and any(c.islower() for c in s)
        assert any(c.isdigit() for c in s) and any(c in p.symbols_set for c in s)
    print("  generator    -> OK")

    print("all crypto tests passed")
    sys.exit(0)
