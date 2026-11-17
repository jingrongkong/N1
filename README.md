# DYFudai — 抖音直播福袋自动参与

自动搜索含福袋/抽奖的直播间，进房识别福袋、点参与，**参与完立刻退出**，继续找下一个房间。

当前交付的是 **免费路线**：不注入、不解密、不越狱，抖音始终是 App Store 官方最新版。
iPhone 15 Pro + iOS 26 可直接用，全流程 0 元。

> 完整零成本步骤：**[docs/free-path.md](docs/free-path.md)**

---

## 它是怎么工作的

```
GitHub Actions(macos-26) 编 WDA  ──►  Sideloadly 用免费 Apple ID 签名
                                            │
Windows: python go.py  ──tidevice(USB)──►  iPhone 上运行的 WebDriverAgent
        │                                        │
        └── 读无障碍树 → 状态机决策 → 发真实点击 ─┘
```

- **识别**：读抖音的无障碍树，直接拿到按钮文案（比 OCR 猜字准）
- **操作**：发系统级真实触摸事件，不是模拟坐标
- **不改抖音**：没有重打包，也就没有签名校验、没有掉签封号风险

状态机：

```
搜索"福袋" → 切直播tab → 挑标题含福袋的卡片 → 进房
    → 找福袋入口 → 点参与 → 看到"已参与" → 立刻退出 → 冷却 → 下一个
```

`roomStaySeconds`（默认 45s）是单房间硬上限，到点无条件走——这就是"参与完不停留"。

---

## 文件

| 文件 | 作用 |
|---|---|
| `windows/go.py` | **入口**：体检 → 起 WDA 代理 → 开跑 / 引导校准 |
| `windows/run.bat` | 双击即跑（等价 `python go.py`） |
| `windows/douyin_bot.py` | WDA 客户端 + 状态机 + 配置 |
| `windows/wizard.py` | 把 `probe/*.xml` 自动转成 `config.json` 的关键词 |
| `windows/mock_wda.py` | 假 WDA 服务，**不接手机**也能验证整套逻辑 |
| `.github/workflows/build-wda.yml` | 免费编 WDA（macos-26 runner，10 分钟出 ipa） |
| `docs/free-path.md` | 免费路线全流程 + 故障表 + 7 天续签方案 |
| `docs/windows-wda.md` | WDA 细节、云 Mac 价格对比、排错 |
| `Sources/`、`tools/`、`docs/ios26.md` | 另一条路线：自签注入（需解密 IPA），备查 |

---

## 快速开始

```bash
# 1. 编 WDA：把仓库推到 GitHub → Actions → build-wda → Run workflow
#    下 Artifact 得到 WebDriverAgentRunner.ipa

# 2. 用 Sideloadly 拿免费 Apple ID 签它装上（bundle id 必须
#    com.facebook.WebDriverAgentRunner.xctrunner）

# 3. 装依赖
cd windows
pip install requests tidevice

# 4. 体检（Python / 依赖 / 手机连接 / WDA 是否就绪）
python go.py doctor

# 5. 校准：按提示在三个界面各按一次回车
python go.py probe

# 6. 开跑
python go.py --duration 600     # 先短跑 10 分钟观察
python go.py                    # 确认没问题后长跑
```

首次一定先 `doctor` 再 `probe`。抖音每个版本的按钮文案会变，校准就是把真实文案抓下来。

---

## 不用手机也能先验证

`mock_wda.py` 会模拟一个抖音界面（首页→搜索→列表→直播间→福袋面板→已参与→关闭），
改完逻辑先在这里跑：

```bash
python go.py mock                                  # 窗口 A
python douyin_bot.py --url http://127.0.0.1:8101   # 窗口 B
```

已实测：60 秒内进房 6 次、参与成功 6 次，点击坐标与关键词匹配全部命中。

---

## 配置（`windows/config.json`）

首次运行自动生成。常用几项：

| 键 | 说明 |
|---|---|
| `searchKeywords` | 轮换搜索词，列表翻完自动换下一个 |
| `roomTitleKeywords` | 卡片标题里出现这些词才进房 |
| `luckyBagKeywords` | 房间内福袋入口的文案 |
| `participateKeywords` | 参与按钮文案 |
| `doneKeywords` | 出现这些说明已经参与成功 |
| `roomStaySeconds` | 单房间硬上限（秒），到点无条件退出 |
| `maxRoomsPerHour` | 每小时进房上限，**建议 40–60** |
| `jitterMin/Max` | 动作后随机延时，别设固定值 |
| `bagHotspotX/Y` | 福袋入口无文字时的归一化热区，`0` 为不启用 |
| `autoFollow` / `autoJoinFansClub` / `autoComment` | 默认全关，开了风控概率明显上升 |

---

## 这套方案的边界

- **必须插着 USB**（WDA 走数据线通信）。手机不能揣兜里自己跑。
- **免费签名 7 天到期**，Sideloadly 重签一次即可，不用重编；或用 AltStore 自动续签。
- **纯图标福袋入口**：部分版本的无障碍树里没有文字，只能靠 `bagHotspotX/Y` 热区 + 二次确认兜底。
- **风控看行为不看工具**：高频进出直播间本身就是异常特征。限速、随机化、只点参与不关注加团，
  是唯一能拉长账号寿命的做法。
- `windows/` 下的代码做过离线验证（模拟器全链路 + 语法 + 配置生成）；
  **真机未验证**——抖音真实界面需要你按 `go.py probe` 校准一次。

---

## 另一条路线（备查）

`Sources/` 是进程内注入版（Objectiv-C dylib，Vision OCR 驱动），需要**解密版抖音 IPA**。
iOS 26 上巨魔（TrollStore/TrollFools）已经不可用，只能自签注入，
且重签可能触发抖音的签名校验。原因与三条替代路线对比见 [docs/ios26.md](docs/ios26.md)。
除非你特别需要"手机脱离电脑独立跑"，否则不建议走这条。
