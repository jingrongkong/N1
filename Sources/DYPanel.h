#import "DYCommon.h"

/// 悬浮控制条：启动/停止、探测模式、重载配置。
/// 贴在屏幕左边缘，纵向拖动可移动，避免压住抖音的关键按钮。
@interface DYPanel : NSObject

+ (instancetype)shared;
- (void)show;
- (void)hide;

@end
