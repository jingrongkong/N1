#import "DYEngine.h"
#import "DYConfig.h"
#import "DYLog.h"
#import "DYOCR.h"
#import "DYScreen.h"
#import <QuartzCore/QuartzCore.h>

@interface DYEngine ()
@property (nonatomic, assign) BOOL running;
@property (nonatomic, assign) DYState state;
@property (nonatomic, assign) BOOL reconMode;
@property (nonatomic, assign) NSInteger enteredRooms;
@property (nonatomic, assign) NSInteger successCount;
@end

@implementation DYEngine {
    NSTimer *_timer;
    dispatch_queue_t _ocrQueue;
    BOOL _busy;

    NSTimeInterval _stateSince;
    NSTimeInterval _delayUntil;
    NSTimeInterval _roomEnterTime;

    NSInteger _keywordIndex;
    NSInteger _roomsThisRound;
    NSInteger _tappedLiveTab;
    BOOL _hotspotTried;
    NSString *_pendingTitle;
    NSMutableSet<NSString *> *_triedTitles;
    NSMutableArray<NSNumber *> *_entryTimes;

    NSString *_lastQuickText;
}

+ (instancetype)shared {
    static DYEngine *e;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        e = [[DYEngine alloc] init];
    });
    return e;
}

- (instancetype)init {
    if (self = [super init]) {
        _ocrQueue = dispatch_queue_create("dyfudai.ocr", DISPATCH_QUEUE_SERIAL);
        _triedTitles = [NSMutableSet set];
        _entryTimes = [NSMutableArray array];
        _state = DYStateBoot;
        _stateSince = CACurrentMediaTime();
    }
    return self;
}

#pragma mark - 生命周期

- (void)start {
    if (_running) return;
    _running = YES;
    _state = DYStateBoot;
    _stateSince = CACurrentMediaTime();
    _delayUntil = 0;
    _keywordIndex = 0;
    _roomsThisRound = 0;
    [_triedTitles removeAllObjects];

    _timer = [NSTimer timerWithTimeInterval:0.8 target:self selector:@selector(tick)
                                  userInfo:nil repeats:YES];
    [[NSRunLoop mainRunLoop] addTimer:_timer forMode:NSRunLoopCommonModes];
    DYLOG(@"===== 引擎启动 =====");
}

- (void)stop {
    if (!_running) return;
    _running = NO;
    [_timer invalidate];
    _timer = nil;
    DYLOG(@"===== 引擎停止 进房%ld 成功%ld =====", (long)_enteredRooms, (long)_successCount);
}

- (void)toggle {
    self.running ? [self stop] : [self start];
}

- (NSString *)stateText {
    NSArray *names = @[@"待机", @"搜索入口", @"输入关键词", @"挑直播间",
                       @"房间内识别", @"参与福袋", @"退出房间", @"冷却"];
    NSString *n = (_state >= 0 && _state < (NSInteger)names.count) ? names[_state] : @"?";
    return [NSString stringWithFormat:@"%@ 进%ld/成%ld", n,
            (long)_enteredRooms, (long)_successCount];
}

#pragma mark - 主循环

- (void)tick {
    if (!_running || _busy) return;
    NSTimeInterval now = CACurrentMediaTime();
    if (now < _delayUntil) return;

    // 每小时进房上限
    [_entryTimes addObject:@(now)];
    NSMutableArray *keep = [NSMutableArray array];
    for (NSNumber *t in _entryTimes) {
        if (now - t.doubleValue <= 3600) [keep addObject:t];
    }
    _entryTimes = keep;

    _busy = YES;
    UIImage *shot = [DYScreen snapshot];
    if (!shot) { _busy = NO; return; }

    dispatch_async(_ocrQueue, ^{
        NSArray<DYTextItem *> *items = [DYOCR recognize:shot fast:YES];
        dispatch_async(dispatch_get_main_queue(), ^{
            @try {
                if (self->_running) [self handle:items];
            } @catch (NSException *e) {
                DYLOG(@"主循环异常：%@", e);
            } @finally {
                self->_busy = NO;
            }
        });
    });
}

