#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wizard.py —— 把 --probe 存下来的界面树自动变成 config.json

手抄 label 又慢又容易错，这个脚本直接读 probe/*.xml：

  1. 认出每份 dump 是哪一屏（搜索结果页 / 直播间 / 福袋面板）
  2. 抓出真实文案，填进对应的关键词表
  3. 顺手找出"没有任何文字的小图标"，给出福袋热区坐标建议

用法：
    python wizard.py                  # 扫 probe/ 目录，写入 config.json
    python wizard.py --dir probe --out config.json
    python wizard.py probe/a.xml probe/b.xml
    python wizard.py --dry-run        # 只看不改
"""

import argparse
import glob
import json
import os
import sys
from collections import Counter

try:
    from douyin_bot import DEFAULT_CFG, parse_source
except ImportError as e:
    sys.exit(f"同目录下要能找到 douyin_bot.py: {e}")

# 分类用到的语义线索
BAG_WORDS = ("福袋", "抽奖", "红包", "幸运袋", "锦鲤", "福利")
JOIN_WORDS = ("参与", "领取", "抽取", "抢")
DONE_WORDS = ("已参与", "已参加", "已领", "等待开奖", "已抢光", "已结束")
COND_WORDS = ("关注", "粉丝团", "弹幕", "口令", "分享")
ROOM_HINTS = ("说点什么", "礼物", "在线观众", "人气", "观众")
# 界面骨架文案，不能当关键词用
NOISE = ("搜索", "猜你想搜", "首页", "朋友", "消息", "综合", "视频", "用户",
         "关闭", "返回", "取消", "更多", "分享", "评论")


def load(files):
    """返回 [(文件名, 节点列表, 屏幕宽, 屏幕高)]"""
    out = []
    for f in files:
        try:
            xml = open(f, "r", encoding="utf-8").read()
        except Exception as e:
            print(f"  跳过 {f}: {e}")
            continue
        nodes = parse_source(xml)
        if not nodes:
            print(f"  跳过 {f}: 解析不出节点")
            continue
        # 屏幕尺寸从根节点推
        W = max((n.x + n.w) for n in nodes) or 393.0
        H = max((n.y + n.h) for n in nodes) or 852.0
        out.append((os.path.basename(f), nodes, W, H))
    return out


def guess_screen(nodes, W, H):
    texts = [n.text for n in nodes if n.text]
    joined = " ".join(texts)
    if any(h in joined for h in ROOM_HINTS) and not any(
            "参与" in t for t in texts):
        return "直播间"
    if any(w in joined for w in DONE_WORDS) or any(
            t.strip() in ("立即参与", "参与", "参与抽奖") for t in texts):
        return "福袋面板"
    if "直播" in joined and any(w in joined for w in BAG_WORDS):
        return "搜索结果页"
    return "未识别"


def pick_labels(nodes, words, maxlen=14):
    """抓出含关键词的短文案（长文案多半是标题，不是按钮）"""
    got = []
    for n in nodes:
        t = n.text
        if not t or len(t) > maxlen:
            continue
        if t in NOISE or any(x in t for x in ("搜索", "猜你想搜")):
            continue
        if any(w in t for w in words):
            got.append(t)
    return got


def hotspots(nodes, W, H):
    """无文字、尺寸小、在右侧中部的小方块 —— 纯图标按钮的候选。

    顶部（y<0.20）那排一般是关注/分享/更多，底部是输入栏，都排除掉，
    剩下来最像福袋入口的是面积最大的那个。
    """
    out = []
    for n in nodes:
        if n.text or not n.visible:
            continue
        if n.w > 90 or n.h > 90 or n.w < 18 or n.h < 18:
            continue
        ny = n.cy / H
        if (n.cx / W) < 0.55 or ny < 0.20 or ny > 0.80:
            continue
        out.append(n)
    return sorted(out, key=lambda n: -(n.w * n.h))


def main():
    ap = argparse.ArgumentParser(description="把 probe dump 变成 config.json")
    ap.add_argument("files", nargs="*", help="XML 文件，留空则扫 probe/")
    ap.add_argument("--dir", default="probe")
    ap.add_argument("--out", default="config.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(os.path.join(args.dir, "*.xml")))
    if not files:
        sys.exit(f"没找到 XML。先用 --probe 抓几份：\n"
                 f"  python douyin_bot.py --probe   (在搜索结果页/直播间/福袋面板各跑一次)")

    print(f"读取 {len(files)} 份界面树\n")
    dumps = load(files)
    if not dumps:
        sys.exit("没有可用的界面树")

    found = {"bag": [], "join": [], "done": [], "cond": [], "titles": []}
    hot_hits = []
    seen_screens = {}

    for name, nodes, W, H in dumps:
        screen = guess_screen(nodes, W, H)
        print(f"  {name}  ->  {screen}   ({len(nodes)} 节点, {W:.0f}x{H:.0f})")
        seen_screens[name] = screen

        found["bag"] += pick_labels(nodes, BAG_WORDS)
        found["join"] += pick_labels(nodes, JOIN_WORDS, maxlen=12)
        found["done"] += pick_labels(nodes, DONE_WORDS, maxlen=12)
        found["cond"] += pick_labels(nodes, COND_WORDS, maxlen=12)

        if screen == "搜索结果页":
            # 卡片通常是「标题 | 主播」这种较长文案
            for n in nodes:
                if 0.15 <= n.cy / H <= 0.93 and n.w > 100 and len(n.text) >= 6:
                    if any(w in n.text for w in BAG_WORDS):
                        found["titles"].append(n.text)

        if screen == "直播间":
            hs = hotspots(nodes, W, H)
            hot_hits += [(name, h, W, H) for h in hs[:6]]

    print()
    cfg = dict(DEFAULT_CFG)
    if os.path.isfile(args.out):
        try:
            cfg.update(json.load(open(args.out, encoding="utf-8")))
            print(f"在已有 {args.out} 基础上合并\n")
        except Exception:
            pass

    # --- 关键词 ---------------------------------------------------------
    def merge(key, extra, label):
        old = list(cfg.get(key) or [])
        added, covered = [], 0
        for t in extra:
            t = t.strip()
            if not t or t in old or t in added:
                continue
            if any(o and o in t for o in old):
                covered += 1      # 已能被现有短词命中，加了也是冗余
                continue
            added.append(t)
        if added:
            cfg[key] = old + added
            print(f"  {label:12s} 新增 {len(added):2d} 条: {', '.join(added[:8])}")
        else:
            print(f"  {label:12s} 无新增（现有 {len(old)} 条已覆盖 {covered} 条命中）")

    print("关键词")
    merge("luckyBagKeywords", found["bag"], "福袋入口")
    merge("participateKeywords", found["join"], "参与按钮")
    merge("doneKeywords", found["done"], "已参与标记")
    merge("conditionKeywords", found["cond"], "前置条件")
    if found["titles"]:
        cfg["roomTitleKeywords"] = list(dict.fromkeys(
            (cfg.get("roomTitleKeywords") or []) + found["bag"]))

    # --- 热区 -----------------------------------------------------------
    print("\n纯图标按钮（福袋入口无文字时的热区候选）")
    if not hot_hits:
        print("  没发现。如果你的版本福袋入口有文字，就不用配热区。")
    else:
        for name, h, W, H in hot_hits[:6]:
            rx, ry = h.cx / W, h.cy / H
            print(f"  {name}: 中心 ({rx:.3f}, {ry:.3f})  尺寸 {h.w:.0f}x{h.h:.0f}")
        name, h, W, H = hot_hits[0]
        cfg["bagHotspotX"] = round(h.cx / W, 3)
        cfg["bagHotspotY"] = round(h.cy / H, 3)
        print(f"\n  已把面积最大的那个（最像入口）写进配置: "
              f"bagHotspotX={cfg['bagHotspotX']}, bagHotspotY={cfg['bagHotspotY']}")
        print("  ⚠ 这是猜的，上机后如果点歪了，用截图量一下再改。")

    if args.dry_run:
        print("\n--dry-run，未写入")
        return

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f"\n已写入 {args.out}")
    print("下一步: python douyin_bot.py --duration 120   # 先短跑两分钟看看")


if __name__ == "__main__":
    main()
