# scripts/ 目录说明

**这里有两个东西属于主流程**：`fetch-lesson.js`（取数）和 `api-contract.md`（接口契约）。
其余是兜底路径与自检工具。

| 文件 | 是什么 | 什么时候用 |
|---|---|---|
| [`fetch-lesson.js`](fetch-lesson.js) | ★ **取数脚本**：一次拿到课件帧 + 平台转写 + 课堂元信息 | 主流程。AI 能操作浏览器就由 AI 跑；不能就由你粘到 F12 控制台跑一次 |
| [`api-contract.md`](api-contract.md) | 接口契约、字段结构、时间轴对齐机制、**实测坑清单** | 接口返回异常时**先查它**，别猜 |
| [`asr-setup.md`](asr-setup.md) | 本地转写指南：**先体检电脑，再按配置选模型** | **兜底路径**——仅当平台转写没生成时才需要 |
| [`probe-api.sh`](probe-api.sh) | 手工探测接口（只读、带凭据脱敏） | 没有浏览器环境、要在终端里确认接口是否通的时候 |
| [`privacy-scan.py`](privacy-scan.py) | 上传前隐私扫描（零依赖，含 `--selftest`） | **推送到公开仓库前必跑** |
| [`check-template-sync.py`](check-template-sync.py) | 检查输出模板在各文件间是否同步 | 改过模板、加过章节之后跑一下 |

## 关于 fetch-lesson.js

它不装任何东西——**浏览器控制台就是它的运行环境**。所以"零依赖"这个说法仍然成立。

有两个函数：

| 函数 | 作用 |
|---|---|
| `zccFetch(日期, 关键词, {maxSec, pick, withFrames})` | 取一节课的 `{meta, transcript, frames}` |
| `zccRecent({days, keyword})` | 列最近 N 天**有课的日期**（同学记不住「上周三是几号」时用） |

`withFrames: false` 只返回转写 + 帧总数、不带帧列表——实测一节课可达 346 帧，
先拿转写写正文、再按段挑几帧核对，是省上下文的关键。
它本身就是登录检查——跑通就是已登录，返回 `未传入token` 就是没登录，不用另写探针。

三条硬规则（都是实测踩出来的）：

1. 只能在 `classroom.hzcu.edu.cn` 域下运行，其它城院域名会被跨域策略拦掉
2. 只借用你已登录的 Cookie，**不读取、不打印任何 token**
3. 返回里的课件帧 URL **免登录即可访问**，等于凭证 —— 别贴到任何公开位置

还有一条关于登录的坑，值得单独记：未登录时 `classroom` **不发 302**，而是返回 200 + 前端外壳，
由 SPA 自己 JS 跳去 `ca.hzcu.edu.cn/cas/login`。浏览器工具会把这次导航报成 `ERR_ABORTED`，
**此时重试导航会打断 CAS 回跳，登录页闪一下就没了**。登录态直接看 `zccFetch()` 跑不跑得通。
详见 [`api-contract.md`](api-contract.md) 第 0.5 节。

正常用法是**由 AI 在页面里跑它**，同学不需要碰控制台。
只有当 AI 完全无法操作浏览器、而用户又主动问"还有别的办法吗"时，
才让他按文件顶部注释自己跑一次——这是进阶备选，不是推荐路径。

## 为什么本地转写降级成了兜底

早期设计假设"要整理就得自己录音、自己跑 ASR"。实测发现：
**智云课堂有回放的课，平台自带语音转写已经生成**（实测一节课 1869 段 / 35410 字，前 15 分钟 199 段）。

所以顺序反过来了：

| 情况 | 走什么 |
|---|---|
| 有回放、有转写（**绝大多数**） | `fetch-lesson.js` 直接取，**不用装任何东西** |
| 有回放、转写未生成 | 才需要 `asr-setup.md`：抽音频 → 本地模型转写 |
| 无回放 | 只能靠课件帧 + 你自己的记录，并在笔记里如实标注 |

## 两个自检脚本

```bash
# macOS / Linux
python3 scripts/privacy-scan.py --selftest   # 先确认扫描器本身有效，再看结果才有意义
python3 scripts/privacy-scan.py              # 只扫「git 认为会被上传的文件」，退出码非 0 就别上传

python3 scripts/check-template-sync.py       # 退出码 0 = 同步，1 = 发现漂移
python3 scripts/check-template-sync.py -v    # 同时打印基准契约内容

# Windows：没有 python3 这个命令，换成 python，路径用反斜杠
python scripts\privacy-scan.py --selftest
python scripts\check-template-sync.py
```

两个脚本**只用 Python 标准库，不需要 pip 装任何东西**，兼容 Python 3.8+。
并且已内置输出编码兜底：在 GBK / C locale 下（Windows 控制台、或被 AI Agent 捕获输出时很常见）
不会因为打印中文而 `UnicodeEncodeError` 崩掉。乱码不影响判定，介意的话先 `chcp 65001`。

### 为什么需要 check-template-sync.py

输出模板必然在 5 个文件里各写一遍——因为 `SKILL.md` 和 `PROMPT.md` 必须**自包含**（同学可能只把单个文件丢给 AI），这种重复是设计使然、不能消除。

但重复带来漂移风险：改了一处忘了另一处。这个脚本把 `examples/note-template.md` 当作**唯一契约源**，检查其余 4 处是否包含同样的 header 字段、**全部 `##` 标题**、以及转写版特有的结构标记（`- 依据：`、`｜转写`、`｜课件帧`）。

> 早先只比对「一、二、三…」编号章节，导致新增「附：转写勘误」时检查器**照样报全绿**——假绿灯比没检查更糟。
> 现在改模板后如果没同步，一定会被拦下来。可以故意删掉一处验证。

`examples/fallback-example.md` 是**降级示例**（没有转写），因此豁免「附：转写勘误」这一节。

## 规划中（尚未提供，别照着用）

| 脚本 | 作用 |
|---|---|
| `device-check` | 自动体检配置，直接给出该装哪个模型（目前请先手动跑 `asr-setup.md` 的第 0 步） |
| `frame-dedupe` | 按时间间隔把同一页课件的连续帧归并，减少重复读图 |
| 回放取流 | 转写缺失时拿回放 mp4 的地址 —— **接口本轮未探测**，见 `api-contract.md` 第 6 节 |

## 添加脚本的约定

- 一律放本 `scripts/` 目录
- 必须**可独立运行**、`--help` 或顶部注释有说明
- **不硬编码任何账号密码 / token**，绝不保存用户凭据
- 不批量抓取、不高频并发
- 同时给出 macOS 与 Windows 两套命令（本仓库面向双系统同学）
- 路径用 `__file__` 解析，不要写死绝对路径