#pragma mark - 工具

- (void)goState:(DYState)s delay:(NSTimeInterval)d {
    _state = s;
    _stateSince = CACurrentMediaTime();
    _delayUntil = _stateSince + d;
}

- (NSTimeInterval)stateElapsed {
    return CACurrentMediaTime() - _stateSince;
}

- (CGFloat)randomJitter {
    DYConfig *c = [DYConfig shared];
    CGFloat a = MAX(0.1, c.jitterMin), b = MAX(a, c.jitterMax);
    return a + (CGFloat)arc4random_uniform(1000) / 1000.0 * (b - a);
}

/// 按关键词优先级找第一个 OCR 命中项
- (DYTextItem *)itemIn:(NSArray<DYTextItem *> *)items
            keywords:(NSArray<NSString *> *)kws {
    for (NSString *kw in kws) {
        for (DYTextItem *it in items) {
            if (it.text.length && [it.text containsString:kw]) return it;
        }
    }
    return nil;
}

- (DYTextItem *)itemIn:(NSArray<DYTextItem *> *)items
            keywords:(NSArray<NSString *> *)kws
             yMin:(CGFloat)yMin yMax:(CGFloat)yMax {
    for (NSString *kw in kws) {
        for (DYTextItem *it in items) {
            CGFloat midY = CGRectGetMidY(it.normRect);
            if (it.text.length && [it.text containsString:kw] &&
                midY >= yMin && midY <= yMax) return it;
        }
    }
    return nil;
}

- (BOOL)tapItem:(DYTextItem *)it tag:(NSString *)tag {
    if (!it) return NO;
    BOOL ok = [DYScreen tapNormalizedPoint:DYRectCenter(it.normRect)];
    DYLOG(@"点击 %@「%@」%@" , tag ?: @"", it.text, ok ? @"✓" : @"✗");
    return ok;
}

- (void)openURLString:(NSString *)s {
    NSURL *u = [NSURL URLWithString:s];
    if (!u) return;
    dispatch_async(dispatch_get_main_queue(), ^{
        [[UIApplication sharedApplication] openURL:u
                                           options:@{}
                                 completionHandler:^(BOOL ok) {
            DYLOG(@"deeplink %@ -> %@", s, ok ? @"成功" : @"失败");
        }];
    });
}

- (NSString *)currentKeyword {
    NSArray *kws = [DYConfig shared].searchKeywords;
    if (kws.count == 0) return @"福袋";
    if (_keywordIndex < 0) _keywordIndex = 0;
    return kws[_keywordIndex % kws.count];
}

- (void)nextKeyword {
    _keywordIndex++;
    _roomsThisRound = 0;
    [_triedTitles removeAllObjects];
    _tappedLiveTab = 0;
}

#pragma mark - 状态处理

- (void)handle:(NSArray<DYTextItem *> *)items {
    if (_reconMode) {
        [self reconWithItems:items];
        return;
    }

    switch (_state) {
        case DYStateBoot:        [self doBoot:items]; break;
        case DYStateSearchInput: [self doSearchInput:items]; break;
        case DYStateResults:     [self doResults:items]; break;
        case DYStateInRoom:
        case DYStateParticipate: {
            // 硬性驻留上限：不管有没有参与成功，到点必须走
            CGFloat limit = [DYConfig shared].roomStaySeconds;
            if (limit > 0 && CACurrentMediaTime() - _roomEnterTime > limit) {
                DYLOG(@"房间驻留超过 %.0fs，强制退出", limit);
                [self goState:DYStateExit delay:0];
                break;
            }
            if (_state == DYStateInRoom) [self doInRoom:items];
            else [self doParticipate:items];
            break;
        }
        case DYStateExit:        [self doExit:items]; break;
        case DYStateCooldown:
            if ([self stateElapsed] > 3.0) [self goState:DYStateResults delay:0];
            break;
    }
}

