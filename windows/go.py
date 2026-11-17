#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
go.py —— 一个入口管到底：环境体检 / 起 WDA 代理 / 引导校准 / 开跑

    python go.py            # 体检 -> 起 wdaproxy -> 直接开跑
    python go.py doctor     # 只体检，不跑
    python go.py probe      # 引导式校准：三个界面各抓一份 dump，自动生成 config
    python go.py mock       # 起本地模拟器（不用手机也能验证逻辑）

额外的参数会原样转给 douyin_bot.py，例如：
    python go.py --duration 600 --config my.json
"""

import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

# Windows 控制台默认是 GBK，日志里的 ✅ 之类会直接抛 UnicodeEncodeError
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BUNDLE = "com.facebook.WebDriverAgentRunner.xctrunner"
PORT = 8100

OK = "[ OK ]"
BAD = "[FAIL]"
WARN = "[ !  ]"


def say(tag, msg):
    print(f"{tag} {msg}", flush=True)


# ------------------------------------------------------------ 体检

def check_python():
    v = sys.version_info
    if v < (3, 8):
        say(BAD, f"Python {v.major}.{v.minor}，需要 3.8 以上")
        return False
    say(OK, f"Python {v.major}.{v.minor}.{v.micro}")
    return True


def check_deps(auto=False):
    need = []
    for mod, pkg in (("requests", "requests"), ("tidevice", "tidevice")):
        try:
            __import__(mod)
            say(OK, f"依赖 {pkg} 已装")
        except ImportError:
            say(BAD, f"缺依赖 {pkg}")
            need.append(pkg)
    if need:
        cmd = [sys.executable, "-m", "pip", "install"] + need
        print("\n  执行: " + " ".join(cmd))
        if auto:
            subprocess.call(cmd)
            return check_deps(False)
        return False
    return True


def check_device():
    try:
        r = subprocess.run([sys.executable, "-m", "tidevice", "list"],
                           capture_output=True, text=True, timeout=25)
    except Exception as e:
        say(BAD, f"tidevice 跑不起来: {e}")
        return None

    err = ((r.stderr or "") + (r.stdout or "")).strip()
    if r.returncode != 0 or "Traceback" in err:
        if "No module named" in err:
            say(BAD, "tidevice 未安装，先执行 pip install tidevice")
        elif any(k in err for k in ("usbmux", "_safe_socket", "ConnectionRefused",
                                    "WinError 10061", "No such file", "Connection refused")):
            say(BAD, "连不上手机的 usbmux 通道（Windows 侧的 iPhone 驱动没就绪）")
            print("       1) 装 iTunes（微软商店版即可），确认服务 Apple Mobile Device Service 在运行")
            print("       2) 换一根能传数据的线（很多充电线没有数据线芯）")
            print("       3) 插上后手机要解锁，并点「信任此电脑」")
        else:
            first = [l for l in err.splitlines() if l.strip()][-1:] or ["未知错误"]
            say(BAD, f"tidevice 报错: {first[0][:160]}")
        return None

    out = (r.stdout or "") + (r.stderr or "")
    lines = [l for l in out.splitlines() if l.strip() and "UDID" not in l]
    if not lines:
        say(BAD, "没有检测到 iPhone")
        print("       检查：数据线是否支持数据传输 / 手机是否点了「信任」/ 是否解锁")
        return None
    say(OK, f"检测到设备: {lines[0].strip()[:80]}")
    return lines[0].strip()


def wda_alive(port=PORT, timeout=3):
    try:
        import requests
        j = requests.get(f"http://127.0.0.1:{port}/status", timeout=timeout).json()
        return bool(j.get("value"))
    except Exception:
        return False


def ensure_wda(port=PORT):
    if wda_alive(port):
        say(OK, f"WDA 已在 {port} 端口就绪")
        return True

    say(WARN, "WDA 没响应，尝试起 wdaproxy …")
    kw = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "tidevice", "wdaproxy", "-p", str(port), "-B", BUNDLE],
            **kw)
    except Exception as e:
        say(BAD, f"wdaproxy 起不来: {e}")
        return False

    import atexit
    atexit.register(lambda: proc.poll() is None and proc.terminate())

    for i in range(40):
        time.sleep(1)
        if wda_alive(port):
            say(OK, f"WDA 已就绪（{i + 1}s）")
            return True
        if proc.poll() is not None:
            say(BAD, "wdaproxy 已退出")
            print("       多半是 WDA 没装好或证书过期。检查：")
            print("       1) 手机上有没有 WebDriverAgentRunner 这个 App")
            print("       2) 设置 -> 通用 -> VPN与设备管理 里证书是否还信任")
            print("       3) 7 天到期了？用 Sideloadly 重签一次（不用重新编译）")
            return False
    say(BAD, "40 秒内 WDA 没起来")
    return False


def doctor(auto_install=False):
    print("—— 环境体检 ——")
    ok = check_python()
    ok = check_deps(auto_install) and ok
    if not ok:
        return False
    if not check_device():
        return False
    return ensure_wda()


# ------------------------------------------------------------ 引导校准

PROBE_STAGES = [
    ("搜索结果页", "在抖音里搜「福袋」，停在结果列表，并切到顶部的「直播」tab"),
    ("直播间", "点进一个带福袋的直播间，停在房间画面（不要点开福袋）"),
    ("福袋面板", "点开福袋，停在写有「参与」的面板上"),
]


def guided_probe(port=PORT):
    from douyin_bot import WDA, Cfg, Log

    cfg = Cfg(os.path.join(HERE, "config.json"))
    w = WDA(f"http://127.0.0.1:{port}", cfg.bundleId)
    log = Log.get()
    if not w.alive():
        say(BAD, "WDA 没响应，先跑 python go.py doctor")
        return False
    if not w.new_session():
        say(BAD, "WDA 会话建立失败")
        return False

    outdir = os.path.join(HERE, "probe")
    os.makedirs(outdir, exist_ok=True)

    print("\n—— 引导校准（手机拿在手上，按提示走）——")
    print("每一步：把抖音停在指定界面，然后回车\n")
    for i, (name, tip) in enumerate(PROBE_STAGES, 1):
        print(f"[{i}/{len(PROBE_STAGES)}] {name}")
        print(f"      {tip}")
        try:
            input("      就绪后按回车 …")
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False
        xml = w.source()
        if not xml:
            say(BAD, "抓不到界面树，跳过这一步")
            continue
        fn = os.path.join(outdir, f"{i}_{name}.xml")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(xml)
        shot = os.path.join(outdir, f"{i}_{name}.png")
        w.screenshot(shot)
        say(OK, f"已保存 {os.path.basename(fn)}  ({len(xml)} 字节)")

    try:
        w.req("DELETE", f"/session/{w.sid}")
    except Exception:
        pass

    print("\n—— 生成配置 ——")
    import wizard
    sys.argv = ["wizard.py", "--dir", outdir,
                "--out", os.path.join(HERE, "config.json")]
    wizard.main()
    return True


# ------------------------------------------------------------ 入口

def main():
    args = sys.argv[1:]
    cmd = args[0] if args and not args[0].startswith("-") else "run"

    if cmd == "mock":
        import mock_wda
        mock_wda.main()
        return

    if cmd == "doctor":
        sys.exit(0 if doctor(auto_install=True) else 1)

    if not doctor(auto_install=True):
        print("\n体检没过，先修上面的问题。")
        sys.exit(1)

    if cmd == "probe":
        sys.exit(0 if guided_probe() else 1)

    rest = args[1:] if (args and args[0] == "run") else args

    print("\n—— 启动 ——")
    import douyin_bot
    sys.argv = ["douyin_bot.py"] + rest
    if not any(a == "--url" or a.startswith("--url=") for a in rest):
        sys.argv += ["--url", f"http://127.0.0.1:{PORT}"]
    douyin_bot.main()


if __name__ == "__main__":
    main()
