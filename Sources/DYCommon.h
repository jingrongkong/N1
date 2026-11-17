//
//  DYCommon.h
//  DYFudai - 抖音直播福袋自动参与（TrollStore 注入版）
//
//  所有坐标一律使用「归一化坐标」：左上角为原点，取值 0~1，
//  这样同一份逻辑可以在任何机型 / 分辨率上复用。
//

#ifndef DYCommon_h
#define DYCommon_h

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <CoreGraphics/CoreGraphics.h>

/// 一条 OCR 结果
@interface DYTextItem : NSObject
@property (nonatomic, copy)   NSString *text;
/// 归一化矩形，左上原点，w/h 为占比
@property (nonatomic, assign) CGRect normRect;
@property (nonatomic, assign) float confidence;
@end

static inline CGPoint DYRectCenter(CGRect r) {
    return CGPointMake(CGRectGetMidX(r), CGRectGetMidY(r));
}

static inline NSString *DYRectToString(CGRect r) {
    return [NSString stringWithFormat:@"{%.3f,%.3f,%.3f,%.3f}",
            r.origin.x, r.origin.y, r.size.width, r.size.height];
}

#define DYLOG(fmt, ...) [DYLog log:(fmt), ##__VA_ARGS__]

#endif /* DYCommon_h */
