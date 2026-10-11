/*
 * zcc-fetch-lesson.js —— 智云课堂单课时取数脚本
 *
 * 用途：把一节课的「课件帧 + 平台语音转写 + 课堂元信息」一次导出成 JSON。
 * 关键：全程在你**已登录**的浏览器里运行，凭据不出浏览器；脚本不读也不打印任何 token。
 *
 * 怎么用（不需要任何 AI 能操作浏览器）：
 *   1. 浏览器打开 https://classroom.hzcu.edu.cn/ 并确认已登录
 *   2. F12 → Console（控制台）→ 整段粘贴本文件内容 → 回车
 *   3. 执行：  zccFetch('2026-10-15', '数字媒体')
 *      限制时长：zccFetch('2026-10-15', '数字媒体', {maxSec: 900})
 *   4. 执行：  copy(await zccFetch(...))   ← 直接把结果复制到剪贴板，粘给任意 AI
 *
 * 返回值只含课程内容，不含姓名以外的隐私字段；帧图 URL 无鉴权，等同课程内容，别外发。
 */
async function zccFetch(date, keyword, opts) {
  var API = 'https://yjapi.hzcu.edu.cn';
  var TENANT = '21';
  opts = opts || {};
  var maxSec = typeof opts.maxSec === 'number' ? opts.maxSec : Infinity;

  // 1) 当前用户 id —— 只在页面内解析，不返回
  var uid = '';
  try {
    var u = JSON.parse(sessionStorage.getItem('user') || '{}');
    uid = String(u.user_id || u.id || '');
  } catch (e) {}
  if (!uid) {
    var m = document.cookie.match(/(?:^|; )login_cmc_id=([^;]+)/);
    if (m) uid = decodeURIComponent(m[1]);
  }
  if (!uid) throw new Error('未识别到登录身份，请先在浏览器登录 https://classroom.hzcu.edu.cn/');

  // 2) 该日期所在周（±3 天足够覆盖）的课表
  var d = new Date(date + 'T00:00:00');
  function ymd(x) {
    return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0');
  }
  var from = new Date(d.getTime() - 3 * 864e5), to = new Date(d.getTime() + 3 * 864e5);
  var sch = await (await fetch(API + '/courseapi/v2/schedule/get-week-schedules?user_id=' +
    encodeURIComponent(uid) + '&tenant_id=' + TENANT + '&start_at=' + ymd(from) + '&end_at=' + ymd(to),
    { credentials: 'include' })).json();
  var days = (sch.result && sch.result.list) || [];

  var matched = [];
  days.forEach(function (day) {
    if (day.day !== date) return;
    (day.course || []).forEach(function (c) {
      if (!keyword || String(c.course_title || '').indexOf(keyword) >= 0) matched.push(c);
    });
  });

  if (!matched.length) {
    var avail = [];
    days.forEach(function (day) { (day.course || []).forEach(function (c) { avail.push(day.day + ' ' + c.course_title); }); });
    return { error: '该日期没有匹配「' + keyword + '」的课', hint: '本周有课的条目：', available: avail };
  }
  if (matched.length > 1 && !opts.pick) {
    return { error: '匹配到多节课，请用更长的关键词，或加 {pick: 序号}', matches: matched.map(function (c, i) { return { pick: i, title: c.course_title, time: c.begin_time, room: c.room_name }; }) };
  }
  var idx = opts.pick || 0;
  if (idx >= matched.length) {
    return { error: 'pick 超出范围：' + date + ' 只匹配到 ' + matched.length + ' 节，可选 0~' + (matched.length - 1) };
  }
  var c = matched[idx];

  function hhmm(ts) {
    var x = new Date(Number(ts) * 1000);
    return String(x.getHours()).padStart(2, '0') + ':' + String(x.getMinutes()).padStart(2, '0');
  }
  function mmss(sec) {
    sec = Math.floor(sec);
    return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
  }

  var sid = String(c.id), cid = String(c.course_id);
  var meta = {
    date: date,
    course_title: c.course_title,
    teacher_name: c.teacher_name,
    teachers: (c.teachers || []).map(function (t) { return t.realname; }),
    room_name: c.room_name,
    start: hhmm(c.start_at), end: hhmm(c.end_at),
    status_label: c.status_label,
    sub_id: sid, course_id: cid
  };

  // 3) 课件帧。注意：**不要传 page / per-page**，一传就变成每页 10 条
  var ppt = await (await fetch(API + '/courseapi/v2/schedule/search-ppt?course_id=' +
    encodeURIComponent(cid) + '&sub_id=' + encodeURIComponent(sid), { credentials: 'include' })).json();
  var frames = (ppt.list || []).map(function (r) {
    var p = {};
    try { p = JSON.parse(r.content) || {}; } catch (e) {}
    return {
      sec: r.created_sec,               // 相对录音起点的秒数
      clock: mmss(r.created_sec),
      img: p.pptimgurl || '',           // 免登录可直接下载
      thumb: p.pptthumb || '',
      is_key: !!p.is_key                // 实测恒 false，别依赖
    };
  }).filter(function (f) { return f.sec <= maxSec; });

  // 4) 平台语音转写
  var tr = await (await fetch(API + '/courseapi/v3/web-socket/search-trans-result?sub_id=' +
    encodeURIComponent(sid), { credentials: 'include' })).json();
  var item = (tr.list || [])[0] || null;
  var segs = item && Array.isArray(item.all_content) ? item.all_content : [];
  var merged = [];
  segs.forEach(function (s) {
    if (Number(s.EndSec) > maxSec) return;
    var t = String(s.Text || '').trim();
    if (!t) return;
    var last = merged[merged.length - 1];
    // 平台分段本身是连续的，只按间隔合并会塌成几大块，必须同时限制跨度与长度
    if (last && Number(s.BeginSec) - last.e <= 2 && (Number(s.EndSec) - last.b) < 40 && (last.txt.length + t.length) < 220) {
      last.txt += t; last.e = Number(s.EndSec);
    } else {
      merged.push({ b: Number(s.BeginSec), e: Number(s.EndSec), txt: t });
    }
  });

  return {
    meta: meta,
    transcript: {
      available: !!item,
      source: item ? ('平台语音识别 trans_type=' + item.trans_type) : '无（sub_status 未生成或该课无回放）',
      total_segments: segs.length,
      total_chars: item ? item.zh_num : 0,
      exported: merged.length,
      exported_chars: merged.reduce(function (a, m) { return a + m.txt.length; }, 0),
      text: merged.map(function (m) { return '**[' + mmss(m.b) + ']** ' + m.txt; }).join('\n\n')
    },
    frames: {
      total: frames.length,
      list: frames,
      note: 'img 链接无鉴权，任何人拿到都能看 —— 等同课程内容，不要贴到公开位置。'
    }
  };
}


