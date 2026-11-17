#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mock_wda.py —— 本地假 WDA 服务，用来【不接手机】验证整套状态机

它伪装成 WebDriverAgent 的 HTTP 接口，内部模拟一个抖音界面流程：

    首页 -> 搜"福袋" -> 搜索结果(直播tab) -> 直播间 -> 福袋面板
         -> 已参与 -> 关闭 -> 回搜索结果 -> 下一张卡片
         -> 卡片用完 -> 换关键词(抽奖) -> 继续

用途：
  1. 改完状态机逻辑先在这里跑通，再上真机，省掉反复插拔调试
  2. 验证点击坐标、关键词匹配、去重、限速是否按预期工作

用法（两个窗口）：
    python mock_wda.py --port 8101
    python douyin_bot.py --url http://127.0.0.1:8101

看完统计：
    curl http://127.0.0.1:8101/mock/stats
"""

import argparse
import base64
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

W, H = 393.0, 852.0
BUNDLE = "com.ss.iphone.ugc.Aweme"

# 1x1 透明 PNG，给 /screenshot 用
TINY_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
            "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

HOME, RESULTS, ROOM, BAG = "home", "results", "room", "bag"


def el(tag, x, y, w, h, label="", name="", value="", visible="true"):
    a = [f'type="XCUIElementType{tag}"', f'x="{x:.0f}"', f'y="{y:.0f}"',
         f'width="{w:.0f}"', f'height="{h:.0f}"', f'visible="{visible}"']
    if label:
        a.append(f'label="{escape(label)}"')
    if name:
        a.append(f'name="{escape(name)}"')
    if value:
        a.append(f'value="{escape(value)}"')
    return f"<XCUIElementType{tag} " + " ".join(a) + " />"


class World:
    """界面状态机 + 点击命中判定。所有方法都要持锁调用。"""

    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with getattr(self, "lock", threading.RLock()):
            self.mode = HOME
            self.kw = ""            # 已输入的关键词
            self.focus = False      # 搜索框是否聚焦
            self.results_kw = ""    # 当前结果页对应的关键词
            self.live_tab = False
            self.used = {}          # kw -> set(卡片标题)
            self.title = ""
            self.done = False
            self.rooms = 0
            self.joins = 0
            self.closes = 0
            self.searches = 0

    # -- 卡片 ------------------------------------------------------------
    def titles(self, kw):
        return [
            f"{kw}专场 新人福利 | 主播小王",
            f"整点{kw}雨 倒计时 | 主播阿杰",
            f"{kw}还剩3分钟 | 小美直播间",
            f"深夜{kw} 送不停 | 主播老陈",
        ]

    def cards(self):
        used = self.used.get(self.results_kw, set())
        out = []
        for i, t in enumerate(self.titles(self.results_kw)):
            if t in used:
                continue
            out.append((i, t))
        return out[:4]

    def card_rect(self, idx):
        return (16, 200 + idx * 160, 361, 120)

    # -- 动作 ------------------------------------------------------------
    def tap(self, x, y):
        with self.lock:
            if self.mode in (HOME, RESULTS):
                if y < 120:                      # 顶部搜索区
                    if x < 320:
                        self.focus = True
                        return "focus-search"
                    if self.kw:                  # 搜索按钮
                        self.results_kw = self.kw
                        self.live_tab = False
                        self.mode = RESULTS
                        self.searches += 1
                        return "search"
                    return "noop"
                if self.mode == RESULTS:
                    if 95 <= y <= 150 and 150 < x < 280:   # 直播 tab
                        self.live_tab = True
                        return "live-tab"
                    if y >= 190:                 # 卡片
                        idx = int((y - 190) // 160)
                        cs = self.cards()
                        for i, t in cs:
                            if i == idx:
                                self.title = t
                                self.mode = ROOM
                                self.done = False
                                self.rooms += 1
                                return "enter-room"
                        return "noop"
                return "noop"

            if self.mode == ROOM:
                if x < 75 and y < 110:           # 关闭
                    return self._close()
                if 320 < x < 393 and 280 < y < 380:   # 福袋入口
                    self.mode = BAG
                    return "open-bag"
                return "noop"

            if self.mode == BAG:
                if x < 75 and y < 110:
                    return self._close()
                if 100 < x < 300 and 600 < y < 700:   # 立即参与
                    if not self.done:
                        self.done = True
                        self.joins += 1
                        return "join"
                    return "already"
                return "noop"
            return "noop"

    def _close(self):
        self.used.setdefault(self.results_kw, set()).add(self.title)
        self.mode = RESULTS
        self.done = False
        self.closes += 1
        return "close"

    def close_top_left(self):  # 兼容测试调用
        with self.lock:
            return self._close()

    def type_text(self, text):
        with self.lock:
            self.kw = text
            return "typed"

    # -- 渲染 ------------------------------------------------------------
    def xml(self):
        with self.lock:
            body = []
            if self.mode == HOME:
                body.append(el("SearchField", 16, 55, 300, 36,
                               label="搜索", name="搜索", value=self.kw))
                body.append(el("Button", 330, 55, 50, 36, label="搜索", name="搜索"))
                for i, t in enumerate(("首页", "朋友", "消息", "我")):
                    body.append(el("Button", 10 + i * 96, 790, 80, 45, label=t))
            elif self.mode == RESULTS:
                body.append(el("SearchField", 16, 55, 300, 36,
                               label="搜索", name="搜索", value=self.results_kw))
                body.append(el("Button", 330, 55, 50, 36, label="搜索", name="搜索"))
                for i, t in enumerate(("综合", "视频", "直播", "用户")):
                    body.append(el("Button", 20 + i * 96, 100, 70, 30, label=t))
                for i, t in self.cards():
                    x, y, w, h = self.card_rect(i)
                    body.append(el("Other", x, y, w, h, label=t))
                if not self.cards():
                    body.append(el("Other", 16, 300, 361, 60,
                                   label="没有更多了"))
            elif self.mode == ROOM:
                body.append(el("Button", 20, 55, 40, 40, label="关闭"))
                body.append(el("Other", 100, 55, 200, 40,
                               label=self.title, name=self.title))
                body.append(el("Other", 320, 300, 60, 60,
                               label="福袋 3分12秒", name="luckybag"))
                body.append(el("TextField", 16, 795, 280, 40,
                               label="说点什么...", name="说点什么..."))
                body.append(el("Button", 330, 795, 50, 40, label="礼物"))
            elif self.mode == BAG:
                body.append(el("Button", 20, 55, 40, 40, label="关闭"))
                body.append(el("Other", 60, 120, 270, 40, label="福袋抽奖"))
                body.append(el("Other", 60, 200, 270, 30,
                               label="开奖倒计时 02:31"))
                if self.done:
                    body.append(el("Other", 100, 620, 190, 50,
                                   label="已参与，等待开奖"))
                else:
                    body.append(el("Button", 120, 620, 150, 50,
                                   label="立即参与"))
            app = (f'<XCUIElementTypeApplication type="XCUIElementTypeApplication" '
                   f'name="抖音" label="抖音" x="0" y="0" width="{W:.0f}" '
                   f'height="{H:.0f}" visible="true">')
            return ('<?xml version="1.0" encoding="UTF-8"?>\n<AppiumAUT>'
                    + app
                    + f'<XCUIElementTypeWindow x="0" y="0" width="{W:.0f}" height="{H:.0f}" visible="true">'
                    + '<XCUIElementTypeOther x="0" y="0" width="393" height="852" visible="true">'
                    + "".join(body)
                    + "</XCUIElementTypeOther></XCUIElementTypeWindow>"
                    + "</XCUIElementTypeApplication></AppiumAUT>")


WORLD = World()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass  # 静音

    # -- 工具 ------------------------------------------------------------
    def _json(self, obj, code=200):
        raw = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode() or "{}")
        except Exception:
            return {}

    # -- 路由 ------------------------------------------------------------
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/status":
            return self._json({"value": {"ready": True, "state": "success",
                                         "message": "mock WDA ready"}})
        if p == "/mock/reset":
            with WORLD.lock:
                WORLD.reset()
            return self._json({"value": "reset"})
        if p == "/mock/stats":
            with WORLD.lock:
                return self._json({"mode": WORLD.mode, "rooms": WORLD.rooms,
                                   "joins": WORLD.joins, "closes": WORLD.closes,
                                   "searches": WORLD.searches,
                                   "kw": WORLD.results_kw})
        if p.endswith("/window/size"):
            return self._json({"value": {"width": W, "height": H}})
        if p.endswith("/source"):
            return self._json({"value": WORLD.xml()})
        if p.endswith("/screenshot"):
            return self._json({"value": TINY_PNG})
        if p.endswith("/wda/activeAppInfo"):
            return self._json({"value": {"bundleId": BUNDLE,
                                         "name": "抖音", "pid": 1234}})
        return self._json({"value": None})

    def do_POST(self):
        p = self.path.split("?")[0]
        b = self._body()
        if p == "/session":
            return self._json({"value": {"sessionId": "mock-session",
                                         "capabilities": {"bundleId": BUNDLE}}})
        if p.endswith("/wda/tap") or p.endswith("/wda/tap/0"):
            act = WORLD.tap(float(b.get("x", 0)), float(b.get("y", 0)))
            return self._json({"value": None, "mock": act})
        if p.endswith("/wda/keys") or p.endswith("/keys"):
            t = b.get("text")
            if t is None:
                v = b.get("value") or []
                t = v[0] if v else ""
            return self._json({"value": None, "mock": WORLD.type_text(t)})
        if p.endswith("/wda/dragfromtoforduration"):
            return self._json({"value": None})
        if p.endswith("/wda/homescreen") or p.endswith("/wda/apps/launch"):
            with WORLD.lock:
                WORLD.reset()
            return self._json({"value": None})
        if p.endswith("/element"):
            return self._json({"value": {"element-6066-11e4-a52e-4f735466cecf": "e1"}})
        if re.search(r"/element/[^/]+/clear$", p):
            with WORLD.lock:
                WORLD.kw = ""
            return self._json({"value": None})
        if re.search(r"/element/[^/]+/click$", p):
            return self._json({"value": None})
        if re.search(r"/element/[^/]+/value$", p):
            return self._json({"value": None})
        return self._json({"value": None})

    def do_DELETE(self):
        self._json({"value": None})


def serve(port=8101):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    srv.daemon_threads = True
    return srv


def main():
    ap = argparse.ArgumentParser(description="假 WDA 服务（离线验证用）")
    ap.add_argument("--port", type=int, default=8101)
    a = ap.parse_args()
    srv = serve(a.port)
    print(f"mock WDA 已启动: http://127.0.0.1:{a.port}")
    print(f"另开窗口: python douyin_bot.py --url http://127.0.0.1:{a.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n统计:", json.dumps({"rooms": WORLD.rooms, "joins": WORLD.joins},
                                    ensure_ascii=False))


if __name__ == "__main__":
    main()
