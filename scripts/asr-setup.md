# 本地录音转写：先体检电脑，再配模型

> **这份文档解决一件事**：把课堂录音变成文字，这样笔记里的「★ 重点标注」不再是瞎猜，而是真能看到老师嘴上说了什么。
>
> **不是必须做。** 主路径（你把课件内容发给 AI）完全不需要装任何东西。这份是**可选进阶**，而且只有**能执行命令的 AI Agent** 才用得上的到（Qoder / Cursor / Claude Desktop + 终端权限）。

---

## 为什么需要这一步

课件上通常**不写**"这个要考"。老师嘴上强调的内容，只有录音里才有。

| 你有 | AI 判断重点的依据 | 可靠度 |
|---|---|---|
| 只有课件 | 加粗、篇幅、出现次数 | ⚠️ 猜 |
| 课件 + 录音转出的文字 | 再加老师反复讲的、明确说"要考"的、补充举例外延的 | ✅ 准得多 |

---

## 第 0 步 · 先体检你的电脑（别急着装）

**不同电脑该装的东西完全不一样**。8GB 轻薄本硬上大模型会卡到怀疑人生，有独显的机器却浪费性能。所以先看配置。

### macOS（把下面整段粘进「终端」）

```bash
echo "芯片: $(sysctl -n machdep.cpu.brand_string)"
echo "内存: $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 )) GB"
echo "磁盘剩余: $(df -h ~ | tail -1 | awk '{print $4}')"
echo "Apple Silicon?: $(uname -m)"     # arm64 = 是；x86_64 = Intel 老机器
```

### Windows（把下面整段粘进 PowerShell）

```powershell
(Get-CimInstance Win32_Processor).Name
[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)
(Get-PSDrive C).Free / 1GB
(Get-CimInstance Win32_VideoController).Name
```

四行分别给你：**CPU 型号 / 内存 GB / C 盘剩余 GB / 显卡型号**。

> 显卡那行如果出现 `NVIDIA`，说明你有独显，选择面大很多。

---

## 第 1 步 · 按体检结果选一条路

### 决策表

| 你的情况 | 选哪条 | 模型体积 | 运行内存 | 中文准确率* |
|---|---|---|---|---|
| **你用的 AI 本身支持上传音频** | **路径 A：零安装** ★最优先 | 0 | 0 | 看平台 |
| Apple Silicon（M系列）+ 内存 8GB | 路径 B：whisper.cpp `small` | 约 466 MB | 约 0.8 GB | 词错率约 17% |
| Apple Silicon + 内存 16GB 以上 | 路径 B：whisper.cpp `medium` | 约 1.5 GB | 约 2 GB | 词错率约 12% |
| Windows，无独显，内存 8GB | 路径 B：whisper.cpp `base` 起 | 约 142 MB | 约 0.4 GB | 词错率约 22% |
| Windows，无独显，内存 16GB+ | 路径 B：whisper.cpp `small`/`medium` | 466 MB–1.5 GB | 0.8–2 GB | 17% / 12% |
| 有 NVIDIA 独显（显存 ≥6GB） | 路径 C：FunASR `paraformer-large` | 模型约 1.5 GB | 显存约 4.5 GB | 中文专门优化，通常更准 |
| 只要"能认出个大概" | 路径 B：whisper.cpp `base` | 约 142 MB | 约 0.4 GB | 一般 |

\* 词错率（WER）：越低越好。数据来自公开实测（AISHELL 中文测试集），**你的实际效果会因录音质量、老师口音、教室噪音明显浮动**，别当成承诺值。

### ⛔ 明确不要选的

- **whisper `large-v3` + 只有 CPU**：模型约 3 GB，纯 CPU 处理 1 分钟音频要 5–10 分钟，一节课 45 分钟 = 等 4–7 小时。8GB 笔记本直接放弃。
- **`tiny` 模型做中文**：词错率接近 28%，转出来经常是乱码，不如不转。
- **带 `.en` 的模型**（如 `base.en`）：**只认英文**，中文会变日文或乱码。中文必须用**不带 `.en`** 的多语言版。