// —— 1. 打开搜索 ——
- (void)doBoot:(NSArray *)items {
    NSString *kw = [self currentKeyword];
    NSString *enc = [kw stringByAddingPercentEncodingWithAllowedCharacters:
                     [NSCharacterSet URLQueryAllowedCharacterSet]];
    DYLOG(@"打开搜索：%@", kw);
    [self openURLString:[NSString stringWithFormat:@"snssdk1128://search?keyword=%@", enc]];
    [self goState:DYStateSearchInput delay:2.2];

    // deeplink 被拦时退回 UI：点搜索图标
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.6 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        if (!self->_running || self->_state != DYStateSearchInput) return;
        UIView *v = [DYScreen findViewWithTexts:@[@"搜索", @"search", @"Search"]];
        if (v) {
            [DYScreen tapView:v];
            DYLOG(@"deeplink 未生效，改用点击搜索入口");
        }
    });
}

// —— 2. 输入关键词 ——
- (void)doSearchInput:(NSArray *)items {
    DYConfig *cfg = [DYConfig shared];
    NSString *kw = [self currentKeyword];

    // 已经在搜索结果页（deeplink 直接带词）
    DYTextItem *hit = [self itemIn:items keywords:@[kw] yMin:0.12 yMax:0.95];
    if (hit) {
        DYLOG(@"已进入搜索结果页");
        [self goState:DYStateResults delay:0.6];
        return;
    }

    if ([self stateElapsed] < 1.2) return;

    // 点开搜索框
    UIView *field = [DYScreen findViewWithTexts:@[@"搜索", @"猜你想搜", @"大家都在搜"]];
    if (field) {
        [DYScreen tapView:field];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.6 * NSEC_PER_SEC)),
                       dispatch_get_main_queue(), ^{
            [DYScreen typeText:kw];
        });
    } else {
        [DYScreen typeText:kw];
    }

    // 点「搜索」按钮
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(1.2 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        DYTextItem *btn = nil;
        // 搜索按钮在屏幕上部
        for (DYTextItem *it in items) {
            if ([it.text isEqualToString:@"搜索"] && CGRectGetMidY(it.normRect) < 0.2) { btn = it; break; }
        }
        if (btn) [self tapItem:btn tag:@"搜索按钮"];
        else {
            // 兜底：回车
            UIView *fr = [DYScreen firstResponder];
            if (fr) [fr resignFirstResponder];
        }
    });

    [self goState:DYStateResults delay:2.4];
    if (cfg.maxRoomsPerRound <= 0) DYLOG(@"提示：maxRoomsPerRound 配置异常");
}

// —— 3. 挑直播间 ——
- (void)doResults:(NSArray *)items {
    DYConfig *cfg = [DYConfig shared];

    if (_roomsThisRound >= cfg.maxRoomsPerRound) {
        DYLOG(@"本轮达到上限 %ld，切换关键词", (long)cfg.maxRoomsPerRound);
        [self nextKeyword];
        [self goState:DYStateBoot delay:self.randomJitter];
        return;
    }

    // 先切到「直播」tab（只在顶部区域找，避免误点标题里的“直播”）
    if (_tappedLiveTab < 1) {
        DYTextItem *tab = [self itemIn:items keywords:@[@"直播"] yMin:0.05 yMax:0.30];
        if (tab) {
            [self tapItem:tab tag:@"直播tab"];
            _tappedLiveTab++;
            [self goState:DYStateResults delay:1.6];
            return;
        }
    }

    // 找标题含关键词的卡片，跳过已试过的
    DYTextItem *card = nil;
    for (DYTextItem *it in items) {
        if (CGRectGetMidY(it.normRect) < 0.15) continue;    // 顶部 tab 区
        if (CGRectGetMidY(it.normRect) > 0.93) continue;    // 底部 tab 区
        if (it.text.length < 4) continue;                   // 太短的不是标题
        if ([_triedTitles containsObject:it.text]) continue;
        for (NSString *kw in cfg.roomTitleKeywords) {
            if ([it.text containsString:kw]) { card = it; break; }
        }
        if (card) break;
    }

    if (!card) {
        DYLOG(@"当前列表没有新房间，换关键词");
        [self nextKeyword];
        [self goState:DYStateBoot delay:self.randomJitter + 0.5];
        return;
    }

    _pendingTitle = card.text;
    [_triedTitles addObject:card.text];
    _roomsThisRound++;
    _enteredRooms++;
    _roomEnterTime = CACurrentMediaTime();
    _hotspotTried = NO;
    DYLOG(@"进入直播间(%ld)：%@", (long)_enteredRooms, card.text);
    [self tapItem:card tag:@"直播间卡片"];
    [self goState:DYStateInRoom delay:[DYConfig shared].enterWait];
}

