# scripts/ —— 可选进阶材料

这个目录**不属于主流程**。主流程（把课件内容发给 AI 整理）**永远零依赖**，不需要这里任何东西。

## 目录内容

| 文件 | 是什么 | 什么时候用 |
|---|---|---|
| [`asr-setup.md`](asr-setup.md) | 本地录音转写指南：**先体检电脑，再按配置选模型** | 你想把课堂录音变成文字，让「重点标注」有真实依据时 |
| [`check-template-sync.py`](check-template-sync.py) | 检查输出模板在各文件间是否同步（零依赖，只用 Python 标准库） | 改过模板、加过章节之后跑一下：`python3 scripts/check-template-sync.py` |

### 为什么需要 check-template-sync.py

输出模板必然在 5 个文件里各写一遍——因为 `SKILL.md` 和 `PROMPT.md` 必须**自包含**（同学可能只把单个文件丢给 AI），这种重复是设计使然、不能消除。

但重复带来漂移风险：改了一处忘了另一处。这个脚本把 `examples/note-template.md` 当作**唯一契约源**，自动检查其余 4 处是否包含同样的 header 字段与章节序列：

```bash
python3 scripts/check-template-sync.py        # 退出码 0 = 同步，1 = 发现漂移
python3 scripts/check-template-sync.py -v     # 同时打印基准契约内容
```

## 为什么主流程坚持零依赖

本 skill 的目标是**任何 AI 都能无障碍使用**，这包括：

- 网页版 / App 版 AI（豆包、Kimi、通义、ChatGPT 等）—— 它们**碰不到你的本地环境**，装什么都没用
- 没有技术背景的同学

所以：

| | 主流程 | 本目录 |
|---|---|---|
| 要不要装东西 | ❌ 不用 | ✅ 要 |
| 什么 AI 能用 | 任意 AI | 只有**能执行命令的 AI Agent**（Qoder / Cursor / Claude Desktop 等，且需终端权限） |
| 不做会怎样 | 不会，照常出笔记 | 只是「重点标注」缺少录音依据 |

## 规划中的脚本（尚未提供）

| 脚本 | 作用 |
|---|---|
| `device-check` | 自动体检配置，直接给出该装哪个模型（目前请先手动跑 `asr-setup.md` 的第 0 步） |
| `ppt_extract.py` | 把 PPT / PDF 批量转成纯文本，方便喂给 AI |

## 若将来添加可执行脚本，约定如下

- 一律放本 `scripts/` 目录
- 必须**可独立运行**、`--help` 有说明
- **不硬编码任何账号密码**，绝不保存用户凭据
- 不批量抓取、不高频并发
- 同时给出 macOS 与 Windows 两套命令（本仓库面向双系统同学）