---

## 第 2 步 · 安装（AI 给命令，你点头才执行）

### 路径 A · 零安装（先试这个）

部分 AI 平台本身支持上传音频/视频并转写。**如果你用的 AI 有这功能，直接传录音，跳过下面所有步骤。**

优点：不占硬盘、不装环境、跨系统。缺点：你传的内容会进入该平台，效果看平台。

### 路径 B · whisper.cpp（跨平台推荐）

**macOS**

```bash
brew install whisper-cpp ffmpeg
# 中文用不带 .en 的模型；small 是 8GB 机器的平衡点
curl -L -o ~/ggml-small.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

**Windows**（三选一，按你的情况）

1. **官方 Releases 找预编译包**（最省事，不用装编译器）：去 whisper.cpp 仓库的 Releases 页看有没有 Windows 压缩包；有就下载解压，同样下 `ggml-small.bin` 模型。
2. **用 WSL**：在 PowerShell 里 `wsl --install`，进 WSL 后按上面 macOS 的 Linux 版步骤走。
3. **自己编译**：需要装 CMake + Visual Studio Build Tools，非科班不推荐。

### 路径 C · FunASR（中文更准，但环境重）

需要 Python 环境 + PyTorch，模型约 1.5 GB，依赖安装容易卡。**只建议有 NVIDIA 独显或 16GB 以上内存的同学**。

```bash
pip install funasr modelscope torch
```

> ⚠️ 关于 FunASR 的速度，公开资料说法**互相矛盾**：有实测说 i5 笔记本处理 5 分钟音频只要 8 秒，也有资料说纯 CPU 会从 5 倍实时掉到 0.3 倍实时（即 1 分钟音频要 3 分半）。**所以我无法给你保证值——先拿一段 5 分钟的录音试跑**，能接受再转整节课。

---

## 第 3 步 · 转写

### whisper.cpp

```bash
# 先转成 16kHz 单声道 wav（whisper 要求）
ffmpeg -i 课堂录音.m4a -ar 16000 -ac 1 课堂录音.wav

# 转写，指定中文
whisper-cli -m ~/ggml-small.bin -l zh -f 课堂录音.wav -osrt -of 课堂录音
```

产出 `课堂录音.srt`（带时间戳的字幕文件）——这个格式最好，因为**时间戳能让你回到录音里核对原话**。

### 关键参数说明

| 参数 | 作用 |
|---|---|
| `-l zh` | 明确告诉它是中文，准确率比自动检测更好 |
| `-osrt` | 输出 SRT 带时间戳 |
| `-of <名字>` | 输出文件前缀 |

---

## 第 4 步 · 回到整理流程

把转出的 `.srt` 或纯文字**连同课件一起**发给 AI，并说一句：

```
这次重点判定的依据包含课堂录音，请重新整理
```

AI 就会把「重点判定依据」那一行从 `课件文字` 改成 `课件文字 + 课堂录音`，并且★ 的理由可以写"录音中老师重复讲解 3 次"这种**真实依据**。

---

## 常见坑

| 现象 | 原因 / 解法 |
|---|---|
| 转出来是日文或乱码 | 用了 `.en` 模型，或没加 `-l zh` |
| 装完跑不起来（缺 ffmpeg） | 音频转码需要 ffmpeg；macOS `brew install ffmpeg` |
| 转 45 分钟录音等了很久 | 正常。CPU 上大模型很慢；换 `base`/`small`，或先切一段试听 |
| 内存告警 / 电脑变卡 | 你选的模型超出机器能力，退回更小一档 |
| 磁盘放不下 | `medium` 要 1.5GB、`large` 要 3GB，先 `df -h` 看剩余 |
| 教室后排录音噪音大 | 任何模型都会掉准确率；这不是工具问题，尽量坐前排或用官方录像 |

---

## 一句话提醒

录音转写是**辅助**。转出来的文字一定有错别字，老师说错的地方它也会照抄。**别把转写稿当权威记录**，关键处回到录音核对。
