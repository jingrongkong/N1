#import "DYOCR.h"
#import "DYLog.h"
#import <Vision/Vision.h>

@implementation DYTextItem
- (NSString *)description {
    return [NSString stringWithFormat:@"「%@」%@ c=%.2f", _text, DYRectToString(_normRect), _confidence];
}
@end

@implementation DYOCR

+ (NSArray<DYTextItem *> *)recognize:(UIImage *)image fast:(BOOL)fast {
    if (!image) return @[];
    CGImageRef cg = image.CGImage;
    if (!cg) return @[];

    NSMutableArray<DYTextItem *> *result = [NSMutableArray array];

    VNImageRequestHandler *handler =
        [[VNImageRequestHandler alloc] initWithCGImage:cg options:@{}];

    VNRecognizeTextRequest *req = [[VNRecognizeTextRequest alloc] init];
    req.recognitionLevel = fast ? VNRequestTextRecognitionLevelFast
                                : VNRequestTextRecognitionLevelAccurate;
    req.recognitionLanguages = @[@"zh-Hans", @"en-US"];
    req.usesLanguageCorrection = NO;      // 弹幕/标题不规整，纠错反而误判
    if (@available(iOS 16.0, *)) {
        req.automaticallyDetectsLanguage = NO;
    }

    NSError *err = nil;
    @try {
        [handler performRequests:@[req] error:&err];
    } @catch (NSException *e) {
        DYLOG(@"OCR 异常：%@", e);
        return @[];
    }
    if (err) {
        DYLOG(@"OCR 失败：%@", err.localizedDescription);
        return @[];
    }

    for (VNRecognizedTextObservation *obs in req.results) {
        VNRecognizedText *best = [[obs topCandidates:1] firstObject];
        if (!best || best.string.length == 0) continue;

        CGRect bb = obs.boundingBox;   // 左下原点归一化
        CGRect norm = CGRectMake(bb.origin.x,
                                 1.0 - CGRectGetMaxY(bb),
                                 bb.size.width,
                                 bb.size.height);

        DYTextItem *it = [[DYTextItem alloc] init];
        it.text = [best.string stringByTrimmingCharactersInSet:
                   [NSCharacterSet whitespaceAndNewlineCharacterSet]];
        it.normRect = norm;
        it.confidence = best.confidence;
        if (it.text.length) [result addObject:it];
    }

    [result sortUsingComparator:^NSComparisonResult(DYTextItem *a, DYTextItem *b) {
        return a.confidence > b.confidence ? NSOrderedAscending : NSOrderedDescending;
    }];
    return result;
}

+ (NSString *)flatten:(NSArray<DYTextItem *> *)items {
    NSMutableArray *arr = [NSMutableArray array];
    for (DYTextItem *it in items) [arr addObject:it.text];
    return [arr componentsJoinedByString:@" / "];
}

@end
