// ===== QQ 频道帖子关键字提醒 · 后台逻辑 =====
const API = "https://pd.qq.com/qunng/guild/gotrpc/auth/trpc.qchannel.commreader.ComReader/GetGuildFeeds";
const CHANNEL_URL_BASE = "https://pd.qq.com/g/";

const DEFAULTS = {
  guildNumber: "iloveswufe",     // 频道链接 pd.qq.com/g/后面那段
  keywords: [],                  // 由用户在插件窗口里自行填写
  intervalSeconds: 60,           // 检查间隔（秒）。浏览器最快约 30 秒
  sortOption: 1,                 // 1=热门；改成“最新”排序的值需实测确认
  enabled: true,
  pushToken: ""                  // 可选：填了 PushPlus token 就同时推送到微信
};

// QQ 标准 bkn(g_tk) 算法，输入 p_skey
function bkn(pskey) {
  let h = 5381;
  for (let i = 0; i < pskey.length; i++) h += (h << 5) + pskey.charCodeAt(i);
  return h & 2147483647;
}

async function getConfig() {
  return await chrome.storage.local.get(DEFAULTS);
}

async function getPskey() {
  const c = await chrome.cookies.get({ url: "https://pd.qq.com", name: "p_skey" });
  return c ? c.value : null;
}

// 递归收集 QQ 富文本里的 text（帖子文字都在 text_content.text）
function collectText(node, out) {
  if (Array.isArray(node)) {
    for (const x of node) collectText(x, out);
  } else if (node && typeof node === "object") {
    for (const k in node) {
      if (k === "text" && typeof node[k] === "string") out.push(node[k]);
      else collectText(node[k], out);
    }
  }
}
function feedText(feed, key) {
  const out = [];
  collectText(feed[key], out);
  return out.join("");
}

function extract(feed) {
  const id = feed.id || "";
  let title = feedText(feed, "title").trim();
  const content = feedText(feed, "contents").trim();
  if (!title) title = content.slice(0, 30);
  const author = (feed.poster && feed.poster.nick) || "";
  return { id, title, content, author };
}

async function fetchFeeds(cfg) {
  const pskey = await getPskey();
  if (!pskey) {
    throw new Error("没检测到登录态，请先在 Edge 里打开并登录 QQ 频道网页版（pd.qq.com）");
  }
  const url = API + "?bkn=" + bkn(pskey);
  const body = {
    count: 30, from: 7, guild_number: cfg.guildNumber, get_type: 2,
    feedAttchInfo: "", sortOption: Number(cfg.sortOption) || 1,
    need_channel_list: false, need_top_info: false
  };
  const resp = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "x-oidb": '{"uint32_service_type":13}',   // 必需的 OIDB 路由头，缺了会报 no privilege
      "x-qq-client-appid": "537246381"
    },
    body: JSON.stringify(body)
  });
  if (!resp.ok) throw new Error("接口返回 HTTP " + resp.status);
  let data;
  try { data = await resp.json(); }
  catch (e) { throw new Error("接口没返回 JSON —— 登录态可能过期，请重新登录 pd.qq.com"); }
  const feeds = (data && data.data && data.data.vecFeed) || [];
  return { feeds, raw: data };
}

// 可选：推送到微信（PushPlus）。没填 token 就跳过。
async function pushWeixin(cfg, p, matched) {
  if (!cfg.pushToken) return;
  const content =
    "命中关键字：" + matched.join("、") +
    "<br>作者：" + (p.author || "") +
    "<br>标题：" + (p.title || "") +
    "<br>内容：" + (p.content || "").slice(0, 300);
  try {
    await fetch("https://www.pushplus.plus/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: cfg.pushToken,
        title: "[频道监控] " + ((p.title || "新帖命中").slice(0, 30)),
        content: content,
        template: "html"
      })
    });
  } catch (e) { /* 微信推送失败不影响桌面弹窗 */ }
}

function notify(p, matched) {
  chrome.notifications.create("qq_" + p.id, {
    type: "basic",
    iconUrl: "icon128.png",
    title: "频道命中：" + matched.join("、"),
    message: (p.author ? "[" + p.author + "] " : "") + (p.title || "新帖"),
    priority: 2
  });
}

