#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
wda_check.py —— WDA 上机一键验证

拿到签名后的 WebDriverAgentRunner.ipa 后，用本脚本一条命令做完：
    安装 ipa -> 启动 WDA -> 轮询 /status -> 打印判定结果

用法：
    python wda_check.py                     # 自动找当前目录的 *.ipa
    python wda_check.py WebDriverAgentRunner.ipa
    python wda_check.py --no-install        # ipa 已装过，只启动 + 验证
    python wda_check.py --port 8100
    python wda_check.py --keep              # 验证完不关 wdaproxy

退出码：
    0 = WDA 已就绪（可以做 UI 自动化）
    1 = 安装失败
    2 = 启动失败 / 超时
    3 = 环境问题（无设备、无 tidevice）
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

try:
    import requests
except ImportError:
    print("缺少 requests：pip install requests")
    sys.exit(3)

DEFAULT_BUNDLE = "com.facebook.WebDriverAgentRunner.xctrunner"
BUNDLE_ID = DEFAULT_BUNDLE   # 运行时会被实际探测到的值覆盖


def say(msg=""):
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", "replace").decode("utf-8", "replace"), flush=True)


def dev_udid():
    """返回已连接设备的 UDID，失败返回 None"""
    try:
        r = subprocess.run([sys.executable, "-m", "tidevice", "list"],
                           capture_output=True, timeout=60)
    except Exception as e:
        say(f"[!] 调用 tidevice 失败: {e}")
        return None
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    lines = [l for l in out.splitlines() if l.strip()]
    data = [l for l in lines if "UDID" not in l and ("USB" in l or "ConnectionType" in l)]
    if not data:
        say("[!] 没检测到设备。检查：数据线 / 手机是否点过「信任」/ Apple Mobile Device Service 是否在跑")
        if out.strip():
            say("    tidevice 原始输出：")
            for l in lines[:6]:
                say("      " + l)
        return None
    return data[0].split()[0]


def list_bundles(udid):
    """列出设备上已安装应用的 bundle id"""
    try:
        r = subprocess.run([sys.executable, "-m", "tidevice", "-u", udid, "applist"],
                           capture_output=True, timeout=120)
    except Exception:
        return []
    out = (r.stdout or b"").decode("utf-8", "replace")
    ids = []
    for line in out.splitlines():
        line = line.strip()
        if not line or " " not in line:
            continue
        bid = line.split()[0]
        if "." in bid and not bid.startswith("["):
            ids.append(bid)
    return ids


def detect_bundle(udid, override=None):
    """
    探测设备上 WDA 的真实 bundle id。

    Sideloadly 用免费 Apple ID 签名时，若默认 App ID 注册失败会给 bundle id 加后缀
    （如 ...xctrunner2），写死默认值会让 wdaproxy 报 "process not found"。
    """
    if override:
        say(f"[*] 使用指定 bundle id: {override}")
        return override

    ids = list_bundles(udid)
    hits = [b for b in ids if "webdriveragent" in b.lower()]
    if len(hits) == 1:
        say(f"[+] 设备上的 WDA bundle id: {hits[0]}")
        return hits[0]
    if len(hits) > 1:
        say(f"[!] 设备上有多个 WDA（{', '.join(hits)}），用第一个")
        return hits[0]

    say(f"[!] 设备上没找到 WebDriverAgent，按默认 id 试: {DEFAULT_BUNDLE}")
    say("    若下面启动失败，说明还没装或用 Sideloadly 装成了别的 id")
    return DEFAULT_BUNDLE


def find_ipa(explicit=None):
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.getcwd(), os.path.dirname(here)):
        hits = sorted(glob.glob(os.path.join(d, "*.ipa")))
        if hits:
            return hits[0]
    return None


def install(ipa, udid):
    say(f"[*] 安装 {os.path.basename(ipa)} ...")
    try:
        r = subprocess.run([sys.executable, "-m", "tidevice", "-u", udid, "install", ipa],
                           capture_output=True, timeout=600)
    except Exception as e:
        say(f"[!] 安装异常: {e}")
        return False
    out = (r.stdout or b"").decode("utf-8", "replace") + (r.stderr or b"").decode("utf-8", "replace")
    if r.returncode != 0:
        say("[!] 安装失败，原始输出：")
        for l in out.strip().splitlines()[-15:]:
            say("    " + l)
        low = out.lower()
        if "applicationverificationfailed" in low or "signature" in low:
            say("    → 签名问题：用 Sideloadly 重新签一次（同一个 ipa 重签即可，不用重编）")
        elif "already" in low:
            say("    → 已安装过，可加 --no-install 跳过安装")
        return False
    say("[+] 安装成功")
    return True


