#import "DYCommon.h"

/// Vision OCR 封装。识别的是 UI 文字层，与抖音版本无关，这是本方案能长期可用的根本原因。
@interface DYOCR : NSObject

/// 返回按置信度倒序的识别结果，坐标已转成左上原点归一化坐标
+ (NSArray<DYTextItem *> *)recognize:(UIImage *)image fast:(BOOL)fast;

/// 调试用：把所有识别到的文字拼成一行
+ (NSString *)flatten:(NSArray<DYTextItem *> *)items;

@end
