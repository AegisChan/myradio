[app]
title = 湖北经典音乐广播
package.name = hubeiradio
package.domain = org.jdyy
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

# 黄金稳定组合：KivyMD 1.1.1 必须搭配 Kivy 2.1.0，否则安卓底层必崩
requirements = python3,kivy==2.1.0,kivymd==1.1.1,sdl2_ttf==2.0.15,pyjnius,pillow,android
p4a.branch = v2024.01.21

# 砍掉导致崩溃的32位架构，只保留现代手机的64位
android.archs = arm64-v8a

orientation = portrait
fullscreen = 0
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
warn_on_root = 1
