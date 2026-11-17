#import "DYScreen.h"
#import "DYConfig.h"
#import "DYLog.h"
#import <dlfcn.h>
#import <mach/mach_time.h>
#import <objc/runtime.h>
#import <unistd.h>

#pragma mark - 私有 HID 事件注入（坐标点击）

// IOKit 私有函数，用 dlsym 动态取，避免编译期依赖 SDK 私有头。
typedef void *DYHIDEventRef;
typedef void *DYHIDClientRef;

static DYHIDClientRef (*pClientCreate)(CFAllocatorRef);
static void          (*pClientDispatch)(DYHIDClientRef, DYHIDEventRef);
static DYHIDEventRef (*pCreateDigitizerEvent)(CFAllocatorRef, uint64_t, uint32_t, uint32_t,
                                              uint32_t, uint32_t, uint32_t,
                                              double, double, double, double, double,
                                              Boolean, Boolean, uint32_t);
static DYHIDEventRef (*pCreateFingerEvent)(CFAllocatorRef, uint64_t, uint32_t, uint32_t,
                                           uint32_t, uint32_t,
                                           double, double, double, double,
                                           Boolean, Boolean, uint32_t);
static void          (*pAppendEvent)(DYHIDEventRef, DYHIDEventRef, uint32_t);
static void          (*pSetInteger)(DYHIDEventRef, uint32_t, int64_t);

// kIOHIDEventTypeDigitizer = 11；IOHIDEventFieldBase(t) = (t << 16)
static const uint32_t kDYFieldDigitizerBase = (11u << 16);
static const uint32_t kDYFieldIsDisplayIntegrated = kDYFieldDigitizerBase | 21;

static BOOL gHIDReady = NO;

static void DYHIDSetup(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        void *h = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_LAZY);
        if (!h) h = RTLD_DEFAULT;

        pClientCreate         = dlsym(h, "IOHIDEventSystemClientCreate");
        pClientDispatch       = dlsym(h, "IOHIDEventSystemClientDispatchEvent");
        pCreateDigitizerEvent = dlsym(h, "IOHIDEventCreateDigitizerEvent");
        pCreateFingerEvent    = dlsym(h, "IOHIDEventCreateDigitizerFingerEvent");
        pAppendEvent          = dlsym(h, "IOHIDEventAppendEvent");
        pSetInteger           = dlsym(h, "IOHIDEventSetIntegerValue");

        gHIDReady = (pClientCreate && pClientDispatch && pCreateDigitizerEvent &&
                     pCreateFingerEvent && pAppendEvent);
        DYLOG(@"HID 注入初始化：%@", gHIDReady ? @"就绪" : @"不可用（请改用 view 模式）");
    });
}

static DYHIDClientRef gHIDClient = NULL;

static BOOL DYHIDTap(double x, double y) {
    DYHIDSetup();
    if (!gHIDReady) return NO;

    @try {
        if (!gHIDClient) {
            gHIDClient = pClientCreate(kCFAllocatorDefault);
        }
        if (!gHIDClient) return NO;

        uint64_t ts = mach_absolute_time();

        // hand 容器事件：type=3 表示整只手
        DYHIDEventRef hand = pCreateDigitizerEvent(kCFAllocatorDefault, ts,
                                                   3 /*hand*/, 0, 1,
                                                   3 /*touch|range*/, 0,
                                                   0, 0, 0, 0, 0,
                                                   true, true, 0);
        if (!hand) return NO;

        // 按下
        DYHIDEventRef down = pCreateFingerEvent(kCFAllocatorDefault, ts,
                                                2 /*index*/, 2 /*identity*/,
                                                3 /*touch|range*/, 0,
                                                x, y, 0, 0,
                                                true, true, 0);
        if (!down) return NO;
        if (pSetInteger) pSetInteger(down, kDYFieldIsDisplayIntegrated, 1);
        pAppendEvent(hand, down, 0);
        pClientDispatch(gHIDClient, hand);

        usleep(40 * 1000);

        // 抬起
        uint64_t ts2 = mach_absolute_time();
        DYHIDEventRef hand2 = pCreateDigitizerEvent(kCFAllocatorDefault, ts2,
                                                    3, 0, 1, 3, 0,
                                                    0, 0, 0, 0, 0,
                                                    true, true, 0);
        DYHIDEventRef up = pCreateFingerEvent(kCFAllocatorDefault, ts2,
                                              2, 2,
                                              2 /*range*/, 0,
                                              x, y, 0, 0,
                                              false, false, 0);
        if (hand2 && up) {
            if (pSetInteger) pSetInteger(up, kDYFieldIsDisplayIntegrated, 1);
            pAppendEvent(hand2, up, 0);
            pClientDispatch(gHIDClient, hand2);
        }
        return YES;
    } @catch (NSException *e) {
        DYLOG(@"HID 点击异常：%@", e);
        return NO;
    }
}

#pragma mark -

@implementation DYScreen

