# Windows 方案：WDA 驱动官方抖音（不解密、不注入、不越狱）

## 为什么选这条路

iOS 沙盒不允许第三方 App 读写别的 App 的界面，安卓的「无障碍服务」在 iOS 上没有对应物。
所以"不注入"就等于"程序必须跑在手机外面"。WebDriverAgent 是 **Apple 自己的 UI 测试框架**
（XCTest），它跑在手机上、以测试模式驱动被测算 App：

- 读抖音的**无障碍树**（直接拿到按钮文案，比 OCR 准）
- 发**真实触摸事件**（不是模拟，是系统级注入）
- 抖音是官方原版，一个字节没改，也没有签名校验和掉签问题

代价：需要签一个 WDA（7 天重签），且必须插着 USB。

---

## 一、准备

| 项 | 要求 |
|---|---|
| 手机 | iPhone 15 Pro，iOS 26 |
| 设置 | `设置 → 隐私与安全性 → 开发者模式 → 打开`，重启确认 |
| 电脑 | Windows 10/11 + Python 3.9+ |
| 数据线 | 原装或 MFI，USB 插上后手机点「信任」 |
| 锁屏 | 跑的时候把**自动锁屏设为「永不」** |

```bash
pip install requests tidevice
```

`tidevice` 是阿里开源的 iOS 设备通信库，Windows 上能装能跑，用来做端口转发和装包
（等价于 Mac 上的 `iproxy`）。

---

## 二、最难的一步：拿到 WDA

WDA 必须用 **Xcode 26** 编译（iOS 26 的 XCTest 才能挂上去）。这是整条链路上唯一绕不开
Mac 的环节。四条路，按推荐度排：

### 路线 1（首选，免费）：GitHub Actions 的 macOS 26 runner

GitHub 托管的 `macos-26` 起 **2026 年 2 月就 GA 了**，原生 arm64、预装 Xcode 26，
公开仓库完全免费，私有仓库每月 2000 分钟（macOS 按 10 倍计 ≈ 200 分钟），编一次 WDA 只要
十分钟左右。

仓库里已经带好了 workflow：`.github/workflows/build-wda.yml`

```
1. 把整个 douyin-fudai 目录推到一个 GitHub 仓库（公开或私有都行）
2. 仓库 → Actions → 左侧选 build-wda → Run workflow
3. 等 8-12 分钟，进这次运行，页面底部下载 Artifact：WebDriverAgent-unsigned-ipa
4. 解压得到 WebDriverAgentRunner.ipa（未签名，直接给 Sideloadly 签）
```

这个 workflow 干的事就是下面这条命令，加上打包成 ipa：

```bash
git clone --depth 1 https://github.com/appium/WebDriverAgent.git
cd WebDriverAgent
xcodebuild build-for-testing \
  -project WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination 'generic/platform=iOS' \
  -derivedDataPath ./out \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO
```

**只编一次，之后重签不用再编**，ipa 存本地即可。

### 路线 2：按小时租云 Mac（要交互式 Xcode 才用得上）

| 平台 | 价格（2026-11 查） | 说明 |
|---|---|---|
| **MacinCloud** | PAYG **$1.25/小时**（预付 25 小时 $31.25）；托管机 $25/月起 | 有 **Asia East（新加坡）** 节点，国内延迟最低；M2 + macOS Tahoe 26.3 + Xcode 26.6 预装；新用户有 24 小时试用 |
| **AWS EC2 Mac** | M1 **$0.65/小时**，但**最低 24 小时**（约 $15.6 起） | 贵在起租门槛和配置麻烦，适合已有 AWS 体系的人 |
| **Scaleway** | €50/月（M1 独享） | 欧洲机房，国内延迟高 |
| **MacStadium** | $79/月起 | 企业向，按年起租才划算 |

十分钟就能编完，用 MacinCloud 的 PAYG 也就是一小时的钱。**注意别在共享 Mac 上登录抖音
账号或你自己的 Apple ID 主账号**，签完立刻退出。

### 路线 3：让有 Mac 的朋友帮编一次

上面那条命令复制给他，产物 zip 发回来即可。这是零成本方案。

### 路线 4：现成的预编译 WDA ipa

网络上有流传的包，能省事，但：来源不明的二进制等于把手机交出去；且很多是旧 Xcode 编的，
在 iOS 26 上根本挂不上去。**要用就自己核对版本，别装来源不清的包。**

> 四条都不想走：改用 `docs/ios26.md` 的方式一（自签注入，但要解密 IPA）或换安卓备机。
> 另外，"云电脑跑黑苹果"这条路别碰——违反 Apple 许可，而且现在的 Xcode 只认 Apple Silicon。


---

## 三、签名安装 WDA

