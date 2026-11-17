#import "DYConfig.h"
#import "DYLog.h"

@implementation DYConfig

+ (instancetype)shared {
    static DYConfig *c;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        c = [[DYConfig alloc] init];
        [c applyDefaults];
        [c reload];
    });
    return c;
}

- (NSString *)configPath {
    return [NSHomeDirectory() stringByAppendingPathComponent:@"Documents/dyfudai.json"];
}

- (void)applyDefaults {
    _enabled             = NO;   // 默认不自动跑，避免一开 App 就乱点
    _searchKeywords      = @[@"福袋", @"抽奖", @"发福袋"];
    _roomTitleKeywords   = @[@"福袋", @"抽奖", @"红包", @"福利"];
    _luckyBagKeywords    = @[@"福袋", @"抽奖", @"红包雨", @"幸运袋"];
    _participateKeywords = @[@"立即参与", @"立即抽奖", @"参与抽奖", @"点击参与", @"参与", @"立即领取"];
    _doneKeywords        = @[@"已参与", @"已参加", @"已领", @"等待开奖", @"已抢光"];
    _conditionKeywords   = @[@"关注主播", @"加入粉丝团", @"发送弹幕", @"发送口令", @"观看"];

    _enterWait           = 3.0;
    _roomStaySeconds     = 45.0;
    _maxRoomsPerRound    = 30;
    _maxRoomsPerHour     = 60;
    _jitterMin           = 0.6;
    _jitterMax           = 1.8;

    _tapMode             = @"view";
    _hidUsePixels        = NO;

    _autoFollow          = NO;
    _autoJoinFansClub    = NO;
    _autoComment         = NO;
    _commentText         = @"福袋";

    _showFloatingPanel   = YES;

    _bagHotspotX         = 0;
    _bagHotspotY         = 0;
}

- (void)reload {
    NSData *data = [NSData dataWithContentsOfFile:[self configPath]];
    if (!data) {
        DYLOG(@"未找到配置文件，使用默认配置：%@", [self configPath]);
        [self writeExampleIfMissing];
        return;
    }
    NSError *err = nil;
    NSDictionary *j = [NSJSONSerialization JSONObjectWithData:data options:0 error:&err];
    if (![j isKindOfClass:[NSDictionary class]]) {
        DYLOG(@"配置解析失败：%@", err);
        return;
    }

    #define GET_BOOL(k, p)  if (j[@#k]) _##p = [j[@#k] boolValue]
    #define GET_INT(k, p)   if (j[@#k]) _##p = [j[@#k] integerValue]
    #define GET_FLT(k, p)   if (j[@#k]) _##p = [j[@#k] floatValue]
    #define GET_STR(k, p)   if (j[@#k]) _##p = [j[@#k] description]
    #define GET_ARR(k, p)   if ([j[@#k] isKindOfClass:[NSArray class]]) _##p = j[@#k]

    GET_BOOL(enabled, enabled);
    GET_ARR(searchKeywords, searchKeywords);
    GET_ARR(roomTitleKeywords, roomTitleKeywords);
    GET_ARR(luckyBagKeywords, luckyBagKeywords);
    GET_ARR(participateKeywords, participateKeywords);
    GET_ARR(doneKeywords, doneKeywords);
    GET_ARR(conditionKeywords, conditionKeywords);
    GET_FLT(enterWait, enterWait);
    GET_FLT(roomStaySeconds, roomStaySeconds);
    GET_INT(maxRoomsPerRound, maxRoomsPerRound);
    GET_INT(maxRoomsPerHour, maxRoomsPerHour);
    GET_FLT(jitterMin, jitterMin);
    GET_FLT(jitterMax, jitterMax);
    GET_STR(tapMode, tapMode);
    GET_BOOL(hidUsePixels, hidUsePixels);
    GET_BOOL(autoFollow, autoFollow);
    GET_BOOL(autoJoinFansClub, autoJoinFansClub);
    GET_BOOL(autoComment, autoComment);
    GET_STR(commentText, commentText);
    GET_BOOL(showFloatingPanel, showFloatingPanel);
    GET_FLT(bagHotspotX, bagHotspotX);
    GET_FLT(bagHotspotY, bagHotspotY);

    #undef GET_BOOL
    #undef GET_INT
    #undef GET_FLT
    #undef GET_STR
    #undef GET_ARR

    DYLOG(@"配置已加载 tapMode=%@ stay=%.0fs", _tapMode, _roomStaySeconds);
}

- (void)writeExampleIfMissing {
    NSDictionary *d = @{
        @"enabled": @NO,
        @"searchKeywords": _searchKeywords,
        @"participateKeywords": _participateKeywords,
        @"roomStaySeconds": @(_roomStaySeconds),
        @"maxRoomsPerHour": @(_maxRoomsPerHour),
        @"tapMode": _tapMode,
        @"autoComment": @NO,
        @"autoFollow": @NO,
        @"showFloatingPanel": @YES
    };
    NSData *out = [NSJSONSerialization dataWithJSONObject:d
                                                  options:NSJSONWritingPrettyPrinted
                                                    error:nil];
    [out writeToFile:[self configPath] atomically:YES];
    DYLOG(@"已生成示例配置：%@", [self configPath]);
}

@end
