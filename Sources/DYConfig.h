#import "DYCommon.h"

/// 运行配置，从 <抖音沙盒>/Documents/dyfudai.json 读取，缺字段用默认值。
/// 改完配置在浮窗上点一下「重载」即可，不用重装。
@interface DYConfig : NSObject

@property (nonatomic, assign) BOOL   enabled;

/// 搜索入口用的关键词，逐个轮换
@property (nonatomic, strong) NSArray<NSString *> *searchKeywords;

/// 直播间标题命中这些词才认为是「有福袋的直播间」（用于二次筛选）
@property (nonatomic, strong) NSArray<NSString *> *roomTitleKeywords;

/// 房间内识别福袋入口的文字
@property (nonatomic, strong) NSArray<NSString *> *luckyBagKeywords;

/// 表示「可以点」的按钮文字，按优先级排序
@property (nonatomic, strong) NSArray<NSString *> *participateKeywords;

/// 表示「已经参加过了」的文字
@property (nonatomic, strong) NSArray<NSString *> *doneKeywords;

/// 表示「有前置条件」的文字（关注/加团/看播/发弹幕）
@property (nonatomic, strong) NSArray<NSString *> *conditionKeywords;

/// 进入房间后等待 UI 渲染的时间
@property (nonatomic, assign) NSTimeInterval enterWait;
/// 单个房间最长驻留（到点强制退出，避免停留）
@property (nonatomic, assign) NSTimeInterval roomStaySeconds;
/// 每轮最多进多少个房间
@property (nonatomic, assign) NSInteger maxRoomsPerRound;
/// 每小时最多进多少个房间（防风控）
@property (nonatomic, assign) NSInteger maxRoomsPerHour;
/// 两次动作之间的随机抖动区间（秒）
@property (nonatomic, assign) CGFloat jitterMin;
@property (nonatomic, assign) CGFloat jitterMax;

/// 点击方式: "hid"（坐标注入，需 entitlement） / "view"（视图命中，无需权限）
@property (nonatomic, copy)   NSString *tapMode;
/// hid 模式下坐标是否要乘屏幕 scale（部分机型需要）
@property (nonatomic, assign) BOOL hidUsePixels;

/// 是否自动关注主播
@property (nonatomic, assign) BOOL autoFollow;
/// 是否自动加入粉丝团
@property (nonatomic, assign) BOOL autoJoinFansClub;
/// 是否自动发送口令评论
@property (nonatomic, assign) BOOL autoComment;
@property (nonatomic, copy)   NSString *commentText;

/// 是否显示悬浮控制窗
@property (nonatomic, assign) BOOL showFloatingPanel;

/// 福袋入口热区（归一化坐标）。福袋图标没有任何文字的版本用这个兜底。
/// 任一为 0 表示不启用。
@property (nonatomic, assign) CGFloat bagHotspotX;
@property (nonatomic, assign) CGFloat bagHotspotY;

+ (instancetype)shared;

/// 从 Documents/dyfudai.json 重新加载
- (void)reload;

/// 配置文件的绝对路径
- (NSString *)configPath;

@end