def start_wdaproxy(port, udid, bundle=BUNDLE_ID):
    """后台起 wdaproxy，返回 Popen"""
    cmd = [sys.executable, "-m", "tidevice", "-u", udid, "wdaproxy",
           "-p", str(port), "-B", bundle]
    say(f"[*] 启动 WDA: {' '.join(cmd[3:])}")
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p


def wait_ready(port, timeout=120):
    url = f"http://127.0.0.1:{port}/status"
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                data = r.json()
                if data.get("value", {}).get("ready"):
                    return True, data
                last = "state=" + str(data.get("value", {}).get("state"))
        except Exception as e:
            last = type(e).__name__
        time.sleep(2)
    return False, last


def diagnose(proxy_proc, port, bundle=BUNDLE_ID):
    """超时后给出可操作的诊断"""
    say("")
    say("— 诊断 —")
    out = ""
    if proxy_proc and proxy_proc.poll() is not None:
        try:
            out = (proxy_proc.stdout.read() or b"").decode("utf-8", "replace")
        except Exception:
            pass
        say("wdaproxy 已退出，输出：")
        for l in out.strip().splitlines()[-12:]:
            say("  " + l)
    low = out.lower()
    if "not found" in low or "no such" in low or "unable to launch" in low:
        say("  → WDA 没装到设备上，或 bundle id 不是 " + bundle)
        say("    用 Sideloadly 重新签名安装；装完可以用 --bundle 手动指定实际 id")
        say("    查实际 id：python -m tidevice applist | findstr /i webdriver")
    elif "developer" in low or "not trusted" in low:
        say("  → 开发者模式没开，或证书没被信任")
        say("    设置 → 隐私与安全性 → 开发者模式；设置 → 通用 → VPN与设备管理 → 信任")
    elif "testmanagerd" in low or "quiescence" in low or "crash" in low:
        say("  → 命中 iOS 27 的私有方法缺失（protocolVersion / quiescence）")
        say("    WDA 版本偏旧，改用 appium/WebDriverAgent 最新版重新编译")
    else:
        say("  常见三种原因，按顺序排：")
        say("    1) 开发者模式未开 / 未重启生效")
        say("    2) 设置 → 开发者 → 启用 UI 自动化 没打开（iOS 17+ 必须）")
        say("    3) 签名已过期（免费 Apple ID 7 天），用 Sideloadly 重签")
    say("")
    say(f"  端口 {port} 现在能访问到但 WDA 未就绪时，也可能是设备锁屏了 —— 解锁后再试")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ipa", nargs="?", help="WebDriverAgentRunner.ipa 路径")
    ap.add_argument("--no-install", action="store_true", help="跳过安装，只启动验证")
    ap.add_argument("--port", type=int, default=8100)
    ap.add_argument("--timeout", type=int, default=120, help="等待就绪秒数")
    ap.add_argument("--keep", action="store_true", help="验证成功后保留 wdaproxy 进程")
    ap.add_argument("--bundle", default=None, help="手动指定 WDA 的 bundle id（默认自动探测）")
    args = ap.parse_args()

    say("=" * 52)
    say(" WDA 上机验证")
    say("=" * 52)

    udid = dev_udid()
    if not udid:
        return 3
    say(f"[+] 设备: {udid}")

    bundle = detect_bundle(udid, args.bundle)

    if not args.no_install:
        ipa = find_ipa(args.ipa)
        if not ipa:
            say("[!] 没找到 ipa。把它放到当前目录，或直接把路径作为参数传进来")
            say("    已经装过 WDA 的话，加 --no-install 跳过安装")
            return 3
        say("[*] 注意：未签名的 ipa 无法直接安装，Sideloadly 会同时完成签名+安装")
        if not install(ipa, udid):
            return 1

    proxy = start_wdaproxy(args.port, udid, bundle)
    try:
        say(f"[*] 等待 WDA 就绪（最多 {args.timeout}s）...")
        ok, info = wait_ready(args.port, args.timeout)
        if ok:
            v = info.get("value", {})
            say("")
            say("[+] WDA 已就绪 ✔")
            say(f"    ready      = {v.get('ready')}")
            say(f"    state      = {v.get('state')}")
            say(f"    os.version = {v.get('os', {}).get('version', '-')}")
            dev = v.get("device", {})
            if dev:
                say(f"    device     = {dev.get('name', '-')}")
            say(f"    URL        = http://127.0.0.1:{args.port}")
            say("")
            say("下一步：")
            say(f"  cd ..\\windows && python go.py --url http://127.0.0.1:{args.port}")
            return 0
        say("")
        say(f"[!] {args.timeout}s 内未就绪（最后状态: {info}）")
        diagnose(proxy, args.port, bundle)
        return 2
    finally:
        if not args.keep and proxy.poll() is None:
            proxy.terminate()
            try:
                proxy.wait(timeout=5)
            except Exception:
                proxy.kill()


if __name__ == "__main__":
    sys.exit(main())
