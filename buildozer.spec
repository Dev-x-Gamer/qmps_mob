[app]
title = Patient Token Slip
package.name = qmstoken
package.domain = com.warissoftware
source.dir = .
source.include_exts = py,png,jpg,kv,json
version = 1.0

requirements = python3,kivy==2.3.0,pyjnius,android
orientation = portrait
fullscreen = 0

# Bluetooth (classic) permissions - Android 12+ needs CONNECT/SCAN, older needs BLUETOOTH/ADMIN
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,BLUETOOTH_CONNECT,BLUETOOTH_SCAN,ACCESS_FINE_LOCATION

android.api = 34
android.minapi = 24
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