+ (UIWindow *)keyWindow {
    UIWindow *fallback = nil;
    for (UIScene *scene in [UIApplication sharedApplication].connectedScenes) {
        if (![scene isKindOfClass:[UIWindowScene class]]) continue;
        for (UIWindow *w in ((UIWindowScene *)scene).windows) {
            if (w.isKeyWindow) return w;
            if (!fallback && !w.hidden) fallback = w;
        }
    }
    return fallback ?: [UIApplication sharedApplication].keyWindow;
}

/// 采样判断截图是不是一片黑（iOS 26 上 drawViewHierarchy 对部分新渲染层会返回黑图）
+ (BOOL)imageIsBlank:(UIImage *)img {
    CGImageRef cg = img.CGImage;
    if (!cg) return YES;

    const size_t w = 16, h = 16;
    unsigned char buf[w * h * 4];
    CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(buf, w, h, 8, w * 4, cs,
                                             kCGImageAlphaPremultipliedLast);
    CGColorSpaceRelease(cs);
    if (!ctx) return NO;
    CGContextDrawImage(ctx, CGRectMake(0, 0, w, h), cg);
    CGContextRelease(ctx);

    int lit = 0;
    for (size_t i = 0; i < w * h; i++) {
        int r = buf[i * 4], g = buf[i * 4 + 1], b = buf[i * 4 + 2];
        if (r + g + b > 24) lit++;
    }
    return lit < (int)(w * h) * 0.05;   // 95% 以上纯黑 → 视为没抓到
}

+ (UIImage *)renderWindow:(UIWindow *)w hierarchy:(BOOL)hierarchy {
    CGRect bounds = w.bounds;
    UIGraphicsImageRendererFormat *fmt = [UIGraphicsImageRendererFormat defaultFormat];
    fmt.scale = 2.0;   // 1x 时小字号（11pt）识别率明显下降，2x 是准确率/耗时的平衡点
    fmt.opaque = NO;
    UIGraphicsImageRenderer *r = [[UIGraphicsImageRenderer alloc] initWithBounds:bounds format:fmt];
    return [r imageWithActions:^(UIGraphicsImageRendererContext *ctx) {
        if (hierarchy) {
            @try {
                if ([w drawViewHierarchyInRect:bounds afterScreenUpdates:NO]) return;
            } @catch (NSException *e) {
                // 落到下面用 layer 渲染
            }
        }
        @try {
            [w.layer renderInContext:ctx.CGContext];
        } @catch (NSException *e) {
            DYLOG(@"layer 渲染失败：%@", e);
        }
    }];
}

+ (UIImage *)snapshot {
    UIWindow *w = [self keyWindow];
    if (!w) return nil;
    if (w.bounds.size.width < 1 || w.bounds.size.height < 1) return nil;

    UIImage *img = [self renderWindow:w hierarchy:YES];
    if ([self imageIsBlank:img]) {
        static BOOL warned = NO;
        if (!warned) {
            warned = YES;
            DYLOG(@"截图全黑，切换到 layer 渲染（iOS 26 上 drawViewHierarchy 会失效）");
        }
        img = [self renderWindow:w hierarchy:NO];
    }
    return img;
}

+ (BOOL)tapNormalizedPoint:(CGPoint)p {
    UIWindow *w = [self keyWindow];
    if (!w) return NO;
    CGPoint abs = CGPointMake(p.x * w.bounds.size.width, p.y * w.bounds.size.height);

    DYConfig *cfg = [DYConfig shared];
    BOOL preferView = [cfg.tapMode isEqualToString:@"view"];

    if (preferView) {
        UIView *hit = [w hitTest:abs withEvent:nil];
        if (hit) {
            // 命中的是容器就往上找可点的父控件
            UIView *cur = hit;
            while (cur && cur != w) {
                if ([cur isKindOfClass:[UIControl class]]) {
                    if ([self tapView:cur]) return YES;
                    break;
                }
                cur = cur.superview;
            }
            // 没有 UIControl（手势驱动的 UI），退化到坐标注入
            if (DYHIDTap(abs.x, abs.y)) return YES;
            // 最后尝试直接命中
            return [self tapView:hit];
        }
        return NO;
    }

    // hid 模式
    double x = abs.x, y = abs.y;
    if (cfg.hidUsePixels) {
        CGFloat s = w.screen.scale > 0 ? w.screen.scale : 3.0;
        x *= s; y *= s;
    }
    if (DYHIDTap(x, y)) return YES;
    UIView *hit = [w hitTest:abs withEvent:nil];
    return hit ? [self tapView:hit] : NO;
}

