ARCHS = arm64 arm64e
TARGET = iphone:clang:16.5:14.0
INSTALL_TARGET_PROCESSES = Aweme

include $(THEOS)/makefiles/common.mk

LIBRARY_NAME = DYFudai
DYFudai_FILES = $(wildcard Sources/*.m)
DYFudai_CFLAGS = -fobjc-arc -ISources -Wno-deprecated-declarations -Wno-unused-function -Wno-unused-parameter -Wno-unused-variable
DYFudai_FRAMEWORKS = UIKit Foundation Vision QuartzCore CoreGraphics
DYFudai_LDFLAGS = -undefined dynamic_lookup
DYFudai_INSTALL_PATH = /usr/lib

include $(THEOS_MAKE_PATH)/library.mk
