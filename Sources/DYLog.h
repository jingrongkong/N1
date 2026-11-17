#import "DYCommon.h"

@interface DYLog : NSObject
+ (void)log:(NSString *)fmt, ... NS_FORMAT_FUNCTION(1, 2);
+ (NSString *)logFilePath;
+ (void)clear;
@end
