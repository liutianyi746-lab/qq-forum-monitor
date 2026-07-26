#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QQ 频道帖子关键字监控 —— 方案 2a · 做法②（扫码半自动抓接口）

用法：
  python monitor.py --setup       首次运行：开浏览器扫码登录，自动抓取帖子接口，生成 request_template.json
  python monitor.py               循环监控：定时重放接口，命中关键字就推送
  python monitor.py --once        只查一次（调试用），不循环
  python monitor.py --test-push   测试 PushPlus 推送是否配好

依赖：pip install -r requirements.txt  且  python -m playwright install chromium
"""
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

import requests
import yaml

BASE = Path(__file__).resolve().parent
CONFIG_PATH = BASE / "config.yaml"
TEMPLATE_PATH = BASE / "request_template.json"
SAMPLE_PATH = BASE / "sample_response.json"
SEEN_PATH = BASE / "seen.json"
BROWSER_DATA = BASE / "browser_data"

# 用于自动识别帖子字段的候选键名（小写匹配）
ID_KEYS = ["thread_id", "post_id", "feed_id", "tid", "pid", "topic_id", "id"]
TITLE_KEYS = ["title", "subject", "feed_title", "topic_title"]
CONTENT_KEYS = ["content", "summary", "abstract", "plain_content",
                "text", "desc", "description", "brief"]
URL_KEYS = ["jump_url", "share_url", "url", "link", "scheme", "web_url"]


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


# ----------------------------------------------------------------------------
# 配置 / 状态读写
# ----------------------------------------------------------------------------
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        log(f"找不到配置文件 {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen() -> dict:
    if SEEN_PATH.exists():
        try:
            with open(SEEN_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("seen", {})
        except Exception:
            return {}
    return {}


def save_seen(seen: dict) -> None:
    with open(SEEN_PATH, "w", encoding="utf-8") as f:
        json.dump({"seen": seen, "last_check": now_iso()},
                  f, ensure_ascii=False, indent=2)


# ----------------------------------------------------------------------------
# 从任意 JSON 里定位「帖子列表」并抽取字段（字段名未知时靠启发式）
# ----------------------------------------------------------------------------
def _looks_like_posts(dicts: list) -> bool:
    """一组 dict 是否像帖子：多数元素含标题/正文类的键。"""
    if not dicts:
        return False
    hit = 0
    for d in dicts:
        keys = {str(k).lower() for k in d.keys()}
        if any(t in keys for t in TITLE_KEYS + CONTENT_KEYS):
            hit += 1
        elif any(any(tk in k for tk in ("title", "content", "subject")) for k in keys):
            hit += 1
    return hit >= max(1, len(dicts) // 2)


def find_post_list(node) -> list:
    """递归找出最像「帖子列表」的那个 list（元素为 dict）。"""
    best: list = []
    if isinstance(node, list):
        dicts = [x for x in node if isinstance(x, dict)]
        if _looks_like_posts(dicts) and len(dicts) > len(best):
            best = dicts
        for x in node:
            sub = find_post_list(x)
            if len(sub) > len(best):
                best = sub
    elif isinstance(node, dict):
        for v in node.values():
            sub = find_post_list(v)
            if len(sub) > len(best):
                best = sub
    return best


def _first_key(d: dict, candidates: list, override: str = "") -> str:
    """按候选键名（或配置里指定的覆盖键名）取值，转成字符串。"""
    if override:
        if override in d and d[override] not in (None, ""):
            return str(d[override])
        return ""
    lower = {str(k).lower(): k for k in d.keys()}
    for c in candidates:
        if c in lower:
            v = d[lower[c]]
            if isinstance(v, (str, int)) and str(v).strip():
                return str(v)
    return ""


def _collect_text(node) -> str:
    """递归收集 QQ 富文本里所有 text_content.text（帖子文字都在这些 "text" 键里）。"""
    parts = []

    def walk(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if k == "text" and isinstance(v, str):
                    parts.append(v)
                else:
                    walk(v)
        elif isinstance(n, list):
            for x in n:
                walk(x)

    walk(node)
    return "".join(parts)


def find_feeds(body) -> list:
    """定位 QQ GetGuildFeeds 的帖子列表（data.vecFeed）；结构变了则退回通用启发式。"""
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, dict):
            for key in ("vecFeed", "feeds", "feed_list"):
                v = data.get(key)
                if isinstance(v, list) and v:
                    return v
    return find_post_list(body)


def extract_post(feed: dict, field_map: dict = None) -> dict:
    """按 QQ 频道帖子结构抽取 id / 标题 / 正文 / 作者。"""
    if not isinstance(feed, dict):
        return {"id": "", "title": "", "content": "", "url": "", "author": ""}
    pid = str(feed.get("id") or "").strip()
    title = _collect_text(feed.get("title")).strip()
    content = _collect_text(feed.get("contents")).strip()
    if not title:                      # 有的帖子没标题，用正文开头兜底当标题
        title = content[:30]
    author = ""
    poster = feed.get("poster")
    if isinstance(poster, dict):
        author = str(poster.get("nick") or "")
    # 该接口没有现成帖子直链，退回频道页；id 用于去重
    if not pid:
        import hashlib
        pid = "h:" + hashlib.md5((title + content).encode("utf-8")).hexdigest()[:16]
    return {"id": pid, "title": title, "content": content, "url": "", "author": author}


def match_keywords(text: str, keywords: list) -> list:
    t = text.lower()
    return [k for k in keywords if str(k).lower() in t]


# ----------------------------------------------------------------------------
# --setup：扫码登录 + 自动抓取帖子接口
# ----------------------------------------------------------------------------
def cmd_setup(cfg: dict) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log("未安装 playwright，请先执行：python -m pip install -r requirements.txt")
        log("然后：python -m playwright install chromium")
        sys.exit(1)

    url = cfg["channel_url"]
    responses = []

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA),
            headless=False,  # 首次必须有窗口才能扫码
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        # 只收集响应对象，处理放到关闭前，避免在事件回调里做同步调用
        page.on("response", lambda r: responses.append(r))

        log("正在打开频道页面……")
        try:
            page.goto(url, wait_until="load", timeout=60000)
        except Exception as e:
            log(f"打开页面出错（可继续，页面可能仍在加载）：{e}")

        print("\n" + "=" * 56)
        print("请在弹出的浏览器里：")
        print("  1) 扫码登录 QQ 频道")
        print("  2) 确认能看到帖子列表（可上下滑动几下让帖子加载）")
        print("  3) 回到本窗口，按【回车】开始自动抓取接口")
        print("=" * 56)
        try:
            input()
        except EOFError:
            page.wait_for_timeout(20000)

        # 处理收集到的所有 JSON 响应，挑出「帖子最多」的那条作为模板
        candidates = []
        for r in responses:
            try:
                ct = (r.headers.get("content-type") or "").lower()
                if "json" not in ct:
                    continue
                body = r.json()
            except Exception:
                continue
            posts = find_feeds(body)
            if posts:
                # URL 含 feed 的接口（GetGuildFeeds）优先，避免误选到别的响应
                score = len(posts) + (100000 if "feed" in r.url.lower() else 0)
                candidates.append((score, r, body))

        if not candidates:
            log("没抓到像帖子列表的接口。请确认已登录且帖子已显示，再重试 --setup。")
            ctx.close()
            sys.exit(1)

        candidates.sort(key=lambda x: x[0], reverse=True)
        _score, req_resp, body = candidates[0]
        num = len(find_feeds(body))
        req = req_resp.request
        try:
            headers = req.all_headers()
        except Exception:
            headers = dict(req.headers)

        template = {
            "url": req_resp.url,
            "method": req.method,
            "headers": headers,          # 含 cookie，即登录态
            "post_data": req.post_data,
            "captured_at": now_iso(),
        }
        with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        with open(SAMPLE_PATH, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)

        ctx.close()

    log(f"已抓到接口：{template['method']} {template['url']}")
    log(f"该接口本次返回 {num} 条帖子，模板已存 {TEMPLATE_PATH.name}")
    log(f"原始返回已存 {SAMPLE_PATH.name}（如自动识别字段不准，可据此在 config.yaml 的 field_map 里手动指定）")
    # 预览一下识别效果
    posts = find_feeds(body)[:3]
    for d in posts:
        pp = extract_post(d, cfg.get("field_map"))
        log(f"  预览 · 作者[{pp['author']}] 标题「{pp['title'][:30]}」")
    log("完成！接下来执行：python monitor.py")


# ----------------------------------------------------------------------------
# 循环监控
# ----------------------------------------------------------------------------
def replay(template: dict) -> requests.Response:
    # 过滤掉 requests(HTTP/1.1) 不支持的头：
    #  - HTTP/2 伪头（:authority / :method / :path / :scheme，以冒号开头）
    #  - 由 requests 自己管理的头（host / content-length / accept-encoding / connection）
    drop = {"host", "content-length", "accept-encoding", "connection"}
    headers = {}
    for k, v in template.get("headers", {}).items():
        if str(k).startswith(":"):
            continue
        if str(k).lower() in drop:
            continue
        headers[k] = v
    return requests.request(
        template.get("method", "GET"),
        template["url"],
        headers=headers,
        data=template.get("post_data"),
        timeout=30,
    )


def push_pushplus(cfg: dict, title: str, content_html: str) -> None:
    token = cfg.get("pushplus_token", "")
    if not token or "填你的" in token:
        log(f"[未配置 pushplus_token，跳过推送] {title}")
        return
    try:
        r = requests.post(
            "http://www.pushplus.plus/send",
            json={"token": token, "title": title,
                  "content": content_html, "template": "html"},
            timeout=20,
        )
        ok = r.json().get("code") == 200
        log(("推送成功：" if ok else f"推送失败({r.text[:80]})：") + title)
    except Exception as e:
        log(f"推送异常：{e}")


def check_once(cfg: dict, template: dict, seen: dict, first_run: bool) -> None:
    try:
        resp = replay(template)
    except Exception as e:
        log(f"请求接口失败：{e}")
        return

    try:
        body = resp.json()
    except Exception:
        log("接口没返回 JSON —— 登录态可能已过期，请重新执行：python monitor.py --setup")
        return

    posts = find_feeds(body)
    if not posts:
        log("接口正常但没解析到帖子 —— 可能登录态过期或页面结构变了，建议重新 --setup。")
        return

    field_map = cfg.get("field_map")
    keywords = cfg.get("keywords", [])
    new_count, hit_count = 0, 0

    for d in posts:
        pp = extract_post(d, field_map)
        if pp["id"] in seen:
            continue
        seen[pp["id"]] = pp["title"][:40]
        new_count += 1
        if first_run:
            continue  # 首次运行只记录，不推送，避免刷屏
        matched = match_keywords(pp["title"] + " " + pp["content"], keywords)
        if matched:
            hit_count += 1
            link = pp["url"] or cfg["channel_url"]
            content_html = (
                f"<b>命中关键字：</b>{'、'.join(matched)}<br>"
                f"<b>作者：</b>{pp.get('author', '')}<br>"
                f"<b>标题：</b>{pp['title']}<br>"
                f"<b>内容：</b>{pp['content'][:300]}<br>"
                f"<b>去看看：</b><a href='{link}'>{link}</a>"
            )
            push_pushplus(cfg, f"[频道监控] {pp['title'][:30] or '新帖命中'}", content_html)

    save_seen(seen)
    if first_run:
        log(f"首次运行：已记录 {new_count} 条现有帖子（不推送），之后只提醒新帖。")
    else:
        log(f"本轮检查：新帖 {new_count} 条，命中关键字 {hit_count} 条。")


def cmd_monitor(cfg: dict, once: bool = False) -> None:
    if not TEMPLATE_PATH.exists():
        log("还没抓接口。请先执行：python monitor.py --setup")
        sys.exit(1)
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = json.load(f)

    seen = load_seen()
    first_run = len(seen) == 0
    interval = max(1, int(cfg.get("interval_minutes", 3))) * 60

    log(f"开始监控：{cfg['channel_url']}")
    log(f"关键字：{ '、'.join(map(str, cfg.get('keywords', []))) }")
    log(f"间隔：{cfg.get('interval_minutes', 3)} 分钟" + ("（--once 只查一次）" if once else ""))

    while True:
        check_once(cfg, template, seen, first_run)
        first_run = False
        if once:
            break
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("已停止。")
            break


def cmd_test_push(cfg: dict) -> None:
    push_pushplus(cfg, "[频道监控] 测试推送",
                  "如果你在微信收到这条，说明 PushPlus 配好了 ✅")


# ----------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="QQ 频道帖子关键字监控")
    ap.add_argument("--setup", action="store_true", help="扫码登录并抓取帖子接口")
    ap.add_argument("--once", action="store_true", help="只查一次，不循环")
    ap.add_argument("--test-push", action="store_true", help="测试 PushPlus 推送")
    args = ap.parse_args()

    cfg = load_config()
    if args.setup:
        cmd_setup(cfg)
    elif args.test_push:
        cmd_test_push(cfg)
    else:
        cmd_monitor(cfg, once=args.once)


if __name__ == "__main__":
    main()