// 核心检查：抓帖子 → 去重 → 匹配 → 弹窗
async function check(isManual) {
  const cfg = await getConfig();
  if (!cfg.enabled && !isManual) return { skipped: true };

  const { feeds, raw } = await fetchFeeds(cfg);
  let debug = "";
  if (feeds.length === 0) {
    debug = "诊断: retcode=" + (raw && raw.retcode) +
      " | msg=" + (raw && (raw.msg || raw.message || "")) +
      " | error=" + JSON.stringify((raw && raw.error) || {}) +
      " | data里的键=[" + Object.keys((raw && raw.data) || {}).join(",") + "]";
  }
  const store = await chrome.storage.local.get({ seen: {}, seeded: false });
  const seen = store.seen || {};
  const seeded = store.seeded;
  const kws = (cfg.keywords || []).map(k => String(k).toLowerCase()).filter(Boolean);

  let newCount = 0, hitCount = 0;
  const hits = [];
  for (const f of feeds) {
    const p = extract(f);
    if (!p.id || seen[p.id]) continue;
    seen[p.id] = (p.title || "").slice(0, 40);
    newCount++;
    if (!seeded) continue;               // 首次只播种，不弹窗
    const hay = (p.title + " " + p.content).toLowerCase();
    const matched = kws.filter(k => hay.includes(k));
    if (matched.length) { hitCount++; hits.push({ p, matched }); }
  }
  // 限制 seen 体积，避免无限增长
  const ids = Object.keys(seen);
  if (ids.length > 300) for (const id of ids.slice(0, ids.length - 300)) delete seen[id];

  // 只有真正拿到帖子才算“已播种”，避免首次抓空后下次把全部帖子当新帖刷屏
  await chrome.storage.local.set({ seen, seeded: seeded || feeds.length > 0, lastCheck: Date.now(), lastError: debug });
  for (const h of hits) {
    notify(h.p, h.matched);          // 桌面弹窗
    await pushWeixin(cfg, h.p, h.matched);  // 若配置了 token，同时推微信
  }
  return { total: feeds.length, newCount, hitCount, firstSeed: !seeded, debug };
}

// 点通知 → 打开频道页
chrome.notifications.onClicked.addListener(async () => {
  const cfg = await getConfig();
  chrome.tabs.create({ url: CHANNEL_URL_BASE + cfg.guildNumber });
});

// 定时器
async function resetAlarm() {
  const cfg = await getConfig();
  await chrome.alarms.clear("poll");
  // 浏览器 alarms 最小约 30 秒；periodInMinutes 支持小数（0.5=30秒）
  const sec = Math.max(30, Number(cfg.intervalSeconds) || 60);
  chrome.alarms.create("poll", { periodInMinutes: sec / 60 });
}
chrome.alarms.onAlarm.addListener(a => {
  if (a.name === "poll") {
    check(false).catch(e => chrome.storage.local.set({ lastError: String(e.message || e) }));
  }
});
chrome.runtime.onInstalled.addListener(resetAlarm);
chrome.runtime.onStartup.addListener(resetAlarm);

// 来自 popup 的消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "test") {
        // 先发一条测试弹窗，确认通知权限正常
        chrome.notifications.create("qq_test", {
          type: "basic", iconUrl: "icon128.png",
          title: "测试通知 ✅", message: "能看到这条，说明弹窗提醒正常工作。", priority: 2
        });
        // 若配置了微信 token，同时发一条测试微信
        const cfg = await getConfig();
        if (cfg.pushToken) {
          await pushWeixin(cfg,
            { author: "", title: "测试推送", content: "能在微信收到这条，说明微信推送也配好了。" },
            ["测试"]);
        }
        const r = await check(true);   // 顺便测接口连通
        sendResponse({ ok: true, result: r });
      } else if (msg.type === "checkNow") {
        const r = await check(true);
        sendResponse({ ok: true, result: r });
      } else if (msg.type === "resetAlarm") {
        await resetAlarm();
        sendResponse({ ok: true });
      } else {
        sendResponse({ ok: false, error: "unknown message" });
      }
    } catch (e) {
      await chrome.storage.local.set({ lastError: String(e.message || e) });
      sendResponse({ ok: false, error: String(e.message || e) });
    }
  })();
  return true; // 保持异步通道
});
