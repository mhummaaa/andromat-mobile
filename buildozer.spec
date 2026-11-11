[app]
title = ANDROMAT CHAT
package.name = andromatchat
package.domain = org.andromat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

requirements = python3,kivy==2.3.0,telethon,numpy,pyjnius,android
# Note: cryptography hata diya - Telethon ko sirf pyaes+rsa chahiye (pure Python),
# aur cryptography recipe Android pe heavy Rust build maangta hai

orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
# CI par SDK license auto-accept (isse 'license is not accepted' error nahi aayega)
android.accept_sdk_license = True
# known-good build tools (37 wala license issue avoid)
android.build_tools_version = 34.0.0

# icon & presplash (files in project root)
icon.filename = icon.png
presplash.filename = presplash.png

# keep build lean
warnings_as_errors = False
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
