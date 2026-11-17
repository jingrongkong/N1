#!/usr/bin/env bash
# 在 WSL / Linux 上编译 DYFudai.dylib —— 不需要 Mac
# 用法: bash build-wsl.sh
set -euo pipefail

echo "==> 安装依赖"
sudo apt-get update
sudo apt-get install -y git make clang xz-utils fakeroot dpkg curl python3 || true
# ldid 是签名工具，部分发行版需要单独装
sudo apt-get install -y ldid 2>/dev/null || echo "!! 没装到 ldid，若编译报错请从 https://github.com/ProcursusTeam/ldid 自行编译"

export THEOS="${THEOS:-$HOME/theos}"

echo "==> 拉取 Theos 到 $THEOS"
if [ ! -d "$THEOS" ]; then
  git clone --recursive --depth 1 https://github.com/theos/theos.git "$THEOS"
fi

echo "==> 拉取 iOS SDK"
if [ ! -d "$THEOS/sdks" ] || [ -z "$(ls -A "$THEOS/sdks" 2>/dev/null)" ]; then
  git clone --depth 1 https://github.com/theos/sdks.git "$THEOS/sdks"
fi

cd "$(dirname "$0")"

echo "==> 编译"
make clean 2>/dev/null || true
make -j"$(nproc)"

echo "==> 产物"
find .theos -name '*.dylib' -exec ls -lh {} \;

cat <<'EOF'

下一步（Windows）：
  1. 把 dylib 拷回 Windows
  2. python tools/patch_ipa.py --ipa <解密版抖音.ipa> --out douyin_patched.ipa
  3. Sideloadly 注入 dylib + Apple ID 签名安装
详见 docs/ios26.md
EOF
