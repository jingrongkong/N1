# iOS 26 上的注入路线（iPhone 15 Pro / A17 Pro）

## 先说结论：巨魔这条链在 iOS 26 上是断的

TrollStore 的原理是 CoreTrust 签名校验漏洞 **CVE-2023-41991**，苹果在 **iOS 17.0.1 就修了**。
所以官方支持范围只有：

```
iOS 14.0 beta2 – 16.6.1 ｜ 16.7 RC (20H18) ｜ 17.0
```

17.0.1 及以上（含 18、26）全部不支持，而且是**修死了**，不是"还没适配"。

由此连带失效的：

| 东西 | 状态 |
|---|---|
| TrollStore 本体 | iOS 26 不可用 |
| **TrollFools（巨魔注入器）** | 依赖 TrollStore，同样不可用 |
| TrollStore Lite | 需要先越狱；A17 Pro + iOS 26 目前没有公开越狱 |
| 降级回 17.0 | 签名窗口早关，无解 |

> 网上那些"iOS 26 巨魔安装包 / 26.1 版本号"的下载，基本是引流或带毒，别下。

所以你要做的不是"换个注入器版本"，而是换一条技术路线。

---

## 路线 A：自签注入（推荐，代码完全不用改）

本质和 TrollStore 一样：把 dylib 塞进 `.app` 再签一次名。区别只是签名从"系统被骗"变成
"Apple 证书真实签名"，代价是有效期 7 天（免费账号）或 1 年（付费开发者账号 $99）。

### 准备

1. **解密版抖音 IPA** —— 硬性前提。App Store 下的包是 FairPlay 加密的，注入后必崩。
   获取途径只能从越狱设备 dump 或现成解密包，这一步没有替代方案。
2. **DYFudai.dylib** —— 用仓库的 GitHub Actions 出包，或 WSL 本地编（见 `build-wsl.sh`）。
3. **Windows：Sideloadly**（免费，支持注入 dylib + Apple ID 签名）。
4. **iPhone：设置 → 隐私与安全性 → 开发者模式 → 打开**（iOS 16 起必须有），重启确认。

### 步骤

```bash
# 1. 给 IPA 打补丁（开文件共享，方便在手机上改配置）
python tools/patch_ipa.py --ipa douyin_decrypted.ipa --out douyin_patched.ipa

# 也可直接把 dylib 内嵌进 .app，跳过 Sideloadly 的注入选项
python tools/patch_ipa.py --ipa douyin_decrypted.ipa --out douyin_patched.ipa --dylib DYFudai.dylib
```

2. 手机先**卸载官方抖音**（同 bundle id 不能共存，账号数据在云端，登录后会回来）。
3. Sideloadly：连手机 → 拖入 `douyin_patched.ipa` → Apple ID 填自己的 →
   `Advanced Options` 里勾选注入 `DYFudai.dylib`（若已内嵌则不用）→ Start。
4. 手机上：设置 → 通用 → VPN与设备管理 → 信任你的开发者证书。
5. 打开抖音，等 2.5 秒，左边缘出现悬浮条 → 点「探测」开始校准（流程见 README）。
6. 7 天到期后 App 打不开，用 Sideloadly 重新签名一次即可；或用 AltStore 走局域网自动续签。

### 这条路要接受的三个代价

- **抖音可能校验签名**：重签名版有一定概率启动闪退，或直播/钱包等模块提示非官方版本。
  这个只能实测，不同抖音版本表现不一样。真拦住了就走路线 B。
- **7 天/1 年有效期**：免费证书 7 天；付费开发者证书 1 年，且不需要反复连电脑。
- **企业证书（轻松签/全能签之类）**：能免电脑装，但证书随时被苹果吊销，掉了整批 App 一起死。
  只适合试水，不适合长期挂着跑。

---

## 路线 B：电脑端 XCUITest / WebDriverAgent（最稳，但需要一台 Mac）

不碰抖音二进制，用 XCUITest 在外部驱动：读**无障碍树**（比 OCR 准得多，能直接拿到按钮文案），
再发真实触摸事件。不存在签名校验、不存在掉签。

- 需要 Mac + Xcode 编译一次 WebDriverAgent（或用现成的已签名 WDA）。
- 驱动侧用 Appium，或者直接用 `facebook/wda` 的 HTTP 接口写 Python。
- 缺点：必须连着电脑（USB 或同局域网 Wi-Fi）；不适合"手机揣兜里自己跑"。

本工程的状态机可以整体平移过去：`搜索关键词 → 挑含福袋的卡片 → 进房 → 找入口 → 参与 → 退出`
这套决策逻辑不变，只是把「截图 + OCR + 坐标点击」换成「`/source` 拿控件树 + `/element/:id/click`」。

---

## 路线 C：LiveContainer（能装，但不建议跑抖音）

免越狱、可注入 tweak、不限 3 个 App。但容器内的 App 拿不到抖音需要的 entitlements
（推送、部分鉴权、keychain 隔离），直播和登录容易出问题。只当备选。

---

## 三条路线对比

| | A 自签注入 | B WDA 驱动 | C LiveContainer |
|---|---|---|---|
| iOS 26 可用 | ✅ | ✅ | ✅ |
| 需要解密 IPA | 是 | **否** | 是 |
| 签名校验风险 | 有 | 无 | 有 |
| 有效期 | 7 天 / 1 年 | 7 天（WDA 本身） | 7 天（容器） |
| 是否要电脑常连 | 否 | **是** | 否 |
| 识别精度 | OCR | 无障碍树（更高） | OCR |
| 改动量 | 0（现成） | 中（重写驱动层） | 低 |

**建议顺序：先 A。** 代码是现成的，成本就是一个解密 IPA + 一次签名。
A 若被签名校验挡住，再上 B。

---

## 关于抖音版本

这套方案基于 OCR，**不挑抖音版本**——只要直播间的文案没大改就能跑。
但每次抖音大版本更新，建议用「探测」重新过一遍 `luckyBagKeywords` / `participateKeywords`，
因为按钮文案和位置可能微调（尤其是 iOS 26 的新视觉样式下）。

## iOS 26 已做的适配

- 窗口获取改为遍历 `connectedScenes`（`keyWindow` 在 26 上已不可靠）
- 新增截图黑帧检测：`drawViewHierarchyInRect` 在新渲染层可能返回纯黑，自动 fallback 到
  `layer renderInContext`
- 坐标全程归一化，不受刘海/灵动岛/新分辨率影响
- 无 substrate 依赖，自签注入时不需要额外装 ElleKit
