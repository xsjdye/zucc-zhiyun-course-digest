#!/usr/bin/env python3
"""检查输出模板在仓库各文件间是否同步（v2 · 框架优先 + 双轨分层 + 按段定位）。

单一事实源：`examples/note-template.md` 定义**单讲笔记**契约；`templates/course-INDEX.md`
定义**课程索引**契约（两种文档类型，字段不同，不能互相卡）。
其余文件必须包含同样的字段、章节与【课】/【延】标记。

为什么要这个脚本：SKILL.md 与 PROMPT.md 必须**自包含**（同学可能只把单个文件丢给
AI），所以模板必然在多处重复。重复是设计使然、不能消除，但**漂移**可以自动发现。

注意：同一文件里的**每个** ```markdown 块都会被校验——SKILL.md 的第六节模板与第九节
示例是两个块，只看第一块会给第二块放假绿灯（真出过事）。

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
    "templates/lecture.md",
    "examples/usage-example.md",
    "examples/fallback-example.md",
]

# 课程索引是**另一种文档类型**，契约源不同，不能拿单讲笔记的字段去卡它。
# 加这一组是因为真出过事——examples/course-index-example.md 曾经既不在任何 TARGETS 里、
# 也没人发现，等于新增的示例完全没人校。
INDEX_BASELINE = "templates/course-INDEX.md"
INDEX_TARGETS = ["examples/course-index-example.md"]
INDEX_REQUIRED_H2 = ["课程总纲", "课程综述", "课时表", "复习进度"]
INDEX_REVIEW_STAGES = ["知识点整体归纳", "对应专家分析", "导出结果"]
INDEX_FRONT_MATTER_KEYS = ["persona:", "course_id:"]


# v2 必现标题（要在 markdown 模板块内出现；变量「第 N 段」单列）
REQUIRED_HEADINGS = [
    "骨架",
    "重点",
    "待办",
    "遗漏",
]

# v2 双轨标记：每个走转写的文件至少各出现一次
DUAL_TRACK_MARKERS = ["【课】", "【延】"]

# 可选章节：缺了不报错，但**会被点名**（缺哪些写进括号里）。
# 「易混易错点」——自媒体类课不需要，概念重的课（古代汉语/数理）保留。
# 「转写勘误」——没拿到转写的课就没有这一节（如 fallback-example）。
# 注：早先「转写勘误」既不在必现也不在可选列表，等于**完全不被检查**，
# 而注释还写着"只有用转写的文件才要求"——注释描述了一个不存在的检查。
OPTIONAL_HEADINGS = ["易混易错点", "转写勘误"]

# v2 新增 front matter 标记：每个 ```markdown 模板块内都要带
V2_FRONT_MATTER_KEYS = ["format: v2", "persona:"]

# 「第 N 段（...）」是变量计数的，逐个匹配
SEGMENT_RE = re.compile(r"^##\s*第\s*\d+\s*段[（(]", re.M)
ANY_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)

# 「附：转写勘误」等老格式被认为漂移——v2 已统一为「转写勘误」
# v1 遗留词汇：带编号的标题 + **不带编号的术语**。
# 加裸术语是因为真出过事——SKILL/PROMPT 开头的「职责定义」列的是 v1 四项，
# 用的是不带编号的写法（`**知识点梳理**`），只禁「一、知识点梳理」的检查器看不见。
# 「易混易错点」不在列——它是 v2 的可选节，合法。
LEGACY_HEADINGS_TO_FORBID = [
    "一、知识点梳理", "二、重点标注", "三、易混易错点",
    "四、课后待办", "五、本次遗漏", "附：转写勘误",
    "知识点梳理", "重点标注", "本次遗漏", "课后待办",
]

# 自包含文件的「取数能力」必须对齐：SKILL.md 与 PROMPT.md 都要提到同一组函数与选项。
# 加这条是因为真出过事——PROMPT.md 的读帧指导整整一轮没写进去（那次编辑在 SKILL 的断言上
# 失败整批中止了），而只校模板的检查器看不见这种执行步骤的漂移。
CAPABILITY_MARKERS = ["zccFetch", "zccRecent", "withFrames", "minSec"]
ALIGN_FILES = ["SKILL.md", "PROMPT.md"]

# 双轨标记【课】/【延】只在这些文件里强制（降级示例没有转写，但【延】仍要）。
# 「转写勘误」不在此强制——它按 OPTIONAL_HEADINGS 处理：缺了只点名、不报错。
FULL_PATH_FILES = {
    "examples/note-template.md",
    "SKILL.md",
    "PROMPT.md",
    "templates/lecture.md",
    "examples/usage-example.md",
}


def template_blocks(text):
    """按行解析**所有**顶层 ```markdown 围栏块，遵循 CommonMark 的围栏长度规则。

    规则：闭合围栏必须**不短于**开启围栏。所以用 3 反引号开启时，块内再出现一行
    ``` 就会提前收尾——这正是真出过的事：外层 3 反引号里套 3 反引号，GitHub 上会
    渲染成"前半截代码块 + 后半截正文"。要安全包住 3 反引号的内层围栏，外层必须用
    4 反引号（`examples/note-template.md` 与 SKILL 第九节就是这么写的）。
    """
    blocks = []
    in_block = False
    open_len = 0
    out = []
    for line in text.split('\n'):
        if not in_block:
            if line.startswith('```') and line.lstrip('`').startswith('markdown'):
                in_block = True
                open_len = len(line) - len(line.lstrip('`'))
                out = []
            continue
        s = line.strip()
        if s and all(c == '`' for c in s) and len(s) >= open_len:
            blocks.append('\n'.join(out))
            in_block = False
            continue
        out.append(line)
    return blocks


def regions(text):
    """文件里代表「笔记 / 索引本体」的文本区。

    优先取 ```markdown 围栏块（可能多个）；一个都没有时退化为**整个文件**——
    `templates/*.md` 是直接填写的原始模板，本身不带围栏。
    """
    blocks = template_blocks(text)
    return blocks if blocks else [text]


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

    base_regs = regions(base_path.read_text(encoding="utf-8"))
    base_blk = "\n".join(base_regs)
    base_segments = SEGMENT_RE.findall(base_blk)
    if not base_segments:
        print(f"❌ 基准文件里没解析到「第 N 段」标题，模板写法可能被改动：{BASELINE}", file=sys.stderr)
        return 2

    if args.verbose:
        print(f"基准契约（来自 {BASELINE}）")
        print(f"  必现 ## 标题：{', '.join(REQUIRED_HEADINGS)}")
        print(f"  双轨标记：{', '.join(DUAL_TRACK_MARKERS)}（每个走转写的文件各出现至少一次）")
        print(f"  front matter 标记：{', '.join(V2_FRONT_MATTER_KEYS)}（每个块内都要带）")
        print(f"  可选：{', '.join(OPTIONAL_HEADINGS)}（缺不报错）")
        print(f"  禁用（v1 残留）：{', '.join(LEGACY_HEADINGS_TO_FORBID)}")
        print(f"  课程索引契约（来自 {INDEX_BASELINE}）")
        print(f"    必备 ## 标题：{', '.join(INDEX_REQUIRED_H2)}")
        print(f"    综述三段：{', '.join(INDEX_REVIEW_STAGES)}")
        print()

    drifted = []

    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            drifted.append((rel, ["文件不存在"]))
            print(f"❌ {rel}\n     - 文件不存在")
            continue

        text = p.read_text(encoding="utf-8")
        # 同一文件里的**每个** ```markdown 块都要满足契约；无围栏的原始模板
        # （templates/*.md）退化为整文件。只看第一块会给第二块放假绿灯——真出过事。
        regs = regions(text)
        multi = len(regs) > 1
        problems = []
        headings_all = []

        for i, blk in enumerate(regs, 1):
            tag = f"块#{i} " if multi else ""
            headings = extract_headings(blk)
            headings_all.extend(headings)

            # 必现 ## 标题（用前缀匹配，容忍标题带括号/说明文字）
            for h in REQUIRED_HEADINGS:
                if not any(x == h or x.startswith(h + '（') or x.startswith(h + ' ') or x.startswith(h + '(') for x in headings):
                    problems.append(f"{tag}缺必现标题「{h}」")

            # v2 front matter 标记（每个块都要带）
            for k in V2_FRONT_MATTER_KEYS:
                if k not in blk:
                    problems.append(f"{tag}缺 front matter 标记「{k}」")

            # 至少一段「第 N 段（...）」
            if not SEGMENT_RE.search(blk):
                problems.append(f"{tag}缺「第 N 段（HH:MM–HH:MM）」结构")

        # 可选章节只警告
        optional_present = [h for h in OPTIONAL_HEADINGS if h in headings_all]
        optional_missing = [h for h in OPTIONAL_HEADINGS if h not in headings_all]

        # v1 残留禁用：**扫全文件**，不只看 markdown 块。
        # 加这条是因为真出过事——SKILL.md 的「示例对话」曾是第二个块，还留着 v1 的
        # 一/二/三/四/五 章节名，而只查首块的检查器完全看不见。
        legacy_present = [h for h in LEGACY_HEADINGS_TO_FORBID if h in text]
        if legacy_present:
            problems.append(f"残留 v1 标题「{'、'.join(legacy_present)}」（全文件扫描）")

        # 双轨标记（走转写的文件必须有）
        if rel in FULL_PATH_FILES:
            for m in DUAL_TRACK_MARKERS:
                if m not in text:
                    problems.append(f"缺双轨标记「{m}」")

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

    # SKILL.md「红线」的条目编号必须 1..N 唯一递增。
    # 加这条是因为真出过事——凭据组后加了一条（登录重定向），但下面各组的编号没顺延，
    # 于是两个组都从 7 开始，「第 7 条」指向不明，而只校章节名的检查器看不见编号。
    sk = ROOT / "SKILL.md"
    if sk.exists():
        txt = sk.read_text(encoding="utf-8")
        m = re.search(r"##\s*八、红线.*?(?=^##\s*九、)", txt, re.S | re.M)
        if m:
            nums = [int(x) for x in re.findall(r"^(\d+)\.\s", m.group(0), re.M)]
            expect = list(range(1, len(nums) + 1))
            if nums != expect:
                drifted.append(("SKILL.md", ["红线编号不是 1..%d 唯一递增：实际 %s" % (len(nums), nums)]))
                print("❌ SKILL.md")
                print("     - 红线编号不是 1..%d 唯一递增：实际 %s" % (len(nums), nums))

    # ---- 课程索引契约（另一种文档类型，契约源 templates/course-INDEX.md）----
    # 不能让 course-index-example 混进上面的 TARGETS：它没有骨架/第N段/format:v2 这些
    # 单讲笔记字段，拿笔记契约去卡它只会假报红。这里单独按索引契约校验。
    ib = ROOT / INDEX_BASELINE
    if not ib.exists():
        drifted.append((INDEX_BASELINE, ["基准文件不存在"]))
        print(f"❌ {INDEX_BASELINE}\n     - 基准文件不存在")
    else:
        ibtext = ib.read_text(encoding="utf-8")
        miss = [st for st in INDEX_REVIEW_STAGES if st not in ibtext]
        if miss:
            drifted.append((INDEX_BASELINE, [f"基准缺综述阶段「{'、'.join(miss)}」"]))
            print(f"❌ {INDEX_BASELINE}")
            print(f"     - 基准缺综述阶段「{'、'.join(miss)}」")

    for rel in INDEX_TARGETS:
        ip = ROOT / rel
        if not ip.exists():
            drifted.append((rel, ["文件不存在"]))
            print(f"❌ {rel}\n     - 文件不存在")
            continue
        itext = ip.read_text(encoding="utf-8")
        body = "\n".join(regions(itext))
        h2s = extract_headings(body)
        probs = []
        for h in INDEX_REQUIRED_H2:
            if h not in h2s:
                probs.append(f"缺索引标题「{h}」")
        for st in INDEX_REVIEW_STAGES:
            if st not in body:
                probs.append(f"缺综述阶段「{st}」")
        for k in INDEX_FRONT_MATTER_KEYS:
            if k not in body:
                probs.append(f"缺 front matter 标记「{k}」")
        legacy = [h for h in LEGACY_HEADINGS_TO_FORBID if h in itext]
        if legacy:
            probs.append(f"残留 v1 标题「{'、'.join(legacy)}」")
        if probs:
            drifted.append((rel, probs))
            print(f"❌ {rel}")
            for m in probs:
                print(f"     - {m}")
        else:
            print(f"✅ {rel}  (课程索引契约)")

    # 自包含文件的能力标记对齐（SKILL 与 PROMPT 必须同组出现）
    present = {}
    for rel in ALIGN_FILES:
        fp = ROOT / rel
        if fp.exists():
            txt = fp.read_text(encoding="utf-8")
            present[rel] = set(m for m in CAPABILITY_MARKERS if m in txt)
    if len(present) == len(ALIGN_FILES):
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
        print(f"改模板时请同步修改：{BASELINE}（单讲笔记）/ {INDEX_BASELINE}（课程索引），以及上面列出的文件。")
        return 1

    print("全部同步 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())