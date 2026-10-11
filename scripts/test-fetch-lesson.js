#!/usr/bin/env node
/*
 * zccFetch 控制流集成测试（零依赖，只用 node）
 *
 * 为什么需要它：fetch-lesson.js 在浏览器里跑，而登录态约 1 天就过期，
 * 很多改动没法随手实跑。这个测试把三个接口桩掉，把 **四条返回分支** 都走一遍，
 * 覆盖 ok 判别位、错误返回形状、frames.total / total_all 的语义差别。
 *
 * 用法：  node scripts/test-fetch-lesson.js
 *
 * 被测文件里读的是本仓库自己的源码（非外部输入）；用 vm 在隔离上下文里求值，
 * 不污染本进程。
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const target = process.argv[2] || path.join(__dirname, 'fetch-lesson.js');
const src = fs.readFileSync(target, 'utf8');

const m = src.match(/async function zccFetch\([\s\S]*?\n}\n/);
if (!m) { console.log('❌ 抽不出 zccFetch'); process.exit(1); }

const sessionStorage = { getItem: () => JSON.stringify({ user_id: '9' }) };
const document = { cookie: '' };

function course(title) {
  return { id: '11', course_id: '22', course_title: title, teacher_name: 't',
           teachers: [], room_name: 'r', start_at: 1, end_at: 2, status_label: '回放' };
}
function sched(days) { return { result: { list: days } }; }
function ppt(frames) {
  return { code: 0, total: String(frames.length), page: 1, per_page: 10,
           list: frames.map((f) => ({ created_sec: f.sec,
             content: JSON.stringify({ detecttype: 'ppt', is_key: false, status: 'running',
               pptimgurl: 'https://video.hzcu.edu.cn/ai3/ppt/20261015/x/' + f.sec + '.jpg',
               pptthumb: '', taskid: 'x', created: '0' }) })) };
}
function trans(segs) {
  return { code: 0, msg: 'ok', total: 1, list: [{ all_content: segs, trans_content: '[]',
           sub_id: '11', resource_guid: '', trans_type: 'ainew', zh_num: 100, en_num: 0, en_rate: 0 }] };
}

function mkFetch(s, p, t) {
  return async (url) => {
    if (url.indexOf('get-week-schedules') >= 0) return { json: async () => s };
    if (url.indexOf('search-ppt') >= 0) return { json: async () => p };
    if (url.indexOf('search-trans-result') >= 0) return { json: async () => t };
    throw new Error('unexpected url: ' + url);
  };
}

(async () => {
  const factory = async (fetchImpl) => {
    const sandbox = { fetch: fetchImpl, sessionStorage, document, console, Date, Math, Number, JSON, String, Array, Object, Error, encodeURIComponent };
    const ctx = vm.createContext(sandbox);
    return vm.runInContext('(async () => {' + m[0] + '; return zccFetch; })()', ctx);
  };

  const DAYS = [ { day: '2026-10-15', course: [course('数字媒体传播'), course('媒介环境学导论')] } ];
  const FRAMES = [ { sec: 30 }, { sec: 100 }, { sec: 2500 }, { sec: 2600 }, { sec: 4800 }, { sec: 9000 } ];
  const SEGS = [ { BeginSec: 30, EndSec: 40, Text: 'A', TransText: '' },
                 { BeginSec: 2500, EndSec: 2510, Text: 'B', TransText: '' } ];

  const results = [];
  const run = async (label, s, p, t, args, opts) => {
    const f = await factory(mkFetch(s, p, t));
    let out;
    try { out = await f.apply(null, args.concat([opts])); }
    catch (e) { out = { threw: String(e.message) }; }
    results.push({ label, out });
    return out;
  };

  // ① 无匹配
  const e1 = await run('无匹配', sched([{ day: '2026-10-15', course: [] }]), ppt([]), trans([]), ['2026-10-15', 'x']);
  console.log('① 无匹配      ok=' + e1.ok + '  有 transcript=' + ('transcript' in e1) + '  error=' + (e1.error ? '有' : '无'));

  // ② 多匹配
  const e2 = await run('多匹配', sched(DAYS), ppt([]), trans([]), ['2026-10-15', '']);
  console.log('② 多匹配      ok=' + e2.ok + '  matches=' + (e2.matches ? e2.matches.length : 0));

  // ③ pick 越界
  const e3 = await run('pick越界', sched(DAYS), ppt([]), trans([]), ['2026-10-15', ''], { pick: 9 });
  console.log('③ pick越界    ok=' + e3.ok + '  error=' + (e3.error || '').slice(0, 22));

  // ④ 成功（默认：全量）
  const ok1 = await run('成功-全量', sched(DAYS), ppt(FRAMES), trans(SEGS), ['2026-10-15', '数字媒体']);
  console.log('④ 成功-全量   ok=' + ok1.ok + '  frames.total_all=' + ok1.frames.total_all + '  frames.total=' + ok1.frames.total + '  list=' + ok1.frames.list.length + '  transcript.available=' + ok1.transcript.available);

  // ⑤ 成功 + withFrames:false
  const ok2 = await run('成功-不要帧列表', sched(DAYS), ppt(FRAMES), trans(SEGS), ['2026-10-15', '数字媒体'], { withFrames: false });
  console.log('⑤ withFrames:false  total_all=' + ok2.frames.total_all + '  total=' + ok2.frames.total + '  list=' + ok2.frames.list.length);

  // ⑥ 成功 + 时间窗 [2400,4800]
  const ok3 = await run('成功-按段', sched(DAYS), ppt(FRAMES), trans(SEGS), ['2026-10-15', '数字媒体'], { minSec: 2400, maxSec: 4800 });
  console.log('⑥ 按段[2400,4800]  total_all=' + ok3.frames.total_all + '  total=' + ok3.frames.total + '  list秒=' + JSON.stringify(ok3.frames.list.map((f) => f.sec)) + '  转写段数=' + ok3.transcript.exported);

  // 断言
  const T = [];
  T.push(['三条错误分支都是 ok:false', e1.ok === false && e2.ok === false && e3.ok === false]);
  T.push(['错误分支不带 transcript（形状确实不同）', !('transcript' in e1) && !('transcript' in e2) && !('transcript' in e3)]);
  T.push(['成功分支 ok:true', ok1.ok === true && ok2.ok === true && ok3.ok === true]);
  T.push(['total_all 不受时间窗影响（恒 6）', ok1.frames.total_all === 6 && ok3.frames.total_all === 6]);
  T.push(['total 受时间窗影响（全量 6 / 按段 3）', ok1.frames.total === 6 && ok3.frames.total === 3]);
  T.push(['withFrames:false 只报数不给列表', ok2.frames.total === 6 && ok2.frames.list.length === 0]);
  T.push(['按段只取窗口内帧（2500,2600,4800）', JSON.stringify(ok3.frames.list.map((f) => f.sec)) === '[2500,2600,4800]']);
  T.push(['按段转写只留窗口内段', ok3.transcript.exported === 1]);

  console.log();
  let all = true;
  for (const [n, ok] of T) { console.log((ok ? '✅ ' : '❌ ') + n); if (!ok) all = false; }
  console.log();
  console.log(all ? '✅ 8 条断言全过' : '❌ 有断言失败');
  process.exit(all ? 0 : 1);
})();
