#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_ipa.py — 给解密版抖音 IPA 打补丁，供 iOS 26 自签安装使用

做两件事：
  1. 给主 App 的 Info.plist 打开文件共享（UIFileSharingEnabled / LSSupportsOpeningDocumentsInPlace）
     这样 dyfudai.json 和 dyfudai.log 可以直接在 iPhone 的「文件」App 里改和看，不用连电脑。
  2. 可选：把 DYFudai.dylib 塞进 .app 根目录（如果你不想用 Sideloadly 的注入选项）。

用法：
  python patch_ipa.py --ipa douyin_decrypted.ipa --out douyin_patched.ipa
  python patch_ipa.py --ipa douyin_decrypted.ipa --out douyin_patched.ipa --dylib DYFudai.dylib

注意：只接受**已解密**的 IPA。App Store 下载的原包是 FairPlay 加密的，注入后跑不起来。
"""

import argparse
import os
import plistlib
import shutil
import sys
import zipfile

APP_PLIST_SUFFIX = ".app/Info.plist"


def find_app_dir(names):
    for n in names:
        if not n.startswith("Payload/"):
            continue
        parts = n.split("/")
        if len(parts) >= 2 and parts[1].endswith(".app"):
            return "Payload/" + parts[1]
    return None


def is_symlink(info):
    return (info.external_attr >> 16) & 0o170000 == 0o120000


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ipa", required=True, help="已解密的 IPA")
    ap.add_argument("--out", required=True, help="输出 IPA")
    ap.add_argument("--dylib", default=None, help="要一并塞进 .app 的 dylib（可选）")
    args = ap.parse_args()

    if not os.path.isfile(args.ipa):
        sys.exit("找不到输入文件: " + args.ipa)

    zin = zipfile.ZipFile(args.ipa, "r")
    names = zin.namelist()
    app_dir = find_app_dir(names)
    if not app_dir:
        sys.exit("IPA 结构不对：没找到 Payload/*.app")

    main_plist = app_dir + "/Info.plist"
    if main_plist not in names:
        sys.exit("没找到主 App 的 Info.plist: " + main_plist)

    raw = zin.read(main_plist)
    try:
        pl = plistlib.loads(raw)
    except Exception as e:
        sys.exit("Info.plist 解析失败: %s" % e)

    bid = pl.get("CFBundleIdentifier", "?")
    ver = pl.get("CFBundleShortVersionString", "?")
    print("[i] 目标 App: %s  版本 %s" % (bid, ver))

    pl["UIFileSharingEnabled"] = True
    pl["LSSupportsOpeningDocumentsInPlace"] = True
    new_plist = plistlib.dumps(pl, fmt=plistlib.FMT_BINARY)

    dylib_name = None
    if args.dylib:
        if not os.path.isfile(args.dylib):
            sys.exit("找不到 dylib: " + args.dylib)
        dylib_name = os.path.basename(args.dylib)
        print("[i] 将写入 %s/%s" % (app_dir, dylib_name))

    tmp = args.out + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename) if not is_symlink(info) else b""
            if info.filename == main_plist:
                data = new_plist
                print("[+] 已开启文件共享")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.external_attr = info.external_attr
            zi.compress_type = info.compress_type
            zout.writestr(zi, data)

        if dylib_name:
            arc = app_dir + "/" + dylib_name
            zi = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(args.dylib, "rb") as f:
                zout.writestr(zi, f.read())
            print("[+] 已写入 " + arc)

    zin.close()
    if os.path.exists(args.out):
        os.remove(args.out)
    shutil.move(tmp, args.out)
    size = os.path.getsize(args.out) / (1024.0 * 1024.0)
    print("[✓] 输出: %s (%.1f MB)" % (args.out, size))
    print("    下一步: Sideloadly 选择这个 IPA，注入 DYFudai.dylib（若已内嵌则跳过注入），用 Apple ID 签名安装")


if __name__ == "__main__":
    main()
