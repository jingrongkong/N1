#import "DYLog.h"

// 日志落在抖音沙盒 Documents 下，TrollStore 自带文件管理器可直接查看/导出。
// 路径：<抖音沙盒>/Documents/dyfudai.log

static NSString *gLogPath = nil;
static const unsigned long long kMaxLogSize = 2ull * 1024 * 1024;

@implementation DYLog

+ (NSString *)logFilePath {
    if (!gLogPath) {
        NSString *home = NSHomeDirectory();
        gLogPath = [home stringByAppendingPathComponent:@"Documents/dyfudai.log"];
    }
    return gLogPath;
}

+ (void)rotateIfNeeded {
    NSFileManager *fm = [NSFileManager defaultManager];
    NSDictionary *attr = [fm attributesOfItemAtPath:[self logFilePath] error:nil];
    if (attr && [attr fileSize] > kMaxLogSize) {
        NSString *old = [[self logFilePath] stringByAppendingString:@".1"];
        [fm removeItemAtPath:old error:nil];
        [fm moveItemAtPath:[self logFilePath] toPath:old error:nil];
    }
}

+ (void)log:(NSString *)fmt, ... {
    va_list args;
    va_start(args, fmt);
    NSString *msg = [[NSString alloc] initWithFormat:fmt arguments:args];
    va_end(args);

    NSDateFormatter *df = [[NSDateFormatter alloc] init];
    df.dateFormat = @"MM-dd HH:mm:ss.SSS";
    NSString *line = [NSString stringWithFormat:@"[%@] %@\n", [df stringFromDate:[NSDate date]], msg];

    NSLog(@"[DYFudai] %@", msg);

    static dispatch_queue_t q;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        q = dispatch_queue_create("dyfudai.log", DISPATCH_QUEUE_SERIAL);
    });
    dispatch_async(q, ^{
        [self rotateIfNeeded];
        NSFileHandle *fh = [NSFileHandle fileHandleForWritingAtPath:[self logFilePath]];
        if (!fh) {
            [[NSFileManager defaultManager] createFileAtPath:[self logFilePath] contents:nil attributes:nil];
            fh = [NSFileHandle fileHandleForWritingAtPath:[self logFilePath]];
        }
        [fh seekToEndOfFile];
        [fh writeData:[line dataUsingEncoding:NSUTF8StringEncoding]];
        [fh closeFile];
    });
}

+ (void)clear {
    [[NSFileManager defaultManager] removeItemAtPath:[self logFilePath] error:nil];
}

@end