// —— 4. 房间内识别福袋 ——
- (void)doInRoom:(NSArray *)items {
    DYConfig *cfg = [DYConfig shared];
    NSTimeInterval elapsed = [self stateElapsed];

    // 确认真的在直播间（有输入框提示/礼物/人气 等）
    BOOL alive = NO;
    for (NSString *h in @[@"说点什么", @"礼物", @"人气", @"在线"]) {
        if ([self itemIn:items keywords:@[h]]) { alive = YES; break; }
    }
    if (!alive) {
        UIView *fr = [DYScreen findViewWithTexts:@[@"说点什么"]];
        if (fr) alive = YES;
    }

    if (!alive) {
        if (elapsed > 8.0) {
            DYLOG(@"未进入直播间，返回重选");
            [self goState:DYStateExit delay:0];
        }
        return;
    }

    // 找福袋入口
    DYTextItem *bag = [self itemIn:items keywords:cfg.luckyBagKeywords];
    if (bag) {
        DYLOG(@"发现福袋入口「%@」", bag.text);
        [self tapItem:bag tag:@"福袋"];
        [self goState:DYStateParticipate delay:1.4];
        return;
    }

    // 有些房间直接显示「参与」
    DYTextItem *direct = [self itemIn:items keywords:cfg.participateKeywords];
    if (direct) {
        DYLOG(@"房间直接显示「%@」", direct.text);
        [self tapItem:direct tag:@"参与"];
        [self goState:DYStateParticipate delay:1.2];
        return;
    }

    // 福袋入口是纯图标、OCR 抓不到：用校准过的热区试探一次
    if (!_hotspotTried && cfg.bagHotspotX > 0.01 && cfg.bagHotspotY > 0.01
        && elapsed > 2.0) {
        _hotspotTried = YES;
        DYLOG(@"无文字命中，热区试探点击 {%.2f, %.2f}", cfg.bagHotspotX, cfg.bagHotspotY);
        [DYScreen tapNormalizedPoint:CGPointMake(cfg.bagHotspotX, cfg.bagHotspotY)];
        // 点开后面板里必须有参与类文字，否则 doParticipate 会 3 秒内退出
        [self goState:DYStateParticipate delay:1.4];
        return;
    }

    if (elapsed > 6.0) {
        DYLOG(@"本房间无福袋，退出");
        [self goState:DYStateExit delay:0];
    }
}

