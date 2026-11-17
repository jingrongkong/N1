#import "DYCommon.h"

/// 屏幕读写层：截图、OCR、点击、查找控件、输入文字。
/// 全部在抖音进程内完成，不需要任何系统权限（HID 坐标注入除外）。
@interface DYScreen : NSObject

/// 主窗口（多 scene 取 keyWindow）
+ (UIWindow *)keyWindow;

/// 进程内截图。视频层可能是黑帧，但 UI 文字层可正常捕获，OCR 足够用。
+ (UIImage *)snapshot;

/// 按当前配置的 tapMode 点击归一化坐标，返回是否成功派发
+ (BOOL)tapNormalizedPoint:(CGPoint)p;

/// 直接命中某个 view 并触发它（优先走 UIControl / 手势）
+ (BOOL)tapView:(UIView *)v;

/// 递归查找带指定 accessibilityLabel / text 的控件
+ (UIView *)findViewWithTexts:(NSArray<NSString *> *)texts;

/// 遍历窗口的所有子视图，输出可读描述（调试用）
+ (NSString *)dumpViewTreeWithLimit:(NSInteger)limit;

+ (UIView *)firstResponder;

/// 往当前输入框写文字（不触发键盘）
+ (BOOL)typeText:(NSString *)text;

@end