/*
 * zccProbe() —— 登录态预检：**不导航**，一次 fetch 就判定
 *
 * 为什么需要它：classroom.hzcu.edu.cn 未登录时不会返回 302，而是照常返回 200 + 前端外壳，
 * 由 SPA 自己用 JS 跳去 https://yjlogin.hzcu.edu.cn（见其 static/config.js 的 LOGIN_URL）。
 * Agent 若在跳转在途时再发起一次导航，就会把登录页反复冲掉——表现为"登录页闪一下就没"。
 * 所以正确做法是先探测，再决定要不要打扰用户，而不是导航进去追。
 *
 * 实测依据：未登录时课表接口返回 HTTP 200 且 body 为
 *   {"success":true,"result":{"err":0,"errMsg":"","data":"未传入token"}}
 * 这是个干净的机器可读信号。
 *
 * 用法：await zccProbe()
 *   → { loggedIn: true,  host: 'classroom.hzcu.edu.cn', uidResolved: true }
 *   → { loggedIn: false, why: 'not-logged-in', ... }   ← 此时**不要重新导航**，交给用户登录
 *   → { loggedIn: false, why: 'wrong-origin', host: 'yjlogin.hzcu.edu.cn' }
 */
async function zccProbe() {
  var API = 'https://yjapi.hzcu.edu.cn';
  var TENANT = '21';
  var host = location.hostname;
  var onCas = host === 'ca.hzcu.edu.cn' || /\/cas\/login/i.test(location.pathname);

  if (host !== 'classroom.hzcu.edu.cn') {
    return {
      loggedIn: false,
      why: onCas ? 'on-login-page' : 'wrong-origin',
      host: host,
      action: onCas
        ? '这就是登录页，它已经稳定停住了。⚠️ 现在**绝对不要再调用 navigate / goto**：' +
          '重新导航会打断 CAS 的回跳，把这张表单冲掉，表现就是"登录页闪一下就没"。' +
          '请用户在**当前这个窗口**里自己输入账号密码登录，然后轮询本函数直到 loggedIn 为 true。'
        : '请在 https://classroom.hzcu.edu.cn/ 页面内运行本脚本'
    };
  }

  var uid = '';
  try { uid = String(JSON.parse(sessionStorage.getItem('user') || '{}').user_id || ''); } catch (e) {}
  if (!uid) {
    var m = document.cookie.match(/(?:^|; )login_cmc_id=([^;]+)/);
    if (m) uid = decodeURIComponent(m[1]);
  }
  if (!uid) return { loggedIn: false, why: 'no-identity', host: host, action: '页面里没有登录身份，需要用户在浏览器完成登录' };

  var r;
  try {
    r = await (await fetch(API + '/courseapi/v2/schedule/get-week-schedules?user_id=' +
      encodeURIComponent(uid) + '&tenant_id=' + TENANT +
      '&start_at=2000-01-03&end_at=2000-01-07', { credentials: 'include' })).json();
  } catch (e) {
    return { loggedIn: false, why: 'fetch-failed', host: host, detail: String(e).slice(0, 80) };
  }

  var data = r && r.result && r.result.data;
  if (typeof data === 'string' && data.indexOf('未传入token') >= 0) {
    return {
      loggedIn: false, why: 'not-logged-in', host: host, uidResolved: true,
      action: '有身份标识但会话无效。不要重新导航（会把登录页冲掉）；' +
              '请用户在当前可见窗口完成登录，然后轮询本函数直到 loggedIn 为 true。'
    };
  }
  return { loggedIn: true, host: host, uidResolved: true, shape: typeof data };
}
