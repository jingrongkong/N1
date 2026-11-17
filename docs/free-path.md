# 免费路线：从零到跑起来（总花费 0 元）

这条路不注入、不解密、不越狱，抖音始终是 App Store 官方最新版。
整个链路只用免费额度：**GitHub Actions 编 WDA + 免费 Apple ID 签名 + Windows 跑脚本**。

```
GitHub Actions(macos-26)          Windows                       iPhone 15 Pro
   编 WDA → 未签名 ipa   ──►  Sideloadly 用 Apple ID 签名  ──►  装 WDA + 官方抖音
                                                                     │
   python go.py  ◄──── tidevice 端口转发(USB) ◄──────────────────────┘
        │
        └─ 读无障碍树 → 决策 → 发真实点击
```

---

## 0. 准备清单

| 项目 | 说明 | 花钱 |
|---|---|---|
| GitHub 账号 | 存代码 + 用免费 macOS runner | 0 |
| Windows 10/11 电脑 | 跑脚本 | 0 |
| iTunes | **必须**。提供 Windows 侧的 iPhone USB 驱动（Apple Mobile Device Service） | 0 |
| Sideloadly | 用 Apple ID 给 ipa 签名（有 Windows 版） | 0 |
| Python 3.9+ | 装 `requests` + `tidevice` | 0 |
| 一根数据线 | 要能传数据，纯充电线不行 | 0 |

iPhone 上要开的开关：`设置 → 隐私与安全性 → 开发者模式 → 打开`（会重启一次）。

---

## 1. 编 WDA（约 10 分钟，全自动）

WDA 是 Apple 自己的 UI 测试框架，必须用 **Xcode 26** 编（iOS 26 的 XCTest 才挂得上）。
你没有 Mac 也不要紧——GitHub 的 `macos-26` 运行器预装了 Xcode 26。

1. 把 `douyin-fudai` 整个目录推到一个 GitHub 仓库（公开/私有都行）
2. 仓库页面 → **Actions** → 左侧选 **build-wda** → 右上 **Run workflow**
3. 等 8～12 分钟，点进这次运行，页面底部 **Artifacts** 下载 `WebDriverAgent-unsigned-ipa`
4. 解压得到 `WebDriverAgentRunner.ipa`

> 免费额度足够：公开仓库无限；私有仓库每月 2000 分钟，macOS 按 10 倍计 ≈ 200 分钟，
> 而这个任务只要 10 分钟左右。**编一次永久用**，以后重签不用重编。

---

## 2. 签名安装（免费 Apple ID，7 天有效）

1. 打开 Sideloadly，iPhone 插上电脑
2. 把 `WebDriverAgentRunner.ipa` 拖进 Sideloadly
3. Apple ID 填你自己的（会用来生成免费开发证书，密码只在本机用）
4. 确认 bundle id 是 **`com.facebook.WebDriverAgentRunner.xctrunner`**（必须有 `.xctrunner` 后缀）
5. 点 Start，输入 Apple ID 密码；如果弹二次验证，用手机上的 6 位码
6. 装完去手机 `设置 → 通用 → VPN与设备管理`，信任那个开发者证书

装好后手机桌面上会多一个 **WebDriverAgent** 图标，**不要手动点开它**，由电脑端拉起。

---

## 3. 装依赖 + 体检

```bash
cd windows
pip install requests tidevice
python go.py doctor
```

体检会依次检查：Python 版本 → 依赖 → 手机连接 → WDA 是否就绪。
全绿才算通。最常见的红是 `连不上手机的 usbmux 通道`，那就是 iTunes 没装或
`Apple Mobile Device Service` 没起来。

---

## 4. 校准（第一次必做，约 2 分钟）

抖音的按钮文案每个版本都可能改，所以要抓一次你手机上的真实文案：

```bash
python go.py probe
```

它会提示你把抖音停到三个界面，各按一次回车：

