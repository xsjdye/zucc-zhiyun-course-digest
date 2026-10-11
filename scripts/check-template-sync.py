#!/usr/bin/env python3
"""检查输出模板在仓库各文件间是否同步（v2 · 框架优先 + 双轨分层 + 按段定位）。

单一事实源：`examples/note-template.md` 定义模板契约。
其余文件（SKILL.md / PROMPT.md / 两个示例）必须包含同样的字段、章节与【课】/【延】标记。

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

TEMPLATE_BLOCK_RE = re.compile(r"```markdown\n(.*?)```", re.S)

# v2 必现标题（要在 markdown 模板块内出现；变量「第 N 段」单列）
REQUIRED_HEADINGS = [
    "骨架",
    "重点",
    "待办",
    "遗漏",
]

# v2 双轨标记：每个走转写的文件至少各出现一次
DUAL_TRACK_MARKERS = ["【课】", "【延】"]

# 易混易错点是可选（自媒体类课不需要；概念重的课保留）
OPTIONAL_HEADINGS = ["易混易错点"]

# v2 新增 front matter 标记：每个 ```markdown 模板块内都要带
V2_FRONT_MATTER_KEYS = ["format: v2", "persona:"]

# 「第 N 段（...）」是变量计数的，逐个匹配
SEGMENT_RE = re.compile(r"^##\s*第\s*\d+\s*段[（(]", re.M)
ANY_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)

# 「附：转写勘误」等老格式被认为漂移——v2 已统一为「转写勘误」
LEGACY_HEADINGS_TO_FORBID = [
    "一、知识点梳理", "二、重点标注", "三、易混易错点",
    "四、课后待办", "五、本次遗漏", "附：转写勘误",
]

# 自包含文件的「取数能力」必须对齐：SKILL.md 与 PROMPT.md 都要提到同一组函数与选项。
# 加这条是因为真出过事——PROMPT.md 的读帧指导整整一轮没写进去（那次编辑在 SKILL 的断言上
# 失败整批中止了），而只校模板的检查器看不见这种执行步骤的漂移。
CAPABILITY_MARKERS = ["zccFetch", "zccRecent", "withFrames", "minSec"]
ALIGN_FILES = ["SKILL.md", "PROMPT.md"]

# 只有用转写的文件才要求「转写勘误」+【课】/【延】。降级示例没有转写，但【延】仍要。
FULL_PATH_FILES = {
    "examples/note-template.md",
    "SKILL.md",
    "PROMPT.md",
    "examples/usage-example.md",
}


def template_block(text):
    """按行解析 ```markdown 围栏；嵌套 ```mermaid 视作内容层、不收尾。

    用「是否处于内层围栏」一个布尔即可：开标签（```mermaid）置 True，
    纯 ``` 行若在 True 状态就关内层、若在 False 状态就是外层收尾。
    """
    in_block = False
    inside = False
    out = []
    for line in text.split('\n'):
        if not in_block:
            if line.startswith('```') and line.lstrip('`').startswith('markdown'):
                in_block = True
            continue
        s = line.strip()
        if s.startswith('```'):
            # 纯反引号（3 个或更多）= 闭合围栏；有其他字符 = 开新围栏
            if all(c == '`' for c in s) and len(s) >= 3:
                if not inside:
                    return '\n'.join(out)
                inside = False
                out.append(line)
            else:
                inside = True
                out.append(line)
        else:
            out.append(line)
    return '\n'.join(out)


def extract_headings(blk):
    return [m.group(1).strip() for m in ANY_H2_RE.finditer(blk)]


def main():
    ap = argparse.ArgumentParser(description="检查输出模板在各文件间是否同步")
    ap.add_argument("-v", "--verbose", action="store_true", help="同时打印基准契约内容")
    args = ap.parse_args()

    base_path = ROOT / BASELINE
    if not base_path.exists():
        print(f"❌ 基准文件不存在：{BASELINE}", file=sys.stderr)
        return 2

    base_blk = template_block(base_path.read_text(encoding="utf-8"))
    base_headings = extract_headings(base_blk)
    base_segments = SEGMENT_RE.findall(base_blk)
    if not base_segments:
        print(f"❌ 基准文件里没解析到「第 N 段」标题，模板写法可能被改动：{BASELINE}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"基准契约（来自 {BASELINE}）")
        print(f"  必现 ## 标题：{', '.join(REQUIRED_HEADINGS)}")
        print(f"  双轨标记：{', '.join(DUAL_TRACK_MARKERS)}（每个走转写的文件各出现至少一次）")
        print(f"  front matter 标记：{', '.join(V2_FRONT_MATTER_KEYS)}（每个 ```markdown 模板块内都要带）")
        print(f"  可选：{', '.join(OPTIONAL_HEADINGS)}（缺不报错）")
        print(f"  禁用（v1 残留）：{', '.join(LEGACY_HEADINGS_TO_FORBID)}")
        print()

    drifted = []

    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            drifted.append((rel, ["文件不存在"]))
            print(f"❌ {rel}\n     - 文件不存在")
            continue

        text = p.read_text(encoding="utf-8")
        # 允许同文件里 ```markdown 块出现多遍（SKILL.md 有两处）；
        # 只要第一块满足契约即可。后面「示例对话」中的块是示例不是契约。
        first_blk = template_block(text)
        headings = extract_headings(first_blk)
        problems = []

        # 必现 ## 标题（用前缀匹配，容忍标题带括号/说明文字）
        for h in REQUIRED_HEADINGS:
            if not any(x == h or x.startswith(h + '（') or x.startswith(h + ' ') or x.startswith(h + '(') for x in headings):
                problems.append(f"缺必现标题「{h}」")

        # 可选章节只警告
        optional_present = [h for h in OPTIONAL_HEADINGS if h in headings]
        optional_missing = [h for h in OPTIONAL_HEADINGS if h not in headings]

        # v1 残留禁用
        legacy_present = [h for h in LEGACY_HEADINGS_TO_FORBID if h in headings]
        if legacy_present:
            problems.append(f"残留 v1 标题「{'、'.join(legacy_present)}」")

        # v2 front matter 标记
        for k in V2_FRONT_MATTER_KEYS:
            if k not in first_blk:
                problems.append(f"缺 front matter 标记「{k}」")

        # 双轨标记（走转写的文件必须有）
        if rel in FULL_PATH_FILES:
            for m in DUAL_TRACK_MARKERS:
                if m not in text:
                    problems.append(f"缺双轨标记「{m}」")

        # 至少一段「第 N 段（...）」
        if not SEGMENT_RE.search(first_blk):
            problems.append("缺「第 N 段（HH:MM–HH:MM）」结构")

        if problems:
            drifted.append((rel, problems))
            print(f"❌ {rel}")
            for m in problems:
                print(f"     - {m}")
            for m in optional_present:
                print(f"     - i 「{m}」可选但已出现，OK")
            if optional_missing:
                print(f"     - i 「{'、'.join(optional_missing)}」可选，未出现，OK")
        else:
            extra = []
            for m in optional_present:
                extra.append(f"「{m}」可选已出现")
            for m in optional_missing:
                extra.append(f"「{m}」可选未出现")
            print(f"✅ {rel}  ({'; '.join(extra) if extra else '无可选章节'})")

    # 自包含文件的能力标记对齐（SKILL 与 PROMPT 必须同组出现）
    present = {}
    for rel in ALIGN_FILES:
        fp = ROOT / rel
        if fp.exists():
            txt = fp.read_text(encoding="utf-8")
            present[rel] = set(m for m in CAPABILITY_MARKERS if m in txt)
    if len(present) == len(ALIGN_FILES):
        allm = set(CAPABILITY_MARKERS)
        union = set().union(*present.values())
        for rel, ms in present.items():
            miss = (union - ms)
            if miss:
                drifted.append((rel, ["缺能力标记：%s（同组文件里有）" % '、'.join(sorted(miss))]))
                print(f"❌ {rel}")
                print(f"     - 缺能力标记：{'、'.join(sorted(miss))}（另一个自包含文件里有，说明执行步骤漂移）")

    print()
    if drifted:
        print(f"发现 {len(drifted)} 个文件与模板不同步。")
        print(f"改模板时请同步修改：{BASELINE} 以及上面列出的文件。")
        return 1

    print("全部同步 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())