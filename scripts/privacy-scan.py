#!/usr/bin/env python3
"""上传前隐私扫描器 —— 往公开仓库推任何东西之前必跑。

为什么需要它：课堂笔记里天然含有**第三方个人信息**（老师真实姓名、点名环节里的
同学姓名、教室、课表、选课标识）。这些东西一旦被推上公开仓库，泄露的不只是你自己，
还有那些从没同意过的同学 —— 后者比前者严重得多。

检查两类东西：
  1. 通用 PII 模式：手机号、身份证、QQ/学校邮箱、token 形态长随机串、本地用户目录
  2. 自定义敏感词：从 privacy-keywords.txt 读取（你自己 + 老师 + 同学姓名、教室代号等）

用法：
    python3 scripts/privacy-scan.py                # 扫整个仓库
    python3 scripts/privacy-scan.py --strict       # 连"提示级"也算失败
    python3 scripts/privacy-scan.py --selftest     # 自检扫描器本身有没有失效

敏感词清单（不要提交它自己）：
    printf '%s\n' "你自己的名字" "老师甲" "同学乙" > privacy-keywords.txt

退出码：0 = 干净可上传；1 = 有阻断级命中；2 = 参数/环境错误
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 不扫描的文件（本脚本自身含规则正则，会被自己命中）
SELF_EXCLUDE = {"scripts/privacy-scan.py"}

KEYWORDS_FILE = ROOT / "privacy-keywords.txt"

# ── 阻断级：命中就不该上传 ──────────────────────────────────────
BLOCK_PATTERNS = [
    ("中国大陆手机号", re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("身份证号", re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")),
    ("疑似 token/密钥（20+ 位随机串）",
     re.compile(r"(?i)\b(?:[a-f0-9]{32,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,})\b")),
    ("本地用户目录绝对路径", re.compile(r"(?:/Users/|/home/)[a-z0-9_.-]+/[^\s'\"`)]*")),
    ("Windows 用户目录绝对路径", re.compile(r"[A-Za-z]:\\\\?Users\\\\[A-Za-z0-9_.-]+")),
]

# ── 提示级：可能是故意的，要你确认 ──────────────────────────────
WARN_PATTERNS = [
    ("QQ 邮箱", re.compile(r"\b\d{8,11}@qq\.com\b")),
    ("学校邮箱", re.compile(r"\b[\w.\-]+@hzcu\.edu\.cn\b")),
    ("教室编号", re.compile(r"\b文\d-\d{3}\b")),
    ("真实 sub_id / course_id", re.compile(r"(?i)\b(?:sub_id|course_id)\s*[=:]\s*\d{5,}")),
]

SCAN_SUFFIXES = {".md", ".py", ".sh", ".txt", ".json", ".yaml", ".yml",
                 ".toml", ".cfg", ".ini", ".html", ".css", ".js"}


def load_keywords():
    if not KEYWORDS_FILE.exists():
        return []
    words = []
    for line in KEYWORDS_FILE.read_text(encoding="utf-8").splitlines():
        w = line.strip()
        if w and not w.startswith("#"):
            words.append(w)
    return words


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(ROOT))
        if rel.startswith(".git/") or rel in SELF_EXCLUDE:
            continue
        if rel == "privacy-keywords.txt":
            continue
        if p.suffix.lower() not in SCAN_SUFFIXES and p.name not in {
                ".gitignore", ".gitattributes", "LICENSE"}:
            continue
        yield rel, p


def scan():
    """返回 (blocking, warnings) 两个列表。"""
    blocking, warnings = [], []
    keywords = load_keywords()

    for rel, path in iter_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for lineno, line in enumerate(text.splitlines(), 1):
            for label, pat in BLOCK_PATTERNS:
                if pat.search(line):
                    blocking.append((rel, lineno, label, line.strip()[:90]))
            for label, pat in WARN_PATTERNS:
                if pat.search(line):
                    warnings.append((rel, lineno, label, line.strip()[:90]))
            for kw in keywords:
                if kw in line:
                    blocking.append((rel, lineno, f"敏感词命中「{kw}」", line.strip()[:90]))

    return blocking, warnings, keywords


def report(blocking, warnings, keywords, strict):
    print("════════ 上传前隐私扫描 ════════")
    if keywords:
        kw_note = "已加载 %d 个" % len(keywords)
    else:
        kw_note = "⚠️ 未找到 privacy-keywords.txt（建议创建，见 --help）"
    print("  敏感词清单：%s" % kw_note)
    print()

    if blocking:
        print(f"❌ 阻断级命中 {len(blocking)} 处 —— 不要上传，先处理：")
        for rel, ln, label, snippet in blocking:
            print(f"   {rel}:{ln}  [{label}]")
            print(f"       {snippet}")
    else:
        print("✅ 无阻断级命中")
    print()

    if warnings:
        print(f"⚠️  提示级 {len(warnings)} 处（可能是故意的，请自行确认）：")
        for rel, ln, label, snippet in warnings:
            print(f"   {rel}:{ln}  [{label}]  {snippet[:60]}")
    else:
        print("✅ 无提示级命中")

    fail = bool(blocking) or (strict and bool(warnings))
    print()
    print("结论：", "❌ 不建议上传" if fail else "✅ 可以上传")
    return 1 if fail else 0


# 期望命中的级别：block=阻断级 / warn=提示级 / none=不该命中
SELFTEST_SAMPLES = [
    ("手机号", "联系 13800138000 报名", "block"),
    ("身份证", "证号 110101200001011234", "block"),
    ("本地路径", "见 /Users/zhangsan/notes/a.md", "block"),
    ("token形态", "abcdef0123456789abcdef0123456789", "block"),
    ("QQ邮箱", "发到 123456789@qq.com", "warn"),
    ("教室编号", "文2-609 教室", "warn"),
    ("sub_id", "sub_id=2022610", "warn"),
    ("正常内容", "本讲介绍曝光铁三角与七种构图法", "none"),
]


def selftest():
    """验证扫描器本身有效 —— 一个从没命中过的扫描器等于没扫。"""
    print("════════ 扫描器自检 ════════")
    ok = True
    for label, text, expect in SELFTEST_SAMPLES:
        hit = any(pat.search(text) for _, pat in BLOCK_PATTERNS)
        warn = any(pat.search(text) for _, pat in WARN_PATTERNS)
        level = "block" if hit else ("warn" if warn else "none")
        good = (level == expect)
        ok = ok and good
        print(f"  {'✅' if good else '❌'} {label:<10} 期望={expect:<6} 实际={level}")
    # 敏感词路径单独测
    kw = "测试敏感人名"
    good = kw in f"今天 {kw} 来上课了"
    ok = ok and good
    print(f"  {'✅' if good else '❌'} {'敏感词匹配':<10} 期望=命中    实际={'命中' if good else '未命中'}")
    print()
    print("自检结论：", "✅ 扫描器有效" if ok else "❌ 扫描器规则失效，别信它的输出")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="上传前隐私扫描器")
    ap.add_argument("--strict", action="store_true", help="提示级也算失败")
    ap.add_argument("--selftest", action="store_true", help="自检扫描器规则是否有效")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    blocking, warnings, keywords = scan()
    return report(blocking, warnings, keywords, args.strict)


if __name__ == "__main__":
    sys.exit(main())
