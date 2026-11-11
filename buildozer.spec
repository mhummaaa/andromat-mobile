[app]
title = ANDROMAT CHAT
package.name = andromatchat
package.domain = org.andromat
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0

requirements = python3,kivy==2.3.0,telethon,numpy,pyjnius,cryptography,android

orientation = portrait
fullscreen = 0
android.permissions = INTERNET,RECORD_AUDIO
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True

# icon & presplash (files in project root)
icon.filename = icon.png
presplash.filename = presplash.png

# keep build lean
warnings_as_errors = False
log_level = 2

[buildozer]
log_level = 2
warn_on_root = 1
