#import "DYCommon.h"

typedef NS_ENUM(NSInteger, DYState) {
    DYStateBoot = 0,        // 回首页/准备搜索
    DYStateSearchInput,     // 输入关键词并搜索
    DYStateResults,         // 搜索结果页，挑直播间
    DYStateInRoom,          // 已在直播间，找福袋
    DYStateParticipate,     // 点参与 / 处理条件
    DYStateExit,            // 退出直播间
    DYStateCooldown         // 冷却
};

@interface DYEngine : NSObject

+ (instancetype)shared;

@property (nonatomic, readonly) BOOL running;
@property (nonatomic, readonly) DYState state;
@property (nonatomic, readonly) NSString *stateText;

@property (nonatomic, readonly) NSInteger enteredRooms;
@property (nonatomic, readonly) NSInteger successCount;

- (void)start;
- (void)stop;
- (void)toggle;

/// 探测模式：只把每屏 OCR 结果和控件树打进日志，不做任何点击。
/// 首次上机必须先用这个跑一遍，确认关键词和坐标命中。
- (void)setReconMode:(BOOL)on;
@property (nonatomic, readonly) BOOL reconMode;

/// 立刻打一次 OCR + 控件树
- (void)dumpOnce;

@end
