const DEFAULTS = {
  guildNumber: "iloveswufe",
  keywords: ["保研", "调剂", "实习", "内推"],
  intervalSeconds: 60,
  enabled: true,
  pushToken: ""
};

const $ = id => document.getElementById(id);
const statusEl = () => $("status");

function setStatus(text) { statusEl().textContent = text; }

async function load() {
  const c = await chrome.storage.local.get(DEFAULTS);
  $("enabled").checked = !!c.enabled;
  $("keywords").value = (c.keywords || []).join("\n");
  $("guild").value = c.guildNumber || "";
  $("interval").value = c.intervalSeconds || 60;
  $("pushToken").value = c.pushToken || "";

  const meta = await chrome.storage.local.get({ lastCheck: 0, lastError: "" });
  if (meta.lastError) setStatus("上次出错：" + meta.lastError);
  else if (meta.lastCheck) setStatus("上次检查：" + new Date(meta.lastCheck).toLocaleString("zh-CN"));
}

async function save() {
  const cfg = {
    enabled: $("enabled").checked,
    keywords: $("keywords").value.split("\n").map(s => s.trim()).filter(Boolean),
    guildNumber: $("guild").value.trim() || "iloveswufe",
    intervalSeconds: Math.max(30, parseInt($("interval").value, 10) || 60),
    pushToken: $("pushToken").value.trim()
  };
  await chrome.storage.local.set(cfg);
  await chrome.runtime.sendMessage({ type: "resetAlarm" });
  setStatus("已保存 ✅  监控" + (cfg.enabled ? "已开启" : "已关闭"));
}

function send(type, okMsg) {
  setStatus("处理中…");
  chrome.runtime.sendMessage({ type }, resp => {
    if (chrome.runtime.lastError) { setStatus("出错：" + chrome.runtime.lastError.message); return; }
    if (!resp || !resp.ok) { setStatus("失败：" + (resp && resp.error || "未知错误")); return; }
    const r = resp.result || {};
    const tail = r.debug ? "\n" + r.debug : "";
    if (r.firstSeed) setStatus(okMsg + "\n首次运行：已记录当前 " + (r.newCount || 0) + " 条帖子（不弹窗），之后有新帖命中才提醒。" + tail);
    else setStatus(okMsg + "\n本次：抓到 " + (r.total || 0) + " 条，新帖 " + (r.newCount || 0) + " 条，命中 " + (r.hitCount || 0) + " 条。" + tail);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  load();
  $("save").addEventListener("click", save);
  $("test").addEventListener("click", () => send("test", "测试完成：如果没弹窗，请到系统设置允许 Edge 通知。"));
  $("check").addEventListener("click", () => send("checkNow", "检查完成。"));
});
