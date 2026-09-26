[app]
title = 湖北经典音乐广播
package.name = hubeiradio
package.domain = org.jdyy
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,ttc
version = 1.0

# 最新最稳的组合：Kivy 2.3.0 完美适配安卓13+，KivyMD 1.2.0 修复了所有闪退 Bug
requirements = python3,kivy==2.3.0,kivymd==1.2.0,pyjnius,pillow,android
p4a.branch = v2024.01.21

# 砍掉导致崩溃�?2位架构，只保留现代手机的64�?android.archs = arm64-v8a

orientation = portrait
fullscreen = 0
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.entrypoint = org.kivy.android.PythonActivity

[buildozer]
log_level = 2
warn_on_root = 1