1. Sideloadly 拖入 WDA 的 ipa。
2. Apple ID 填自己的，`Advanced Options` 里确认 bundle id 是
   **`com.facebook.WebDriverAgentRunner.xctrunner`**（runner 后缀）。
3. 需要 `get-task-allow` entitlement（默认就有，别手动删）。
4. 装完在手机 `设置 → 通用 → VPN与设备管理` 信任证书。

---

## 四、启动 WDA 并转发端口

```bash
# 确认设备连上了
tidevice list

# 启动 WDA 并把 8100 端口转发到本机（这个窗口要保持开着）
tidevice wdaproxy -p 8100 -B com.facebook.WebDriverAgentRunner.xctrunner
```

另开一个窗口验证：

```bash
curl http://127.0.0.1:8100/status
```

返回一大段 JSON（含 `"ready": true`）就通了。

---

## 五、校准（必须先做）

```bash
cd windows
python go.py probe
```

它会依次提示你把抖音停到三个界面，每步按一次回车：

1. **搜索结果页**：搜「福袋」，切到顶部「直播」tab
2. **直播间**：点进一个带福袋的房间，停在画面（先别点福袋）
3. **福袋面板**：点开福袋，停在有「参与」的面板上

每步会存一份 `probe/N_名字.xml` 和截图，抓完自动调 `wizard.py` 把真实 label 合并进
`config.json`，并识别"无文字的纯图标按钮"给出 `bagHotspotX/Y` 建议。

手动版（知道自己在干什么时用）：

```bash
python douyin_bot.py --probe     # 只 dump 当前界面，不点任何东西
python wizard.py --dry-run       # 只看向导要改成什么，不写盘
```

> **纯图标无 label** 是这条路唯一的硬伤：无障碍树里没有文字就匹配不到。
> 用 `probe/` 里的截图量出福袋图标中心的归一化坐标，填进 `bagHotspotX` / `bagHotspotY`。
> 引擎在该房间无文案命中时只试探点一次，点开后 8 秒内没检测到「参与」就退出，不会反复瞎点。

---

## 六、正式运行

```bash
python go.py                    # 体检 + 起代理 + 跑，一直跑
python go.py --duration 600     # 只跑 10 分钟
python douyin_bot.py            # 只跑脚本（代理自己开）
```

日志同时打到控制台和 `bot.log`。流程与 iOS 注入版一致：

```
搜索关键词 → 直播tab → 挑标题含"福袋"的卡片 → 进房
   → 找福袋入口 → 点参与 → 检测到"已参与" → 立刻退出 → 下一个
```

想看逻辑对不对，但手机不在手边：

```bash
python go.py mock                                   # 假 WDA
python douyin_bot.py --url http://127.0.0.1:8101    # 对着假的跑
```

关键参数（`config.json`）：

- `roomStaySeconds`：单房间硬上限，到点无条件退出（满足"不停留"）
- `maxRoomsPerHour`：每小时进房上限，建议 40–60，别拉满
- `jitterMin/Max`：动作随机延时，别设固定值
- `autoFollow` / `autoJoinFansClub` / `autoComment`：默认全关，开了风控概率明显上升
- `searchKeywords`：轮换关键词，列表翻完了自动换下一个

---

## 七、常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `连不上手机的 usbmux 通道` | Windows 侧 iPhone 驱动没就绪：装 iTunes（微软商店版）、确认 `Apple Mobile Device Service` 在跑、换能传数据的线 |
| 连不上 WDA | `wdaproxy` 窗口没开 / 手机锁屏 / USB 没信任 |
| 会话建立失败 | bundleId 写错；或 WDA 版本比 iOS 26 旧，重编一个 |
| 界面树里几乎没有 label | 抖音部分容器不暴露无障碍信息 → 用 `--probe` 看实际结构，必要时用热区 |
| 点了没反应 | 元素被遮挡（键盘、浮层）→ 先 `tap` 空白处收键盘；或直接改热区坐标 |
| 用 7 天后跑不起来 | WDA 证书过期，Sideloadly 重签一次即可，**不用重新编译** |
| 抖音被切到后台 | 脚本每轮会检查 `activeAppInfo`，自动拉回前台 |
| 手机发烫/耗电 | 长时间跑建议插电、把屏幕亮度调低（WDA 需要屏幕亮着） |

---

## 八、这套方案的风险边界

- 抖音官方包，不涉及重打包，**没有签名校验问题**，也不会因为证书被吊销而封号。
- 但"高频进直播间、机械式点参与"本身就是异常行为特征，风控看的是行为，不是工具。
  限速、随机化、只做点参与不做关注加团，是唯一能拉长账号寿命的做法。
- WDA 只是 UI 自动化，不修改 App、不注入代码、不读内存。
