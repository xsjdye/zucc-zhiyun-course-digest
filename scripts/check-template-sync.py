#!/usr/bin/env python3
"""检查输出模板在仓库各文件间是否同步。

单一事实源：`examples/note-template.md` 定义模板契约（header 字段 + 章节序列）。
其余文件（SKILL.md / PROMPT.md / 两个示例）必须包含同样的字段与章节。

为什么要这个脚本：SKILL.md 与 PROMPT.md 必须**自包含**（同学可能只把单个文件丢给
AI），所以模板必然在多处重复。重复是设计使然、不能消除，但**漂移**可以自动发现。

用法：
    python3 scripts/check-template-sync.py            # 检查，输出结果
    python3 scripts/check-template-sync.py --verbose  # 连基准一起打印

退出码：
    0  全部同步
    1  发现漂移（有文件缺字段或缺章节）
    2  基准文件缺失或无法解析
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "examples/note-template.md"
TARGETS = [
    "SKILL.md",
    "PROMPT.md",
    "examples/usage-example.md",
    "examples/fallback-example.md",
]

FIELD_RE = re.compile(r"([\u4e00-\u9fa5]{2,8})\s*[：:]")
SECTION_RE = re.compile(r"^##\s*([一二三四五六七八九十]+、.+?)\s*$", re.M)


def extract(text):
    """返回 (header 字段集合, 章节标题列表)。

    字段只从 `>` 引用行里取，避免把正文里的冒号误当模板字段。
    章节只取「一、二、三…」编号形式的标题，忽略「填写说明」这类辅助标题。
    """
    fields = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            fields |= set(FIELD_RE.findall(s))
    sections = [m.group(1).strip() for m in SECTION_RE.finditer(text)]
    return fields, sections


def main():
    ap = argparse.ArgumentParser(description="检查输出模板在各文件间是否同步")
    ap.add_argument("-v", "--verbose", action="store_true", help="同时打印基准契约内容")
    args = ap.parse_args()

    base_path = ROOT / BASELINE
    if not base_path.exists():
        print(f"❌ 基准文件不存在：{BASELINE}", file=sys.stderr)
        return 2

    base_fields, base_sections = extract(base_path.read_text(encoding="utf-8"))
    if not base_sections:
        print(f"❌ 基准文件里没解析到编号章节，模板写法可能被改动：{BASELINE}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"基准契约（来自 {BASELINE}）")
        print(f"  header 字段：{', '.join(sorted(base_fields))}")
        print(f"  章节序列：{' → '.join(base_sections)}")
        print()

    drifted = []

    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            drifted.append((rel, ["文件不存在"]))
            print(f"❌ {rel}\n     - 文件不存在")
            continue

        fields, sections = extract(p.read_text(encoding="utf-8"))
        problems = []

        missing_fields = base_fields - fields
        if missing_fields:
            problems.append(f"缺 header 字段：{', '.join(sorted(missing_fields))}")

        missing_sections = [s for s in base_sections if s not in sections]
        if missing_sections:
            problems.append(f"缺章节：{', '.join(missing_sections)}")

        # 顺序检查：允许模板在同一文件里出现多遍（SKILL.md 就有「标准模板 + 示例」两处），
        # 所以只禁止真正的逆序——序号回退时必须是重新开始（回到第一段）
        idx = {s: i for i, s in enumerate(base_sections)}
        seq = [idx[s] for s in sections if s in idx]
        for a, b in zip(seq, seq[1:]):
            if b <= a and b != 0:
                problems.append(f"章节顺序不一致：实际 {' → '.join(sections)}")
                break

        if problems:
            drifted.append((rel, problems))
            print(f"❌ {rel}")
            for m in problems:
                print(f"     - {m}")
        else:
            print(f"✅ {rel}")

    print()
    if drifted:
        print(f"发现 {len(drifted)} 个文件与模板不同步。")
        print(f"改模板时请同步修改：{BASELINE} 以及上面列出的文件。")
        return 1

    print("全部同步 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