1. **搜索结果页**：搜「福袋」，切到顶部「直播」tab
2. **直播间**：点进一个带福袋的房间，停在画面（先别点福袋）
3. **福袋面板**：点开福袋，停在有「参与」的面板上

抓完自动调 `wizard.py`，把发现的真实 label 合并进 `config.json`，并顺手识别
「有没有无文字的纯图标按钮」，给出 `bagHotspotX/Y` 热区建议。

> 如果你的版本福袋入口是**纯图标、无障碍树里没有任何文字**，向导会把它算成热区候选，
> 你上机后如果发现点歪，用 `probe/` 里的截图量一下中心点，改 `config.json` 的两个数字即可。

---

## 5. 开跑

```bash
python go.py                      # 体检 + 起代理 + 开跑，一直跑
python go.py --duration 600       # 只跑 10 分钟（先短跑观察）
```

或直接双击 `run.bat`。

日志同时打到控制台和 `windows/bot.log`。正常输出长这样：

```
进入直播间 #1: 福袋专场 新人福利 | 主播小王
发现福袋入口: 福袋 3分12秒
点击 参与按钮「立即参与」(195,645) ✓
✅ 参与成功（累计 1）
点击 关闭「关闭」(40,75) ✓
进入直播间 #2: ...
```

`roomStaySeconds`（默认 45 秒）是单房间硬上限，到点无条件退出——这就是"参与完不停留"。

---

## 6. 七天到期怎么办

免费 Apple ID 签的证书 **7 天过期**，过期后 WDA 拉不起来，表现是
`wdaproxy 已退出`。两个办法：

**A. 手动重签（最稳，1 分钟）**

Sideloadly 再拖一次同一个 `WebDriverAgentRunner.ipa`，Start。**不用重新编译**，ipa 一直留着。

**B. AltStore / SideStore 自动续签（省事）**

电脑装 AltServer 并保持开机，手机同 Wi-Fi，用 AltStore 装 WDA 而不是 Sideloadly。
它会在后台每 7 天自动刷新一次签名，相当于永久有效。
代价：电脑得常开、同网段，且 AltStore 偶尔会因为 iOS 版本抽风，稳定性不如手动。

> 别删那个 ipa。重签只需要它，不需要再碰 GitHub Actions。

---

## 7. 常见故障

| 现象 | 原因 / 处理 |
|---|---|
| `连不上手机的 usbmux 通道` | iTunes 没装 / Apple Mobile Device Service 没启动 / 线不支持传数据 / 没点「信任」 |
| `wdaproxy 已退出` | WDA 掉了或证书过期。重签 ipa；再不行重装 WDA |
| `会话建立失败` | bundle id 不对（要 `.xctrunner` 结尾）；或 WDA 与 iOS 版本不匹配，回第 1 步重编 |
| 界面树里几乎没有 label | 抖音部分容器不暴露无障碍信息 → 用 `go.py probe` 看实际结构，靠热区兜底 |
| 进了房间却找不到福袋 | 该版本的入口是纯图标 → 配 `bagHotspotX/Y` |
| 点了没反应 | 被键盘/浮层挡住 → 脚本有兜底手势，也可调大 `enterWait` |
| 脚本停在那儿不动 | 抖音被切后台了 → 脚本每轮会检查并自动拉回前台；锁屏设「永不」 |
| 手机发烫 | 插电跑、亮度调低、别开其他 App；屏幕必须亮着 WDA 才工作 |

---

## 8. 费用明细

| 环节 | 费用 |
|---|---|
| GitHub Actions（macos-26） | 0（公开仓库无限 / 私有仓库免费额度够） |
| Apple ID 免费签名 | 0 |
| Sideloadly / AltStore | 0 |
| Python 依赖 | 0 |
| **合计** | **0 元** |

唯一的"成本"是每 7 天重签一次，或者挂一台常开的电脑做自动续签。
