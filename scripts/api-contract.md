# 智云课堂接口契约（实测）

> 实测时间：2026-10-11，用真实账号跑通并逐字段核对。
> 实测样本：一门 2 小时的全校公选课，全讲转写 1869 段 / 35410 字，课件 346 帧。
> （不写课程名与精确日期时间——那属于可定位到个人的课表信息。）
> 本文档只写**字段名与结构**，不写真实值；`sub_id` 一类标识请各自从自己课表里取。

---

## 0. 两条硬前提

| 前提 | 说明 | 踩过的坑 |
|---|---|---|
| **必须在 `classroom.hzcu.edu.cn` 域下调用** | 接口在 `yjapi.hzcu.edu.cn`，靠浏览器 CORS 放行 | 在 `education.hzcu.edu.cn`（同为城院域名）页面里调用，`fetch` 直接 `TypeError: Failed to fetch` |
| **认证 = Cookie，不需要 token** | 请求带 `credentials: 'include'` 即可 | 不要再去找什么 token 往 header/query 里塞；加了 `&token=` 反而换一种响应外壳 |

用 `curl` 时同理，要带 Cookie；平台侧凭据有效期约 1 天。

---

## 1. 课表：定位课时，拿 `sub_id` / `course_id`

```
GET https://yjapi.hzcu.edu.cn/courseapi/v2/schedule/get-week-schedules
      ?user_id=<本人用户id>&tenant_id=21&start_at=<YYYY-MM-DD>&end_at=<YYYY-MM-DD>
```

`user_id` 从页面自己解析，**不要写进任何文件**：

```js
var uid = '';
try { uid = String(JSON.parse(sessionStorage.getItem('user') || '{}').user_id || ''); } catch (e) {}
if (!uid) { var m = document.cookie.match(/(?:^|; )login_cmc_id=([^;]+)/); if (m) uid = decodeURIComponent(m[1]); }
```

响应（`{success, result:{code, msg, list:[按天]}}` 双层外壳）：

```
result.list[]           每天一条
  ├ day                 "YYYY-MM-DD"
  └ course[]            当天课程，无课为空数组
     ├ id               ← 这就是 sub_id
     ├ course_id
     ├ course_title     课程名
     ├ teacher_name     教师名
     ├ teachers[]       {username, realname, is_speaker, kkxy_code, kkxy_name}
     ├ room_name        教室
     ├ start_at/end_at  epoch 秒（真实起止时间）
     ├ begin_time       epoch 秒（上课时刻）
     ├ status           "6"
     ├ status_label     "回放"（有回放）
     ├ is_live / is_public / multi_type / sub_show / sub_review_type
     └ …
```

- 一次最多返回 7 天，跨周要自己分段查。
- **`course` 数组为空 = 那天没课**，不是接口出错。

---

## 2. 课件帧：`search-ppt`

```
GET https://yjapi.hzcu.edu.cn/courseapi/v2/schedule/search-ppt?course_id=<cid>&sub_id=<sid>
```

> ⚠️ 路径是 **`courseapi/v2`**，不是 `pptnote/v1`。后者在 `yjapi` 上返回的是 SPA 的 HTML 页（HTTP 200 + `<!DOCTYPE html>`），不报错，很容易误判成"接口没数据"。

响应：

```
{ code: 0, msg: <str>, total: <str，注意是字符串>, page: 1, per_page: 10,
  list[]: {
    id, course_id, sub_id,
    created_sec   ← 相对录音起点的秒数，这是与转写对齐的关键字段
    create_time / update_time   "YYYY-MM-DD HH:MM:SS"
    type          "ppt"
    default       1
    old_id, resource_guid(实测空串)
    ocr_text      实测恒为 null —— 平台不给课件文字
    content       ← JSON 字符串，要再 JSON.parse 一次
  } }
```

`content` 解析后：

```
{ detecttype: "ppt",
  is_key:     <bool>   ← 实测全讲 346 帧恒 false，别依赖它做重点判定
  status:     "running"← 实测恒 running（识别任务未回填）
  taskid:     <uuid>
  created:    <13位 epoch 毫秒字符串>
  pptimgurl:  "https://video.hzcu.edu.cn/ai3/ppt/<YYYYMMDD>/<guid>/<epochMillis>.jpg"
  pptthumb:   同路径下 "s_<...>.jpg" 缩略图 }
```

### 帧图取用（⚠️ 这是一条**风险**，不是一条能力）

```bash
curl -o frame.jpg "https://video.hzcu.edu.cn/ai3/ppt/…/<ms>.jpg"
```

实测 **不带 Cookie 也返回 200 `image/jpeg`**（约 40 KB / 帧，1280×720）。

> 🔴 **这意味着链接本身就是访问凭证，而不是"一个需要登录才能打开的资源"。**
> 谁拿到 URL 谁就能看到课件内容，平台无从校验拿链接的人是否选了这门课。
>
> 本仓库记录这一点的**唯一目的**是让同学知道**这些链接不能外发**（详见 `SKILL.md` 第八节红线）。
> 它不是"绕过登录"的方法：链接本身要靠登录态才能从 `search-ppt` 里列出来。
>
> **建议**：若你在校内群看到有人转发这类链接，提醒对方删除；
> 若你希望这个行为被修正，把本节截图发给学校信息中心，让他们判断课件帧资源是否应当改为需鉴权访问。
> 不要自己去批量验证边界——那属于未授权的访问控制测试。

### 帧图怎么读：不必装 OCR

