#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
douyin_bot.py —— 通过 WebDriverAgent 驱动【官方】抖音，自动进直播间参与福袋

不需要解密 IPA，不需要注入，不需要越狱。
抖音永远是最新版官方包，WDA 是 Apple 自己的 UI 测试框架。

依赖：
    pip install requests tidevice

典型用法：
    # 1) 端口转发（另开一个窗口，保持运行）
    tidevice wdaproxy -p 8100 -B com.facebook.WebDriverAgentRunner.xctrunner

    # 2) 校准：只 dump 界面树，不点任何东西
    python douyin_bot.py --probe

    # 3) 正式跑
    python douyin_bot.py

状态机与 iOS 注入版完全一致：
    搜索关键词 -> 挑含"福袋"的直播卡片 -> 进房 -> 找福袋入口 -> 参与 -> 立刻退出 -> 下一个

识别方式从 OCR 换成 WDA 的无障碍树（更准：直接拿到按钮文案）。
"""

import argparse
import json
import os
import random
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime

try:
    import requests
except ImportError:
    sys.exit("缺少依赖，先执行: pip install requests tidevice")

DEFAULT_BUNDLE = "com.ss.iphone.ugc.Aweme"


# ---------------------------------------------------------------- WDA 客户端

class WDA:
    """极简 WebDriverAgent 客户端，只实现用得到的接口。"""

    def __init__(self, base: str, bundle: str, timeout: float = 25.0):
        self.base = base.rstrip("/")
        self.bundle = bundle
        self.sid = None
        self.timeout = timeout
        self.http = requests.Session()
        self._log = Log.get()

    # -- 底层 ------------------------------------------------------------
    def req(self, method: str, path: str, body=None, timeout=None):
        url = self.base + path
        try:
            r = self.http.request(method, url, json=body,
                                  timeout=timeout or self.timeout)
        except Exception as e:
            self._log(f"[WDA] {method} {path} 连接失败: {e}")
            return None
        if r.status_code >= 400:
            self._log(f"[WDA] {method} {path} -> {r.status_code} {r.text[:200]}")
            return None
        if not r.content:
            return {}
        try:
            return r.json()
        except Exception:
            return None

    def status(self):
        return self.req("GET", "/status", timeout=5)

    def alive(self) -> bool:
        j = self.status()
        return bool(j and j.get("value"))

    # -- 会话 ------------------------------------------------------------
    def new_session(self) -> bool:
        """WDA 独立运行时两种 payload 都试一遍（W3C / 老版 desiredCapabilities）。"""
        payloads = [
            {"capabilities": {"alwaysMatch": {
                "bundleId": self.bundle,
                "shouldWaitForQuiescence": False,
                "noReset": True,
                "newCommandTimeout": 0,
            }}},
            {"desiredCapabilities": {
                "bundleId": self.bundle,
                "shouldWaitForQuiescence": False,
                "noReset": True,
            }},
        ]
        for p in payloads:
            j = self.req("POST", "/session", p, timeout=60)
            if not j:
                continue
            val = j.get("value") or {}
            sid = val.get("sessionId") or (val.get("capabilities") or {}).get("sessionId")
            if sid:
                self.sid = sid
                self._log(f"[WDA] 会话建立 sid={sid}")
                return True
        return False

    # -- 屏幕 ------------------------------------------------------------
    def window_size(self):
        j = self.req("GET", f"/session/{self.sid}/window/size")
        if not j:
            return None
        v = j.get("value") or {}
        if "width" in v:
            return (v["width"], v["height"])
        return None

    def source(self) -> str:
        j = self.req("GET", f"/session/{self.sid}/source", timeout=30)
        if not j:
            return ""
        v = j.get("value")
        return v if isinstance(v, str) else ""

    def screenshot(self, path: str) -> bool:
        import base64
        j = self.req("GET", "/screenshot", timeout=30)
        if not j or not isinstance(j.get("value"), str):
            return False
        with open(path, "wb") as f:
            f.write(base64.b64decode(j["value"]))
        return True

    # -- 动作 ------------------------------------------------------------
    def tap(self, x: float, y: float) -> bool:
        """按坐标点击。优先用 wda/tap，失败退化到 wda/tap/0。"""
        for path in (f"/session/{self.sid}/wda/tap", f"/session/{self.sid}/wda/tap/0"):
            if self.req("POST", path, {"x": x, "y": y}, timeout=15):
                return True
        return False

    def drag(self, x1, y1, x2, y2, duration=0.35) -> bool:
        body = {"fromX": x1, "fromY": y1, "toX": x2, "toY": y2,
                "duration": duration}
        return bool(self.req("POST", f"/session/{self.sid}/wda/dragfromtoforduration",
                             body, timeout=20))

    def home(self) -> bool:
        return bool(self.req("POST", f"/session/{self.sid}/wda/homescreen",
                             {}, timeout=15))

    def launch(self) -> bool:
        return bool(self.req("POST", f"/session/{self.sid}/wda/apps/launch",
                             {"bundleId": self.bundle}, timeout=30))

    def active_app(self):
        j = self.req("GET", f"/session/{self.sid}/wda/activeAppInfo")
        return (j or {}).get("value") or {}

    def keys(self, text: str) -> bool:
        """往当前焦点输入框写字（中文直接 set，不需要键盘联想）。"""
        for path in (f"/session/{self.sid}/wda/keys",
                     f"/session/{self.sid}/keys"):
            if self.req("POST", path, {"value": [text], "text": text}, timeout=20):
                return True
        return False

    def find(self, xpath: str):
        j = self.req("POST", f"/session/{self.sid}/element",
                     {"using": "xpath", "value": xpath}, timeout=20)
        v = (j or {}).get("value") or {}
        return v.get("element-6066-11e4-a52e-4f735466cecf") or v.get("ELEMENT")

    def click_element(self, eid: str) -> bool:
        return bool(self.req("POST", f"/session/{self.sid}/element/{eid}/click",
                             {}, timeout=20))

    def set_value(self, eid: str, text: str) -> bool:
        return bool(self.req("POST", f"/session/{self.sid}/element/{eid}/value",
                             {"value": [text], "text": text}, timeout=20))

    def clear_element(self, eid: str) -> bool:
        return bool(self.req("POST", f"/session/{self.sid}/element/{eid}/clear",
                             {}, timeout=15))


# ---------------------------------------------------------------- 界面树

class Node:
    __slots__ = ("type", "label", "name", "value", "x", "y", "w", "h", "visible")

    def __init__(self, d):
        self.type = d.get("type", "")
        self.label = (d.get("label") or "").strip()
        self.name = (d.get("name") or "").strip()
        self.value = (d.get("value") or "").strip()
        try:
            self.x = float(d.get("x", 0)); self.y = float(d.get("y", 0))
            self.w = float(d.get("width", 0)); self.h = float(d.get("height", 0))
        except Exception:
            self.x = self.y = self.w = self.h = 0.0
        self.visible = str(d.get("visible", "true")).lower() == "true"

    @property
    def text(self) -> str:
        seen, out = set(), []
        for t in (self.label, self.name, self.value):
            if t and t not in seen:
                seen.add(t); out.append(t)
        return " | ".join(out)

    @property
    def cx(self) -> float: return self.x + self.w / 2.0
    @property
    def cy(self) -> float: return self.y + self.h / 2.0
    def __repr__(self):
        return f"<{self.type} {self.text[:40]!r} @{int(self.cx)},{int(self.cy)} {int(self.w)}x{int(self.h)}>"


def parse_source(xml: str):
    """把 WDA 的 page source 解析成节点列表。属性都在子元素上，遍历即可。"""
    if not xml:
        return []
    # source 里可能有控制字符，先清掉
    xml = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", xml)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # 截断的 XML 兜底：用正则粗略抓元素
        nodes = []
        for m in re.finditer(r"<XCUIElementType(\w+)([^>]*)/?>", xml):
            attrs = dict(re.findall(r'(\w+)="([^"]*)"', m.group(2)))
            attrs["type"] = "XCUIElementType" + m.group(1)
            nodes.append(Node(attrs))
        return nodes

    nodes = []
    for el in root.iter():
        if not el.tag.startswith("XCUIElementType"):
            continue
        d = dict(el.attrib)
        d["type"] = el.tag
        n = Node(d)
        if n.w > 0 and n.h > 0:
            nodes.append(n)
    return nodes


# ---------------------------------------------------------------- 日志

class Log:
    _inst = None

    def __init__(self, path="bot.log"):
        self.path = path
        self.t0 = time.time()

    @classmethod
    def get(cls):
        if cls._inst is None:
            cls._inst = Log()
        return cls._inst

    def __call__(self, msg):
        ts = f"{time.time() - self.t0:7.1f}s"
        line = f"[{datetime.now():%m-%d %H:%M:%S} {ts}] {msg}"
        print(line, flush=True)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------- 配置

DEFAULT_CFG = {
    "bundleId": DEFAULT_BUNDLE,
    "wdaUrl": "http://127.0.0.1:8100",

    "searchKeywords": ["福袋", "抽奖"],
    "roomTitleKeywords": ["福袋", "抽奖", "红包", "福利"],
    "luckyBagKeywords": ["福袋", "抽奖", "红包雨", "幸运袋"],
    "participateKeywords": ["立即参与", "立即抽奖", "参与抽奖", "点击参与", "参与", "立即领取"],
    "doneKeywords": ["已参与", "已参加", "已领", "等待开奖", "已抢光"],
    "conditionKeywords": ["关注主播", "加入粉丝团", "发送弹幕", "发送口令"],

    "enterWait": 3.5,
    "roomStaySeconds": 45,
    "maxRoomsPerRound": 30,
    "maxRoomsPerHour": 60,
    "tickInterval": 1.5,
    "jitterMin": 0.8,
    "jitterMax": 2.2,

    "autoFollow": False,
    "autoJoinFansClub": False,
    "autoComment": False,
    "commentText": "福袋",

    # 福袋入口没有任何无障碍文案时的兜底热区（归一化坐标，0 = 不启用）
    "bagHotspotX": 0.0,
    "bagHotspotY": 0.0,

    "saveScreenshotOnFail": False,
}


class Cfg:
    def __init__(self, path="config.json"):
        self.d = dict(DEFAULT_CFG)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self.d.update(json.load(f))
            except Exception as e:
                print(f"配置读取失败，用默认值: {e}")
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CFG, f, ensure_ascii=False, indent=2)
            print(f"已生成默认配置: {path}")

    def __getitem__(self, k):
        return self.d.get(k, DEFAULT_CFG.get(k))

    def __getattr__(self, k):
        if k in self.d:
            return self.d[k]
        if k in DEFAULT_CFG:
            return DEFAULT_CFG[k]
        raise AttributeError(k)


# ---------------------------------------------------------------- 状态机

SEARCH_INPUT, RESULTS, ROOM, PARTICIPATE, EXIT, COOLDOWN = range(6)
STATE_NAME = ["搜索入口", "输入关键词", "挑直播间", "房间内识别", "参与福袋", "退出房间", "冷却"]


class Bot:
    def __init__(self, wda: WDA, cfg: Cfg):
        self.w = wda
        self.c = cfg
        self.log = Log.get()

        self.W, self.H = 390.0, 844.0
        self.state = SEARCH_INPUT
        self.state_since = time.time()
        self.next_action = 0.0

        self.kw_index = 0
        self.rooms_this_round = 0
        self.entered = 0
        self.success = 0
        self.tried = set()
        self.hotspot_tried = False
        self.room_enter_ts = 0.0
        self.entry_times = []
        self.tapped_live_tab = False
        self.room_title = ""
        self.running = True

    # -- 工具 ------------------------------------------------------------
    def goto(self, st, delay=0.0):
        self.state = st
        self.state_since = time.time()
        self.next_action = self.state_since + delay

    def elapsed(self):
        return time.time() - self.state_since

    def jitter(self):
        lo = max(0.1, float(self.c.jitterMin))
        hi = max(lo, float(self.c.jitterMax))
        return random.uniform(lo, hi)

    def keyword(self):
        kws = self.c.searchKeywords or ["福袋"]
        return kws[self.kw_index % len(kws)]

    def next_keyword(self):
        self.kw_index += 1
        self.rooms_this_round = 0
        self.tried.clear()
        self.tapped_live_tab = False
        self.log(f"切换关键词 -> {self.keyword()}")

    def nodes(self):
        return parse_source(self.w.source())

    def pick(self, nodes, keywords, ymin=0.0, ymax=1.0, min_h=0.0, min_text=2):
        """按关键词优先级挑第一个命中节点（坐标按屏幕归一化过滤）。"""
        for kw in keywords:
            for n in nodes:
                if not n.visible or len(n.text) < min_text:
                    continue
                if kw not in n.text:
                    continue
                ny = n.cy / self.H
                if not (ymin <= ny <= ymax):
                    continue
                if n.h < min_h:
                    continue
                return n
        return None

    def tap_node(self, n: Node, tag=""):
        if not n:
            return False
        ok = self.w.tap(n.cx, n.cy)
        self.log(f"点击 {tag}「{n.text[:30]}」({int(n.cx)},{int(n.cy)}) {'✓' if ok else '✗'}")
        return ok

    def dump(self, nodes, limit=40):
        for n in nodes[:limit]:
            self.log(f"   {n}")

    # -- 位置细节 --------------------------------------------------------
    FIELD_TYPES = ("XCUIElementTypeTextField", "XCUIElementTypeSearchField")

    def find_search_field(self, nodes):
        """搜索输入框。优先真正的输入控件，其次才看文案（顶部 30% 区域）。"""
        best = None
        for n in nodes:
            if not n.visible or (n.cy / self.H) > 0.30:
                continue
            if n.type in self.FIELD_TYPES:
                return n
            if best is None and n.w > 0.4 * self.W and \
                    any(k in n.text for k in ("搜索", "猜你想搜")):
                best = n
        return best

    def find_search_button(self, nodes):
        """「搜索」按钮。必须排除输入框本身，否则会点回输入框导致搜不出去。"""
        cands = []
        for n in nodes:
            if not n.visible or n.type in self.FIELD_TYPES:
                continue
            if (n.cy / self.H) > 0.24:
                continue
            if n.text.strip() != "搜索" and "搜索" not in n.text:
                continue
            if n.w > 0.45 * self.W:      # 整条搜索栏，不是按钮
                continue
            cands.append(n)
        if not cands:
            return None
        # 右侧那个才是按钮（左侧是输入框/返回）
        return max(cands, key=lambda n: n.cx)

    def clear_search_field(self):
        """把输入框里上一次的关键词清掉，否则新词会追加成「福袋抽奖」。"""
        eid = self.w.find("//XCUIElementTypeSearchField | //XCUIElementTypeTextField")
        if not eid:
            return
        if self.w.clear_element(eid):
            return
        # 兜底：按退格
        for _ in range(12):
            if not self.w.keys("\b"):
                break

    def find_bag(self, nodes):
        """找福袋/抽奖入口。要避开房间标题（很多标题本身就写「福袋专场」）。"""
        for kw in self.c.luckyBagKeywords:
            for n in nodes:
                if not n.visible or kw not in n.text:
                    continue
                ny = n.cy / self.H
                if ny < 0.16 or ny > 0.95:      # 顶部标题栏 / 底部输入栏
                    continue
                if n.text == self.room_title:    # 就是标题本身
                    continue
                if n.w > 0.6 * self.W and n.h > 0.12 * self.H:   # 整块容器
                    continue
                return n
        return None

    # -- 各状态 ----------------------------------------------------------
    def escape_room(self, nodes) -> bool:
        """当前停在直播间/福袋面板里时先退出来，否则后面所有判断都会错位。"""
        inside = self.pick(nodes, ["说点什么", "礼物", "在线观众", "人气"])
        if not inside:
            return False
        for kw in ("关闭", "返回"):
            for n in nodes:
                if kw in n.text and (n.cx / self.W) < 0.25 and (n.cy / self.H) < 0.25:
                    self.log(f"启动/异常时停在房内，点「{kw}」退出")
                    self.tap_node(n, kw)
                    self.goto(SEARCH_INPUT, 2.0)
                    return True
        self.log("停在房内但没找到关闭按钮，用边缘手势返回")
        self.w.drag(2, self.H / 2, self.W * 0.75, self.H / 2, 0.3)
        self.goto(SEARCH_INPUT, 2.0)
        return True

    def do_search_input(self, nodes):
        kw = self.keyword()

        # 先排除"停在直播间里"的情况（冷启动最常见）
        if self.escape_room(nodes):
            return

        # 已经在搜索结果页
        if self.pick(nodes, [kw], ymin=0.12, ymax=0.95):
            self.log("检测到搜索结果页")
            self.goto(RESULTS, 1.0)
            return

        if self.elapsed() < 1.5:
            return

        # 点搜索框
        field = self.find_search_field(nodes)
        if field:
            self.tap_node(field, "搜索框")
            time.sleep(0.8)
            self.clear_search_field()

        if not self.w.keys(kw):
            # 退化：直接用元素 set value
            eid = self.w.find("//XCUIElementTypeSearchField | //XCUIElementTypeTextField")
            if eid:
                self.w.set_value(eid, kw)
                self.log(f"用元素写入关键词 {kw}")
            else:
                self.log("写不进关键词，本轮回退首页")
                self.w.launch(); time.sleep(2)
                self.goto(SEARCH_INPUT, 2.5)
                return

        self.log(f"关键词已输入: {kw}")
        time.sleep(1.0)
        btn = self.find_search_button(nodes)
        if btn:
            self.tap_node(btn, "搜索按钮")
        else:
            self.log("没找到搜索按钮，按回车提交")
            eid = self.w.find("//XCUIElementTypeSearchField | //XCUIElementTypeTextField")
            if eid:
                self.w.req("POST", f"/session/{self.w.sid}/element/{eid}/value",
                           {"value": ["\n"]}, timeout=10)
        self.goto(RESULTS, 3.0)

    def do_results(self, nodes):
        if self.rooms_this_round >= int(self.c.maxRoomsPerRound):
            self.log("本轮达到上限，换关键词")
            self.next_keyword()
            self.goto(SEARCH_INPUT, self.jitter())
            return

        # 切「直播」tab（只在屏幕上 1/3 找，避免误点标题）
        if not self.tapped_live_tab:
            tab = self.pick(nodes, ["直播"], ymin=0.05, ymax=0.32, min_text=2)
            if tab:
                self.tap_node(tab, "直播tab")
                self.tapped_live_tab = True
                self.goto(RESULTS, 2.0)
                return

        # 挑标题含关键词的卡片
        card = None
        for n in nodes:
            if not n.visible:
                continue
            ny = n.cy / self.H
            if ny < 0.15 or ny > 0.93:
                continue
            if len(n.text) < 4 or n.w < 100:
                continue
            if n.text in self.tried:
                continue
            if any(kw in n.text for kw in self.c.roomTitleKeywords):
                card = n
                break

        if not card:
            self.log("当前列表没有新房间，换关键词")
            self.next_keyword()
            self.goto(SEARCH_INPUT, self.jitter() + 0.5)
            return

        if not self.hourly_allows():
            self.goto(RESULTS, 30.0)
            return

        title = card.text[:40]
        self.tried.add(card.text)
        self.rooms_this_round += 1
        self.entered += 1
        self.entry_times.append(time.time())
        self.room_title = card.text
        self.room_enter_ts = time.time()
        self.hotspot_tried = False
        self.log(f"进入直播间 #{self.entered}: {title}")
        self.tap_node(card, "直播间卡片")
        self.goto(ROOM, float(self.c.enterWait))

    def do_room(self, nodes):
        # 驻留上限
        if time.time() - self.room_enter_ts > float(self.c.roomStaySeconds):
            self.log(f"驻留超 {self.c.roomStaySeconds}s，强制退出")
            self.goto(EXIT)
            return

        bag = self.find_bag(nodes)
        if bag:
            self.log(f"发现福袋入口: {bag.text[:30]}")
            self.tap_node(bag, "福袋")
            self.goto(PARTICIPATE, 1.8)
            return

        direct = self.pick(nodes, self.c.participateKeywords)
        if direct:
            self.tap_node(direct, "参与")
            self.goto(PARTICIPATE, 1.5)
            return

        # 福袋入口没有无障碍文案：用校准过的热区试探一次
        hx, hy = float(self.c.bagHotspotX), float(self.c.bagHotspotY)
        if (not self.hotspot_tried) and hx > 0.01 and hy > 0.01 and self.elapsed() > 2.0:
            self.hotspot_tried = True
            self.log(f"无文案命中，热区试探点 ({hx:.2f},{hy:.2f})")
            self.w.tap(hx * self.W, hy * self.H)
            self.goto(PARTICIPATE, 1.8)
            return

        if self.elapsed() > 7.0:
            # 确认是不是真的在直播间
            if self.pick(nodes, ["说点什么", "礼物", "人气", "在线"]):
                self.log("房间内没有福袋，退出")
            else:
                self.log("没进到直播间，退回重选")
            self.goto(EXIT)

    def do_participate(self, nodes):
        if self.pick(nodes, self.c.doneKeywords):
            self.success += 1
            self.log(f"✅ 参与成功（累计 {self.success}）")
            self.goto(EXIT, 0.5)
            return

        cond = self.pick(nodes, self.c.conditionKeywords)
        if cond:
            t = cond.text
            if "关注" in t and self.c.autoFollow:
                self.tap_node(cond, "关注"); self.goto(PARTICIPATE, 1.8); return
            if "粉丝团" in t and self.c.autoJoinFansClub:
                self.tap_node(cond, "粉丝团"); self.goto(PARTICIPATE, 2.0); return
            if ("弹幕" in t or "口令" in t) and self.c.autoComment:
                self.w.keys(self.c.commentText); self.goto(PARTICIPATE, 1.2); return
            self.log(f"需要前置条件「{t[:20]}」，未开启自动处理，跳过")
            self.goto(EXIT)
            return

        btn = self.pick(nodes, self.c.participateKeywords)
        if btn:
            self.tap_node(btn, "参与按钮")
            self.goto(PARTICIPATE, 1.6)
            return

        if self.elapsed() > 9.0:
            self.log("参与超时，放弃本房间")
            self.goto(EXIT)

    def do_exit(self, nodes):
        # 优先点关闭/返回，保留搜索结果页的滚动位置
        back = None
        for kw in ("关闭", "返回", "×"):
            for n in nodes:
                if kw in n.text and (n.cx / self.W) < 0.25 and (n.cy / self.H) < 0.25:
                    back = n
                    break
            if back:
                break

        if back:
            self.tap_node(back, "关闭")
        else:
            # 左边缘右滑返回
            self.log("没找到关闭按钮，用边缘手势返回")
            self.w.drag(2, self.H / 2, self.W * 0.75, self.H / 2, 0.3)

        self.goto(COOLDOWN, self.jitter() + 1.0)

    def do_cooldown(self, nodes):
        if self.elapsed() > 2.0:
            self.goto(RESULTS, 0.3)

    # -- 主循环 ----------------------------------------------------------
    def hourly_allows(self) -> bool:
        """每小时进房数限流。超了就停在这儿等，直到窗口滑出配额。"""
        now = time.time()
        self.entry_times = [t for t in self.entry_times if now - t <= 3600]
        limit = int(self.c.maxRoomsPerHour)
        if len(self.entry_times) >= limit:
            wait = 3600 - (now - self.entry_times[0]) + 5
            self.log(f"已达每小时 {limit} 个上限，等待 {int(wait)}s")
            return False
        return True

    def check_foreground(self):
        info = self.w.active_app()
        bid = info.get("bundleId") or ""
        if bid and bid != self.c.bundleId:
            self.log(f"抖音不在前台（当前 {bid}），拉回前台")
            self.w.launch()
            time.sleep(2.5)
            return False
        return True

    def run(self, duration=0.0):
        self.log("===== 开始 =====")
        deadline = time.time() + duration if duration > 0 else 0.0
        while self.running:
            try:
                if deadline and time.time() > deadline:
                    self.log(f"到达设定时长 {int(duration)}s，正常结束")
                    break

                if not self.check_foreground():
                    self.goto(SEARCH_INPUT, 1.0)
                    continue

                if time.time() < self.next_action:
                    time.sleep(0.2)
                    continue

                nodes = self.nodes()
                if not nodes:
                    self.log("拿不到界面树，重试")
                    time.sleep(1.5)
                    continue

                st = self.state
                {
                    SEARCH_INPUT: self.do_search_input,
                    RESULTS: self.do_results,
                    ROOM: self.do_room,
                    PARTICIPATE: self.do_participate,
                    EXIT: self.do_exit,
                    COOLDOWN: self.do_cooldown,
                }[st](nodes)

                time.sleep(float(self.c.tickInterval))
            except KeyboardInterrupt:
                self.log("手动中断")
                break
            except Exception:
                self.log("主循环异常:\n" + traceback.format_exc())
                time.sleep(3)

        self.log(f"===== 结束  进房 {self.entered} / 成功 {self.success} =====")

    def probe(self, save_xml=True, outdir="probe"):
        """探测模式：只 dump 界面树，不点任何东西。"""
        nodes = self.nodes()
        self.log(f"===== 界面树 {len(nodes)} 个节点 =====")
        self.dump(nodes, limit=80)
        if save_xml:
            os.makedirs(outdir, exist_ok=True)
            stamp = time.strftime("%H%M%S")
            xml = self.w.source()
            fn = os.path.join(outdir, f"dump_{stamp}.xml")
            with open(fn, "w", encoding="utf-8") as f:
                f.write(xml or "")
            self.log(f"原始 XML 已保存: {fn}")
            shot = os.path.join(outdir, f"shot_{stamp}.png")
            if self.w.screenshot(shot):
                self.log(f"截图已保存: {shot}")
        self.log("提示：分别停在「搜索结果页」「直播间」「福袋面板」各跑一次 --probe，"
                 "然后执行 python wizard.py 自动生成关键词")


# ---------------------------------------------------------------- 入口

def main():
    ap = argparse.ArgumentParser(description="抖音直播福袋自动参与（WDA 驱动，官方包）")
    ap.add_argument("--url", default=None, help="WDA 地址，默认取 config 里的 wdaUrl")
    ap.add_argument("--bundle", default=None, help="抖音 bundleId")
    ap.add_argument("--config", default="config.json")
    ap.add_argument("--probe", action="store_true", help="探测模式：只打印界面树，不点击")
    ap.add_argument("--size", default=None, help="屏幕逻辑尺寸，如 393x852（自动读不到时手动指定）")
    ap.add_argument("--duration", type=float, default=0,
                    help="限定运行秒数，0 表示一直跑（到点正常退出）")
    ap.add_argument("--reset", action="store_true",
                    help="启动前把抖音重启一次，避免停在某个直播间里")
    args = ap.parse_args()

    cfg = Cfg(args.config)
    if args.url:
        cfg.d["wdaUrl"] = args.url
    if args.bundle:
        cfg.d["bundleId"] = args.bundle

    wda = WDA(cfg.wdaUrl, cfg.bundleId)
    log = Log.get()

    log(f"连接 WDA: {cfg.wdaUrl}")
    if not wda.alive():
        sys.exit(
            "连不上 WDA。检查:\n"
            "  1) tidevice wdaproxy -p 8100 -B com.facebook.WebDriverAgentRunner.xctrunner 是否在跑\n"
            "  2) 手机是否解锁、USB 是否信任\n"
            "  3) WDA 是否已用你的证书签名安装"
        )

    if not wda.new_session():
        sys.exit("WDA 会话建立失败（一般是 bundleId 不对，或 WDA 版本与 iOS 不匹配）")

    bot = Bot(wda, cfg)
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            bot.W, bot.H = float(w), float(h)
        except Exception:
            log("--size 格式应为 393x852")
    else:
        sz = wda.window_size()
        if sz:
            bot.W, bot.H = sz
        log(f"屏幕逻辑尺寸: {bot.W} x {bot.H}")

    if args.probe:
        bot.probe()
        return

    if args.reset:
        log("重启抖音…")
        wda.launch()
        time.sleep(4.0)

    try:
        bot.run(duration=args.duration)
    finally:
        try:
            wda.req("DELETE", f"/session/{wda.sid}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