// —— 5. 参与福袋 ——
- (void)doParticipate:(NSArray *)items {
    DYConfig *cfg = [DYConfig shared];

    // 已参与
    DYTextItem *done = [self itemIn:items keywords:cfg.doneKeywords];
    if (done) {
        _successCount++;
        DYLOG(@"✅ 参与成功「%@」", done.text);
        [self goState:DYStateExit delay:0.4];
        return;
    }

    // 前置条件
    DYTextItem *cond = [self itemIn:items keywords:cfg.conditionKeywords];
    if (cond) {
        NSString *t = cond.text;
        if ([t containsString:@"关注"] && cfg.autoFollow) {
            [self tapItem:cond tag:@"关注"];
            [self goState:DYStateParticipate delay:1.5];
            return;
        }
        if ([t containsString:@"粉丝团"] && cfg.autoJoinFansClub) {
            [self tapItem:cond tag:@"加粉丝团"];
            [self goState:DYStateParticipate delay:1.8];
            return;
        }
        if (([t containsString:@"弹幕"] || [t containsString:@"口令"] || [t containsString:@"评论"])
            && cfg.autoComment) {
            [DYScreen typeText:cfg.commentText];
            [self goState:DYStateParticipate delay:1.0];
            return;
        }
        DYLOG(@"需要前置条件「%@」，未开启自动处理，跳过", t);
        [self goState:DYStateExit delay:0];
        return;
    }

    // 点参与
    DYTextItem *btn = [self itemIn:items keywords:cfg.participateKeywords];
    if (btn) {
        [self tapItem:btn tag:@"参与按钮"];
        [self goState:DYStateParticipate delay:1.3];
        return;
    }

    if ([self stateElapsed] > 8.0) {
        DYLOG(@"参与超时，放弃本房间");
        [self goState:DYStateExit delay:0];
    }
}

// —— 6. 退出 ——
- (void)doExit:(NSArray *)items {
    DYConfig *cfg = [DYConfig shared];

    // 优先点返回，保留搜索结果页的滚动位置
    DYTextItem *back = [self itemIn:items keywords:@[@"返回", @"关闭"] yMin:0.0 yMax:0.25];
    if (back) {
        [self tapItem:back tag:@"返回"];
    } else {
        UIView *v = [DYScreen findViewWithTexts:@[@"返回", @"关闭", @"back", @"close"]];
        if (v) {
            [DYScreen tapView:v];
            DYLOG(@"点击返回控件");
        } else {
            NSString *kw = [self currentKeyword];
            NSString *enc = [kw stringByAddingPercentEncodingWithAllowedCharacters:
                             [NSCharacterSet URLQueryAllowedCharacterSet]];
            DYLOG(@"找不到返回，用 deeplink 回到搜索");
            [self openURLString:[NSString stringWithFormat:@"snssdk1128://search?keyword=%@", enc]];
            [self goState:DYStateResults delay:2.0];
            return;
        }
    }
    [self goState:DYStateResults delay:self.randomJitter + 0.8];
}

#pragma mark - 探测模式

- (void)setReconMode:(BOOL)on {
    _reconMode = on;
    if (on && !_running) {
        _running = YES;
        _timer = [NSTimer timerWithTimeInterval:2.0 target:self selector:@selector(tick)
                                      userInfo:nil repeats:YES];
        [[NSRunLoop mainRunLoop] addTimer:_timer forMode:NSRunLoopCommonModes];
    }
    DYLOG(@"探测模式：%@", on ? @"开（只记录不点击）" : @"关");
}

- (void)reconWithItems:(NSArray<DYTextItem *> *)items {
    NSString *flat = [DYOCR flatten:items];
    if ([flat isEqualToString:_lastQuickText]) return;   // 画面没变就不重复刷日志
    _lastQuickText = flat;
    DYLOG(@"--- OCR %lu 条 ---\n%@", (unsigned long)items.count, flat);
}

- (void)dumpOnce {
    UIImage *shot = [DYScreen snapshot];
    dispatch_async(_ocrQueue, ^{
        NSArray *items = [DYOCR recognize:shot fast:NO];
        NSString *tree = [DYScreen dumpViewTreeWithLimit:400];
        dispatch_async(dispatch_get_main_queue(), ^{
            DYLOG(@"===== OCR 全量 =====\n%@", [DYOCR flatten:items]);
            for (DYTextItem *it in items) DYLOG(@"  %@", it);
            DYLOG(@"===== 控件树(前400) =====\n%@", tree);
        });
    });
}

@end
