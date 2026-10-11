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

# Windows / 被管道捕获时 locale 常是 GBK 或 C，直接 print 中文会 UnicodeEncodeError 崩掉。
# 这里强制把输出切成 UTF-8（编不出的字符降级成 ?），宁可显示乱码也不要让门禁跑不起来。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
ANY_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
TEMPLATE_BLOCK_RE = re.compile(r"```markdown\n(.*?)```", re.S)

# 只有「用到了课堂转写」时才必须出现的结构。降级示例（无转写）可以没有。
TRANSCRIPT_ONLY_HEADINGS = {"附：转写勘误"}
TRANSCRIPT_MARKERS = ["- 依据：", "｜转写 ", "｜课件帧 "]
# 声明自己走了转写的文件；其余按降级路径要求
FULL_PATH_FILES = {
    "examples/note-template.md",
    "SKILL.md",
    "PROMPT.md",
    "examples/usage-example.md",
}


def template_block(text):
    m = TEMPLATE_BLOCK_RE.search(text)
    return m.group(1) if m else text


def extract(text):
    """返回 (header 字段集合, 编号章节列表, 模板块内全部 ## 标题)。

    字段只从 `>` 引用行里取，避免把正文里的冒号误当模板字段。
    标题从 ```markdown 模板块内取，所以「附：转写勘误」这类非编号章节也在契约里——
    早先只比对「一、二、三…」，导致新增小节漂移检查不到。
    """
    fields = set()
    for line in text.splitlines():
        s = line.strip()
        if s.startswith(">"):
            fields |= set(FIELD_RE.findall(s))
    blk = template_block(text)
    sections = [m.group(1).strip() for m in SECTION_RE.finditer(blk)]
    headings = [m.group(1).strip() for m in ANY_H2_RE.finditer(blk)]
    return fields, sections, headings


def main():
    ap = argparse.ArgumentParser(description="检查输出模板在各文件间是否同步")
    ap.add_argument("-v", "--verbose", action="store_true", help="同时打印基准契约内容")
    args = ap.parse_args()

    base_path = ROOT / BASELINE
    if not base_path.exists():
        print(f"❌ 基准文件不存在：{BASELINE}", file=sys.stderr)
        return 2

    base_fields, base_sections, base_headings = extract(base_path.read_text(encoding="utf-8"))
    if not base_sections:
        print(f"❌ 基准文件里没解析到编号章节，模板写法可能被改动：{BASELINE}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"基准契约（来自 {BASELINE}）")
        print(f"  header 字段：{', '.join(sorted(base_fields))}")
        print(f"  章节序列：{' → '.join(base_sections)}")
        print(f"  全部 ## 标题：{', '.join(base_headings)}")
        print()

    drifted = []

    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            drifted.append((rel, ["文件不存在"]))
            print(f"❌ {rel}\n     - 文件不存在")
            continue

        text = p.read_text(encoding="utf-8")
        fields, sections, headings = extract(text)
        problems = []

        missing_fields = base_fields - fields
        if missing_fields:
            problems.append(f"缺 header 字段：{', '.join(sorted(missing_fields))}")

        # 标题契约：走转写的文件要求全部标题；降级文件豁免「附：转写勘误」
        required = list(base_headings)
        if rel not in FULL_PATH_FILES:
            required = [h for h in required if h not in TRANSCRIPT_ONLY_HEADINGS]
        missing_sections = [h for h in required if h not in headings]
        if missing_sections:
            problems.append(f"缺章节：{'、'.join(missing_sections)}")

        if rel in FULL_PATH_FILES:
            missing_markers = [k for k in TRANSCRIPT_MARKERS if k not in text]
            if missing_markers:
                problems.append(f"缺转写版结构标记：{', '.join(missing_markers)}")

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
