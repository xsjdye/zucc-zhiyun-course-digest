#!/usr/bin/env bash
# 智云课堂 API 探测脚本 —— 只读探测，不提交任何作业、不修改任何数据
#
# 目的：在写自动化脚本之前，先确认三件事
#   1. token 该放在哪个 header 里（token / Authorization / Cookie）
#   2. 服务端是否校验 Origin / Referer（你笔记里写过"跨域 API 需在同域页面内调用"）
#   3. 三个端点真实的返回字段结构（课程安排 / PPT 列表 / 语音转录）
#
# 用法：
#   bash scripts/probe-api.sh
#   脚本会让你粘贴 token（不回显、不写入任何文件、不会出现在输出里）
#
# 跑完把【输出】整段贴回来即可 —— 输出里不含 token。

set -u

BASE="https://yjapi.hzcu.edu.cn"
ORIGIN="https://classroom.hzcu.edu.cn"

echo "════════════════════════════════════════════════════════"
echo " 智云课堂 API 探测（只读）"
echo "════════════════════════════════════════════════════════"
echo
printf '请把 token 粘贴到下面（输入不回显，按回车结束）：\ntoken> '
read -rs TK
echo
if [ -z "${TK:-}" ]; then echo "❌ 没输入 token，退出"; exit 1; fi
echo "  （已收到 ${#TK} 个字符的 token，不会打印它）"
echo

# 探测用公共头：带同域 Origin/Referer，模拟"在同域页面内调用"
common_headers() {
  printf '%s\n' "-H" "Origin: $ORIGIN" "-H" "Referer: $ORIGIN/" "-H" "User-Agent: Mozilla/5.0"
}

probe() {
  local label="$1" url="$2"
  echo "────────────────────────────────────────────────────────"
  echo "【$label】"
  echo "  $url"
  for h in "token: $TK" "Authorization: Bearer $TK" "Authorization: $TK"; do
    local hname="${h%%:*}"
    local code
    code=$(curl -s -o /tmp/zc_probe.json -w '%{http_code}' \
      --max-time 20 \
      -H "$h" -H "Origin: $ORIGIN" -H "Referer: $ORIGIN/" -H "User-Agent: Mozilla/5.0" \
      "$url" 2>/dev/null)
    local size
    size=$(wc -c < /tmp/zc_probe.json 2>/dev/null | tr -d ' ')
    printf "  %-14s → HTTP %-4s  响应 %-6s 字节\n" "[$hname]" "${code:-000}" "${size:-0}"
    if [ "${code:-000}" = "200" ] && [ "${size:-0}" -gt 20 ]; then
      echo "  ✅ 这个 header 有效，内容前 400 字节："
      # 抹掉任何可能出现的 token 字串
      head -c 400 /tmp/zc_probe.json | sed "s/${TK}/***REDACTED***/g"
      echo
      echo "  >>> 请记录：本次有效的 header 名是 [$hname]"
      return 0
    fi
  done
  echo "  ⚠️ 三种 header 都没拿到 200 —— 可能需要 Cookie 会话，或该接口要求 POST"
  return 1
}

echo
echo "══════ 第 1 步：课程安排（先拿到 course_id / sub_id）══════"
probe "get-week-schedules" "$BASE/courseapi/v2/schedule/get-week-schedules"

echo
echo "══════ 第 2 步：填 ID 后再跑下面两项 ══════"
echo "  从上面响应里找到 course_id 和 sub_id，然后编辑本文件末尾的 CID/SID，"
echo "  或直接手动跑（把 <CID> <SID> 换成真实值）："
echo
echo "  # PPT 帧列表"
echo "  curl -s -H \"token: \$TK\" -H \"Origin: $ORIGIN\" \\"
echo "    \"$BASE/pptnote/v1/schedule/search-ppt?course_id=<CID>&sub_id=<SID>\" | head -c 800"
echo
echo "  # 平台语音转录（关键：看 all_content 是字符串/数组/空对象哪种）"
echo "  curl -s -H \"token: \$TK\" -H \"Origin: $ORIGIN\" \\"
echo "    \"$BASE/courseapi/v3/web-socket/search-trans-result?sub_id=<SID>\" | head -c 800"
echo
echo "════════════════════════════════════════════════════════"
echo " 把上面所有【输出】贴回来（已自动抹掉 token）"
echo "════════════════════════════════════════════════════════"