帧图是 1280×720 的清晰截图，**带视觉能力的 AI 直接读图即可**，不必部署 EasyOCR / PaddleOCR。
只有当 AI 无视觉能力、或要批量全文检索时，才需要本地 OCR。

---

## 3. 课堂语音转写：`search-trans-result`

```
GET https://yjapi.hzcu.edu.cn/courseapi/v3/web-socket/search-trans-result?sub_id=<sid>
```

响应（**单层外壳** `{code, msg, total, list:[1]}`，与课表的双层壳不同）：

```
list[0] {
  all_content: [ {BeginSec:num, EndSec:num, Text:str, TransText:str} ]  ← 数组，直接用
  trans_content: <字符串>            ← JSON.parse 后是与 all_content 等长的数组
  sub_id, resource_guid(""), trans_type("ainew"),
  zh_num(中文字数), en_num, en_rate
}
```

- `TransText` 实测为空串（疑似译文槽位），整理时忽略，只用 `Text`。
- **`all_content` 与 `trans_content` 二选一用 `all_content`**：前者已是数组，后者还要再 parse。
  这就是"三态兼容"说法的来源——不同课程 / 不同时期返回的是数组、JSON 字符串、或空对象。
  稳妥写法：`Array.isArray(x) ? x : (typeof x === 'string' ? JSON.parse(x||'[]') : [])`。

### 分段合并必须加跨度上限

平台分段本身**时间上是连续的**（上一段 `EndSec` ≈ 下一段 `BeginSec`）。
若只按"间隔 ≤2 秒"合并，前 15 分钟的 199 段会塌成 **3 个巨型段落**，没法读。

实测可用规则（三条同时成立才合并）：

```
间隔 ≤ 2s  AND  合并后跨度 < 40s  AND  合并后字数 < 220
```

199 段 → 26 段，可读。

---

## 4. 三张表怎么对齐（这是本 skill 的核心机制）

```
帧.created_sec  ─┐
                 ├─ 同一个时间轴：相对录音起点的秒数
段.BeginSec/EndSec┘
```

把「帧」按 `created_sec` 排序，每一页课件的**讲解内容**= 落在 `[本帧 sec, 下一帧 sec)` 区间内的所有转写段。
这样得到的不是"课件摘要 + 录音摘要"两份东西，而是**逐页的"老师这页讲了什么"**——
这才是课后整理真正有价值的东西，也是"重点标注"能给出依据的原因。

实测对齐效果：帧 `08:41` 的目录页只有副标题，口述在 08:16–08:53 正好在念这四条；
帧 `09:46` 同一页补出了主标题（动画逐条显现），口述 09:18–09:54 正在逐条解释。

### 由此产生的两个整理规则

1. **同一页课件的多帧要归并**：连续帧往往只是同一页的动画不同显现状态，
   应合并成一个知识点，保留信息最全的那帧作指针。346 帧 ≠ 346 页。
2. **非内容页要丢弃**：帧是**整屏截图**，实测前 5 帧（00:30–01:09）是签到二维码 + 浏览器界面
   （含标签页、任务栏、签到进度）。这类帧没有知识点。

---

## 5. 实测坑清单（速查）

| 现象 | 原因 / 正确做法 |
|---|---|
| `fetch` 报 `Failed to fetch` | 不在 `classroom.hzcu.edu.cn` 域下 |
| `search-ppt` 返回 `<!DOCTYPE html>` | 用了 `pptnote/v1` 路径；改 `courseapi/v2` |
| 课件只拿到 10 条 | 传了 `page` / `per-page`。**不传分页参数会一次返回全部**（实测 346 条） |
| `is_key` 全是 false | 平台重点标记未回填，**不可依赖**，重点要自己判定 |
| `ocr_text` 全是 null | 平台不给课件文字；用视觉读帧图，或本地 OCR |
| `total` 是字符串 `"346"` | 别拿去直接做数值比较，先 `Number()` |
| 逐字稿塌成几大块 | 合并规则缺跨度上限，见第 3 节 |
| `list` 为空但 HTTP 200 | 该课**转写未生成**或无回放，不是接口坏了 → 走本地转写兜底 |
| 外层壳时有时无 | 课表是 `{success,result:{…}}`，转写是 `{code,msg,list}`；两种都要兼容 |

---

## 6. 还没实测的部分（不要假装跑通）

- **鉴权边界未验证**：换一个 `user_id` / `sub_id` 能不能读到不属于自己的课表或课件，本仓库**没有测，也不要去测**。
  那是针对学校系统的未授权访问控制测试，性质和"读自己已登录账号能看的东西"完全不同。
  本工具的设计前提就是：**只做你本人登录后本来就能看到的事**，不试图越权、不试图枚举他人数据。
- **回放取流地址未探测**：`status=6` 但 `search-trans-result` 返回空时，需从回放 mp4 抽音频本地转写。
  回放视频地址接口**本轮未探测**，`SKILL.md` 里按"未验证"处理。
- **本地 ASR 兜底**：见 `asr-setup.md`，注意它现在是**兜底路径**而非主路径——
  绝大多数有回放的课，平台转写已经够用了。
- **多教师课**：`teachers[]` 实测 2 人（`is_speaker` 均为 `"1"`），谁主讲未验证。
- **接口路径来自学校自己下发的 JS**：本轮实测时页面 JS 明文含 26 条接口路径与 10 个 `*.hzcu.edu.cn` 主机名。
  也就是说这些路径不是"逆向出来的秘密"，而是发给每个登录学生的普通前端代码；
  但**它们会变**。如果哪天 `fetch-lesson.js` 报 404，先回自己的网络面板看平台现在在调什么，别照本文档硬试。
