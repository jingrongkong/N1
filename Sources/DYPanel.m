#import "DYPanel.h"
#import "DYConfig.h"
#import "DYEngine.h"
#import "DYLog.h"
#import "DYScreen.h"

@interface DYPanel ()
@property (nonatomic, strong) UIView *bar;
@property (nonatomic, strong) UILabel *title;
@property (nonatomic, strong) NSTimer *refresh;
@end

@implementation DYPanel

+ (instancetype)shared {
    static DYPanel *p;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        p = [[DYPanel alloc] init];
    });
    return p;
}

- (UIButton *)buttonWithTitle:(NSString *)t action:(SEL)sel {
    UIButton *b = [UIButton buttonWithType:UIButtonTypeSystem];
    [b setTitle:t forState:UIControlStateNormal];
    [b setTitleColor:[UIColor whiteColor] forState:UIControlStateNormal];
    b.titleLabel.font = [UIFont boldSystemFontOfSize:11];
    b.backgroundColor = [UIColor colorWithWhite:1.0 alpha:0.16];
    b.layer.cornerRadius = 7;
    b.layer.masksToBounds = YES;
    [b addTarget:self action:sel forControlEvents:UIControlEventTouchUpInside];
    return b;
}

- (void)show {
    if (_bar) return;

    static int retry = 0;
    UIWindow *w = [DYScreen keyWindow];   // iOS 26 上 keyWindow 属性不可靠，走 scene 遍历
    if (!w) {
        // App 还在启动动画里，窗口没建好，1 秒后重试（最多 5 次）
        if (retry++ < 5) {
            dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.0 * NSEC_PER_SEC)),
                           dispatch_get_main_queue(), ^{ [self show]; });
        } else {
            DYLOG(@"拿不到窗口，悬浮条放弃加载");
        }
        return;
    }
    retry = 0;

    CGFloat bw = 62, bh = 30, gap = 6;
    CGFloat totalH = bh * 3 + gap * 2;

    UIView *bar = [[UIView alloc] initWithFrame:CGRectMake(6, w.bounds.size.height * 0.42, bw, totalH)];
    bar.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.45];
    bar.layer.cornerRadius = 10;
    bar.layer.masksToBounds = YES;
    bar.autoresizingMask = UIViewAutoresizingNone;

    UIButton *run = [self buttonWithTitle:@"启动" action:@selector(onRun)];
    run.frame = CGRectMake(4, 4, bw - 8, bh);
    [bar addSubview:run];

    UIButton *probe = [self buttonWithTitle:@"探测" action:@selector(onProbe)];
    probe.frame = CGRectMake(4, 4 + bh + gap, bw - 8, bh);
    [bar addSubview:probe];

    UIButton *reload = [self buttonWithTitle:@"重载" action:@selector(onReload)];
    reload.frame = CGRectMake(4, 4 + (bh + gap) * 2, bw - 8, bh);
    [bar addSubview:reload];

    UIPanGestureRecognizer *pan = [[UIPanGestureRecognizer alloc] initWithTarget:self action:@selector(onPan:)];
    [bar addGestureRecognizer:pan];

    [w addSubview:bar];
    _bar = bar;

    // 恢复上次的位置
    CGFloat saved = [[NSUserDefaults standardUserDefaults] doubleForKey:@"dyfudai.panelY"];
    if (saved > 60 && saved < w.bounds.size.height - totalH - 60) {
        CGRect f = bar.frame; f.origin.y = saved; bar.frame = f;
    }

    _refresh = [NSTimer timerWithTimeInterval:0.5 target:self selector:@selector(refreshTitle)
                                   userInfo:nil repeats:YES];
    [[NSRunLoop mainRunLoop] addTimer:_refresh forMode:NSRunLoopCommonModes];

    DYLOG(@"悬浮控制条已加载");
}

- (void)hide {
    [_refresh invalidate]; _refresh = nil;
    [_bar removeFromSuperview]; _bar = nil;
}

- (void)refreshTitle {
    UIButton *run = (UIButton *)_bar.subviews.firstObject;
    if (![DYEngine shared].running) {
        [run setTitle:@"启动" forState:UIControlStateNormal];
        run.backgroundColor = [UIColor colorWithWhite:1 alpha:0.16];
    } else if ([DYEngine shared].reconMode) {
        [run setTitle:@"探测中" forState:UIControlStateNormal];
        run.backgroundColor = [UIColor colorWithRed:0.95 green:0.6 blue:0.1 alpha:0.9];
    } else {
        [run setTitle:@"停止" forState:UIControlStateNormal];
        run.backgroundColor = [UIColor colorWithRed:0.85 green:0.2 blue:0.2 alpha:0.9];
    }
}

- (void)onRun {
    DYEngine *e = [DYEngine shared];
    if (e.reconMode) [e setReconMode:NO];
    [e toggle];
}

- (void)onProbe {
    DYLOG(@"----- 手动探测 -----");
    DYEngine *e = [DYEngine shared];
    if (e.running && !e.reconMode) [e stop];
    [e setReconMode:YES];
    [e dumpOnce];
}

- (void)onReload {
    [[DYConfig shared] reload];
    DYLOG(@"配置重载完成");
}

- (void)onPan:(UIPanGestureRecognizer *)g {
    UIView *v = g.view;
    CGPoint t = [g translationInView:v.superview];
    CGRect f = v.frame;
    f.origin.y += t.y;
    CGFloat maxY = v.superview.bounds.size.height - f.size.height - 40;
    f.origin.y = MAX(40, MIN(maxY, f.origin.y));
    v.frame = f;
    [g setTranslation:CGPointZero inView:v.superview];
    if (g.state == UIGestureRecognizerStateEnded) {
        [[NSUserDefaults standardUserDefaults] setDouble:f.origin.y forKey:@"dyfudai.panelY"];
    }
}

@end
