# -*- coding: utf-8 -*-
"""
test_vault.py -- 端到端自测（不弹 GUI，直接测行级存储的数据层）

覆盖：
  1. 整个文件无明文：站名/用户名/密码/备注一个都不落盘
  2. 正确密钥往返（含中文、含 FIELD_SEP 无法撞坏的怪字符）
  3. 错误密钥 -> 乱码但可显示、不抛异常、结果确定
  4. 行级混合密钥：同一个文件里第 1-2 行用 a、第 3 行用 b，
     输入 a -> 前两行可读第三行乱码；输入 b -> 反过来
  5. 用错密钥打开后新增一行再保存，不破坏其他密钥的行
  6. 空文件 / 损坏行 / 垃圾行 / 手加的注释行
  7. 明文导出
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="vaulttest-"))
os.environ["VAULT_DIR"] = str(TMP)

import vault_crypto as vc  # noqa: E402
import vault_store as vs   # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  [ok]  %s" % name)
    else:
        FAIL += 1
        print("  [FAIL] %s %s" % (name, detail))


def make_entry(site: str, user: str, pw: str) -> dict:
    return {
        "record": {"site": site, "username": user, "password": pw,
                   "url": "", "policy": "默认(强)"},
        "ok": True, "foreign": False, "newly_encrypted": True, "plain": "",
    }


def main() -> int:
    vs.ensure_dirs()
    print("data dir:", TMP)

    # ---- 1. 基础往返 + 全文件无明文 ----
    entries = [make_entry("github.com", "alice", "Gh!7xQ2p"),
               make_entry("银行A", "alice@mail", "B4nk#Pass2024"),
               make_entry("淘宝", "alice_tao", "tao@123456")]
    text = vc.encrypt_vault(entries, "key-A")
    vs.write_vault_text(text)

    raw = vs.VAULT_FILE.read_text(encoding="utf-8")
    for secret in ("github.com", "alice", "Gh!7xQ2p", "银行A", "淘宝"):
        check("明文不落盘: %s" % secret, secret not in raw)

    data_lines = [ln for ln in raw.split("\n") if ln.strip() and not ln.startswith("#")]
    check("一行一条记录", len(data_lines) == 3, str(len(data_lines)))
    check("每行都是 salt.nonce.body 三段",
          all(len(ln.split(".")) == 3 for ln in data_lines))

    back = vc.decrypt_vault(raw, "key-A")
    check("条目数一致", len(back) == 3)
    check("密码往返", back[1]["record"]["password"] == "B4nk#Pass2024")
    check("中文站名往返", back[1]["record"]["site"] == "银行A")

    # ---- 1b. 怪字符不破坏行结构 ----
    weird = make_entry("站点\n带换行\x1f带分隔符", "u\x00user", "p=w.d")
    wtext = vc.encrypt_vault([weird], "k")
    wback = vc.decrypt_vault(wtext, "k")
    check("换行/分隔符/等号都能往返",
          wback[0]["record"]["site"] == "站点\n带换行\x1f带分隔符"
          and wback[0]["record"]["password"] == "p=w.d",
          repr(wback[0]["record"]["site"]))

    # ---- 2. 错误密钥 ----
    wrong = vc.decrypt_vault(raw, "key-X")
    check("错密钥不崩且条目数一致", len(wrong) == 3)
    check("错密钥全部标记为不可读", all(not e["ok"] for e in wrong))
    check("错密钥也有内容显示", all(e["record"]["site"] for e in wrong))
    wrong2 = vc.decrypt_vault(raw, "key-X")
    check("错密钥结果确定", wrong[0]["record"]["site"] == wrong2[0]["record"]["site"])
    check("错密钥不泄露真密码", all(e["record"]["password"] != "Gh!7xQ2p" for e in wrong))

    # ---- 2b. 界面/数据里不能有任何"这是别的密钥加密的"之类提示 ----
    hints = ("其他密钥", "无法解读", "乱码", "由其他", "该行损坏", "格式无法识别",
             "非本程序", "v1", "migrate", "⟨")
    blob = "".join(str(e["record"]) for e in wrong)
    leaked = [h for h in hints if h in blob]
    check("乱码行不含任何提示性文字", not leaked, str(leaked))
    check("乱码行的每个字段都是原样乱码，无额外说明",
          all(not e["record"]["policy"] for e in wrong))

    # ---- 3. 行级混合密钥 ----
    vs.VAULT_FILE.unlink()
    md_a = vc.encrypt_vault(entries[:2], "a")
    md_b = vc.encrypt_vault(entries[2:], "b")
    # 拼起来：a 的两行 + b 的一行（去掉 b 的头部）
    b_lines = [ln for ln in md_b.split("\n") if ln.strip() and not ln.startswith("#")]
    mixed = md_a.rstrip("\n") + "\n" + "\n".join(b_lines) + "\n"
    vs.write_vault_text(mixed)

    ea = vc.decrypt_vault(mixed, "a")
    eb = vc.decrypt_vault(mixed, "b")
    check("密钥a：前2行可读", ea[0]["ok"] and ea[1]["ok"])
    check("密钥a：第3行乱码", not ea[2]["ok"])
    check("密钥b：前2行乱码", not eb[0]["ok"] and not eb[1]["ok"])
    check("密钥b：第3行可读", eb[2]["ok"])
    check("密钥a读出的内容正确", ea[1]["record"]["site"] == "银行A")
    check("密钥b读出的内容正确", eb[2]["record"]["site"] == "淘宝")

    # ---- 4. 用错密钥打开 + 新增一行 + 保存，不毁掉别人的行 ----
    ea.append(make_entry("新建站点", "bob", "NewPw!9"))
    text2 = vc.encrypt_vault(ea, "a")
    vs.write_vault_text(text2)

    again_a = vc.decrypt_vault(text2, "a")
    again_b = vc.decrypt_vault(text2, "b")
    check("原a的行仍在", again_a[0]["ok"] and again_a[1]["ok"] and not again_a[2]["ok"])
    check("新增行归属a", again_a[3]["ok"] and again_a[3]["record"]["site"] == "新建站点")
    check("b的行没被破坏", again_b[2]["ok"] and again_b[2]["record"]["site"] == "淘宝")
    check("b仍读不到a的新行", not again_b[3]["ok"])

    # ---- 5. 边界：空文件 / 损坏行 / 垃圾 ----
    check("空文件 -> 0 条", vc.decrypt_vault("", "x") == [])
    check("只有注释 -> 0 条", vc.decrypt_vault("# VPMD/2\n# x\n\n", "x") == [])

    broken = "# VPMD/2\n\nnot-a-token\n@@.@@.@@\nAAAA.BBBB.CCCC\n"
    be = vc.decrypt_vault(broken, "x")
    check("损坏行不崩", len(be) == 3 and not any(e["ok"] for e in be))
    check("损坏行也只显示乱码，无提示文字",
          all(not any(h in str(e["record"]) for h in ("损坏", "格式", "非本程序", "⟨"))
              for e in be))

    junk = "随便写点东西\n" + vc.seal_line(b"x", "x") + "\n手写的行\n"
    je = vc.decrypt_vault(junk, "x")
    check("手工垃圾文件不崩", len(je) == 3)

    # ---- 5b. 程序里不存在"导出明文"这条路（入口已被删掉） ----
    check("vault_app 没有导出入口", not hasattr(vc, "export_plaintext")
          and not hasattr(vs, "export_plaintext"))

    # ---- 6. 程序不做任何自动备份 ----
    vs.write_vault_text(text2)
    check("store 没有备份入口", not hasattr(vs, "backup_now"))
    check("store 没有 BACKUP_DIR", not hasattr(vs, "BACKUP_DIR"))
    check("数据目录里不会自动生成 backups/",
          not (vs.DATA_DIR / "backups").exists(),
          str(vs.DATA_DIR / "backups"))

    # ---- 7. 密码生成器合规性 ----
    pol = vc.PasswordPolicy(length=18, symbols_set="!@#")
    bad = 0
    for _ in range(200):
        pw = pol.generate()
        if not (any(c.isupper() for c in pw) and any(c.islower() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#" for c in pw)
                and len(pw) == 18):
            bad += 1
    check("生成器 200 次全部合规", bad == 0, "违规 %d 次" % bad)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        code = main()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(code)