+ (BOOL)tapView:(UIView *)v {
    if (!v) return NO;

    __block BOOL ok = NO;
    void (^work)(void) = ^{
        @try {
            if ([v isKindOfClass:[UIControl class]]) {
                UIControl *c = (UIControl *)v;
                [c sendActionsForControlEvents:UIControlEventTouchUpInside];
                ok = YES;
                return;
            }
            // 有手势识别器的控件只能靠真实触摸，交给 HID
            if (v.gestureRecognizers.count > 0) {
                UIWindow *w = v.window;
                if (w) {
                    CGPoint c = [v convertPoint:DYRectCenter(v.bounds) toView:w];
                    ok = DYHIDTap(c.x, c.y);
                }
                return;
            }
        } @catch (NSException *e) {
            DYLOG(@"tapView 异常：%@", e);
        }
    };

    if ([NSThread isMainThread]) work();
    else dispatch_sync(dispatch_get_main_queue(), work);
    return ok;
}

+ (void)collectViews:(UIView *)root
               depth:(NSInteger)depth
                 out:(NSMutableArray *)out
               limit:(NSInteger)limit {
    if (!root || out.count >= limit) return;
    [out addObject:root];
    for (UIView *sub in root.subviews) {
        if (out.count >= limit) return;
        [self collectViews:sub depth:depth + 1 out:out limit:limit];
    }
}

+ (NSString *)textOfView:(UIView *)v {
    NSMutableArray *parts = [NSMutableArray array];
    if (v.accessibilityLabel.length) [parts addObject:v.accessibilityLabel];
    if (v.accessibilityIdentifier.length) [parts addObject:v.accessibilityIdentifier];
    if ([v isKindOfClass:[UILabel class]]) {
        UILabel *l = (UILabel *)v;
        if (l.text.length) [parts addObject:l.text];
    } else if ([v isKindOfClass:[UIButton class]]) {
        UIButton *b = (UIButton *)v;
        if (b.titleLabel.text.length) [parts addObject:b.titleLabel.text];
    } else if ([v isKindOfClass:[UITextField class]]) {
        UITextField *t = (UITextField *)v;
        if (t.text.length) [parts addObject:t.text];
        if (t.placeholder.length) [parts addObject:t.placeholder];
    } else if ([v isKindOfClass:[UITextView class]]) {
        UITextView *t = (UITextView *)v;
        if (t.text.length) [parts addObject:t.text];
    }
    return [parts componentsJoinedByString:@" | "];
}

+ (UIView *)findViewWithTexts:(NSArray<NSString *> *)texts {
    UIWindow *w = [self keyWindow];
    if (!w || texts.count == 0) return nil;
    NSMutableArray *all = [NSMutableArray array];
    [self collectViews:w depth:0 out:all limit:4000];

    for (NSString *kw in texts) {
        for (UIView *v in all) {
            NSString *t = [self textOfView:v];
            if (t.length && [t containsString:kw] && v.window && !v.hidden && v.alpha > 0.01) {
                return v;
            }
        }
    }
    return nil;
}

+ (NSString *)dumpViewTreeWithLimit:(NSInteger)limit {
    UIWindow *w = [self keyWindow];
    if (!w) return @"<no window>";
    NSMutableArray *all = [NSMutableArray array];
    [self collectViews:w depth:0 out:all limit:limit];
    NSMutableString *s = [NSMutableString string];
    for (UIView *v in all) {
        NSString *t = [self textOfView:v];
        NSString *a = v.accessibilityLabel;
        [s appendFormat:@"%@%@ frame=%@%@\n",
            NSStringFromClass(v.class),
            a.length ? [NSString stringWithFormat:@" a11y=%@", a] : @"",
            NSStringFromCGRect(v.frame),
            t.length ? [NSString stringWithFormat:@" text=%@", t] : @""];
    }
    return s;
}

+ (UIView *)firstResponder {
    UIWindow *w = [self keyWindow];
    if (!w) return nil;
    NSMutableArray *all = [NSMutableArray array];
    [self collectViews:w depth:0 out:all limit:4000];
    for (UIView *v in all) {
        if (v.isFirstResponder) return v;
    }
    return nil;
}

+ (BOOL)typeText:(NSString *)text {
    __block BOOL ok = NO;
    void (^work)(void) = ^{
        UIView *fr = [self firstResponder];
        if (!fr) { DYLOG(@"没有找到输入框"); return; }
        @try {
            if ([fr isKindOfClass:[UITextField class]]) {
                UITextField *t = (UITextField *)fr;
                t.text = text;
                [t sendActionsForControlEvents:UIControlEventEditingChanged];
                ok = YES;
            } else if ([fr isKindOfClass:[UITextView class]]) {
                UITextView *t = (UITextView *)fr;
                t.text = text;
                [[NSNotificationCenter defaultCenter] postNotificationName:UITextViewTextDidChangeNotification object:t];
                ok = YES;
            } else if ([fr respondsToSelector:@selector(insertText:)]) {
                [fr performSelector:@selector(insertText:) withObject:text];
                ok = YES;
            }
            DYLOG(@"写入文字「%@」到 %@ -> %@", text, NSStringFromClass(fr.class), ok ? @"成功" : @"失败");
        } @catch (NSException *e) {
            DYLOG(@"typeText 异常：%@", e);
        }
    };
    if ([NSThread isMainThread]) work();
    else dispatch_sync(dispatch_get_main_queue(), work);
    return ok;
}

@end
