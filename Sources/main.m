#import "DYCommon.h"
#import "DYConfig.h"
#import "DYEngine.h"
#import "DYLog.h"
#import "DYPanel.h"

// dylib 载入点。TrollFools / ElleKit 注入后会在进程启动早期执行。
// 这里刻意不依赖 CydiaSubstrate / libhooker，用纯 runtime + 定时器实现，
// 因此在 TrollStore（无越狱）环境下也能正常工作。

static BOOL gBooted = NO;

static void DYBootstrap(void) {
    if (gBooted) return;
    gBooted = YES;

    NSString *bid = [NSBundle mainBundle].bundleIdentifier ?: @"";
    DYLOG(@"注入成功 bundle=%@ 版本=%@", bid,
          [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"]);

    DYConfig *cfg = [DYConfig shared];

    if (cfg.showFloatingPanel) {
        [[DYPanel shared] show];
    }
    if (cfg.enabled) {
        DYLOG(@"配置 enabled=true，自动启动引擎");
        [[DYEngine shared] start];
    }
}

__attribute__((constructor))
static void DYFudaiInit(void) {
    // 主队列 runloop 还没跑起来时建 UI 会崩，延后到 App 起来再初始化
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.5 * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        @try {
            DYBootstrap();
        } @catch (NSException *e) {
            DYLOG(@"初始化异常：%@", e);
        }
    });
}
