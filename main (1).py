"""
================================================================
 ANDROMAT CHAT MOBILE - v1 "NO LIMITS" (Kivy / Android APK)
================================================================
Red / Black / Cyan / White theme. Screens:
  LOGIN -> API ID/HASH/phone/code/2FA
  HOME  -> hub
  CHATS -> Telegram groups + text chat
  MIC   -> LOUD MIC (v8 DSP engine live on phone speakers)

Built as APK via buildozer (see buildozer.spec + GitHub workflow).
================================================================
"""
import math
import threading

import numpy as np

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform

Window.clearcolor = (0.02, 0.02, 0.03, 1)  # near black

RED = "#ff1e1e"
CYAN = "#00e5ff"
WHITE = "#f2f2f2"
GREY = "#7a7a8a"

IS_ANDROID = platform == "android"

import dsp_mobile
from dsp_mobile import MobileDSP, MODES


# ----------------------------------------------------------------
# styled widgets
# ----------------------------------------------------------------
def make_label(text, color=WHITE, size=16, bold=False, halign="left"):
    lbl = Label(text=text, color=color, font_size=size, halign=halign,
                markup=True, size_hint_y=None, height=size * 2.2)
    lbl.bind(width=lambda inst, w: setattr(inst, "text_size", (w, None)))
    return lbl


def make_input(hint, password=False, multiline=False, h=48):
    ti = TextInput(hint_text=hint, password=password, multiline=multiline,
                   size_hint_y=None, height=h,
                   background_color=(0.055, 0.055, 0.09, 1),
                   foreground_color=(0.95, 0.95, 0.95, 1),
                   cursor_color=(0, 0.9, 1, 1),
                   hint_text_color=(0.45, 0.45, 0.55, 1),
                   font_size=15, write_tab=False)
    return ti


def make_button(text, bg=(0.09, 0.09, 0.14, 1), color=(1, 1, 1, 1), h=52):
    btn = Button(text=text, background_normal="", background_color=bg,
                 color=color, size_hint_y=None, height=h, font_size=15,
                 bold=True)
    return btn


RED_BTN = (0.72, 0.06, 0.06, 1)
CYAN_BTN = (0.0, 0.42, 0.5, 1)
DARK_BTN = (0.09, 0.09, 0.14, 1)


# ----------------------------------------------------------------
# Screens
# ----------------------------------------------------------------
class LoginScreen(Screen):
    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.app_ref = app_ref
        root = BoxLayout(orientation="vertical", padding=24, spacing=10)

        root.add_widget(make_label("ANDROMAT", RED, 40, True))
        root.add_widget(make_label("CHAT MOBILE - NO LIMITS", CYAN, 16, True))
        root.add_widget(make_label("Apna khud ka Telegram client."
                                   " my.telegram.org se API ID aur API"
                                   " HASH lo (free).", GREY, 13))

        self.api_id = make_input("API ID (number)")
        self.api_hash = make_input("API HASH")
        self.phone = make_input("Phone (+91...)")
        self.code = make_input("Telegram code (bhejne ke baad)", password=True)
        self.pw = make_input("2FA password (agar ho)", password=True)
        for w in (self.api_id, self.api_hash, self.phone, self.code, self.pw):
            root.add_widget(w)

        self.btn_connect = make_button("CONNECT", RED_BTN)
        self.btn_connect.bind(on_press=self.do_connect)
        root.add_widget(self.btn_connect)

        self.status = make_label("Ready.", GREY, 13)
        root.add_widget(self.status)
        self.add_widget(root)

    def do_connect(self, *a):
        self.btn_connect.disabled = True
        self.btn_connect.text = "CONNECTING..."
        self.app_ref.mgr.connect(
            self.api_id.text or "0", self.api_hash.text or "",
            self.phone.text or "")

    def set_status(self, msg):
        self.status.text = msg
        if msg.startswith("Logged in"):
            self.btn_connect.disabled = False
            self.btn_connect.text = "CONNECTED"


class HomeScreen(Screen):
    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.app_ref = app_ref
        root = BoxLayout(orientation="vertical", padding=24, spacing=14)
        root.add_widget(make_label("ANDROMAT", RED, 36, True))
        self.hello = make_label("", WHITE, 15)
        root.add_widget(self.hello)
        root.add_widget(make_label("", GREY, 6))

        b1 = make_button("CHATS", CYAN_BTN)
        b1.bind(on_press=lambda *a: self.app_ref.goto("chats"))
        b2 = make_button("LOUD MIC  (v8 ENGINE)", RED_BTN)
        b2.bind(on_press=lambda *a: self.app_ref.goto("mic"))
        b3 = make_button("LOGOUT", DARK_BTN)
        b3.bind(on_press=self.do_logout)
        root.add_widget(b1)
        root.add_widget(b2)
        root.add_widget(b3)
        root.add_widget(make_label(
            "Voice chat streaming = PC wala andromat_chat.py"
            " (pytgcalls sirf desktop par chalta hai)."
            " Mobile app: chat + loud mic.", GREY, 12))
        self.add_widget(root)

    def do_logout(self, *a):
        self.app_ref.mgr.logout()
        self.app_ref.goto("login")


class ChatScreen(Screen):
    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.app_ref = app_ref
        self.current_chat = None
        root = BoxLayout(orientation="vertical", padding=12, spacing=8)
        top = BoxLayout(size_hint_y=None, height=48, spacing=8)
        back = make_button("< BACK", DARK_BTN)
        back.bind(on_press=lambda *a: self.app_ref.goto("home"))
        refresh = make_button("REFRESH", CYAN_BTN)
        refresh.bind(on_press=self.load)
        top.add_widget(back)
        top.add_widget(refresh)
        root.add_widget(top)

        self.list_area = GridLayout(cols=1, size_hint_y=None, spacing=6)
        self.list_area.bind(minimum_height=self.list_area.setter("height"))
        self.sv = ScrollView()
        self.sv.add_widget(self.list_area)
        root.add_widget(self.sv)

        bottom = BoxLayout(size_hint_y=None, height=52, spacing=8)
        self.msg_input = make_input("Message likho...")
        send = make_button("SEND", RED_BTN)
        send.bind(on_press=self.send)
        bottom.add_widget(self.msg_input)
        bottom.add_widget(send)
        root.add_widget(bottom)
        self.add_widget(root)

    def load(self, *a):
        self.list_area.clear_widgets()
        self.list_area.add_widget(make_label("Loading...", GREY, 14))
        self.app_ref.mgr.fetch_dialogs()

    def show_dialogs(self, items):
        self.list_area.clear_widgets()
        if not items:
            self.list_area.add_widget(make_label("Koi chat nahi mili.", GREY, 14))
        for it in items:
            txt = "%s  (%d)" % (it["name"], it["unread"]) if it["unread"] \
                else it["name"]
            b = make_button(txt, DARK_BTN, WHITE, 44)
            b.bind(on_press=lambda inst, cid=it["id"], nm=it["name"]:
                   self.pick(cid, nm))
            self.list_area.add_widget(b)

    def pick(self, chat_id, name):
        self.current_chat = (chat_id, name)

    def send(self, *a):
        if not self.current_chat:
            return
        text = self.msg_input.text.strip()
        if not text:
            return
        self.app_ref.mgr.send_message(self.current_chat[0], text)
        self.msg_input.text = ""


class MicScreen(Screen):
    """LOUD MIC: phone mic -> v8 DSP -> loud speakers (earphones!)."""

    def __init__(self, app_ref, **kw):
        super().__init__(**kw)
        self.app_ref = app_ref
        self.running = False
        self.thread = None
        self.dsp = MobileDSP()

        root = BoxLayout(orientation="vertical", padding=16, spacing=8)
        top = BoxLayout(size_hint_y=None, height=48, spacing=8)
        back = make_button("< BACK", DARK_BTN)
        back.bind(on_press=lambda *a: self.app_ref.goto("home"))
        top.add_widget(back)
        root.add_widget(top)

        root.add_widget(make_label("LOUD MIC", RED, 30, True))
        root.add_widget(make_label(
            "WARNING: earphones lagao - speaker se feedback"
            " (whistle) aayega warna.", GREY, 13))

        mode_row = GridLayout(cols=2, spacing=6, size_hint_y=None, height=120)
        self.mode_buttons = {}
        for m in MODES:
            b = make_button(m, DARK_BTN, WHITE, 44)
            b.bind(on_press=lambda inst, md=m: self.set_mode(md))
            self.mode_buttons[m] = b
            mode_row.add_widget(b)
        root.add_widget(mode_row)

        self.btn_start = make_button("START LOUD MIC", RED_BTN, h=64)
        self.btn_start.bind(on_press=self.toggle)
        root.add_widget(self.btn_start)

        self.meter = make_label("LEVEL: -inf dB", CYAN, 16, True)
        root.add_widget(self.meter)
        self.err = make_label("", GREY, 12)
        root.add_widget(self.err)
        self.add_widget(root)
        self.set_mode("VOICE SLAM")
        Clock.schedule_interval(self.update_ui, 0.15)

    def set_mode(self, m):
        self.dsp.set_mode(m)
        for k, b in self.mode_buttons.items():
            b.background_color = RED_BTN if k == m else DARK_BTN

    def toggle(self, *a):
        if self.running:
            self.running = False
            self.btn_start.text = "START LOUD MIC"
            return
        if IS_ANDROID:
            dsp_mobile.ensure_mic_permission()
        self.running = True
        self.btn_start.text = "STOP"
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        from jnius_helper import AndroidMic, AndroidSpeaker, android_available
        mic = AndroidMic(self.dsp.fs)
        spk = AndroidSpeaker(self.dsp.fs)
        if not android_available():
            Clock.schedule_once(lambda dt: self.show_err(
                "Android hi chahiye mic/speaker ke liye."), 0)
            self.running = False
            return
        if not mic.ok:
            Clock.schedule_once(lambda dt: self.show_err(
                "MIC fail: %s (permission dena zaroori)" % mic.last_error), 0)
            self.running = False
            return
        if not spk.ok:
            Clock.schedule_once(lambda dt: self.show_err(
                "Speaker fail: %s" % spk.last_error), 0)
            self.running = False
            return
        mic.start()
        spk.start()
        self.level = "-inf"
        while self.running:
            block = mic.read_block()
            if block is None:
                continue
            out = self.dsp.process(block)
            spk.write_block(out)
            rms = float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))
            self.level = "%+.1f" % (20 * math.log10(rms + 1e-9))
            if self.dsp.last_error:
                Clock.schedule_once(lambda dt, e=self.dsp.last_error:
                                    self.show_err("DSP: " + e), 0)
                self.dsp.last_error = None
        mic.stop()
        spk.stop()

    def show_err(self, msg):
        self.err.text = msg

    def update_ui(self, dt):
        lvl = getattr(self, "level", None)
        if lvl and self.running:
            self.meter.text = "LEVEL: %s dB   [%s]" % (lvl, self.dsp.mode)


# ----------------------------------------------------------------
# App
# ----------------------------------------------------------------
class AndromatMobileApp(App):
    title = "ANDROMAT CHAT"

    def build(self):
        self.sm = ScreenManager()
        self.mgr = TGManager(
            session_dir=self.user_data_dir,
            on_status=lambda m: Clock.schedule_once(
                lambda dt: self.scr_login.set_status(m), 0),
            on_code=lambda: Clock.schedule_once(
                lambda dt: self.scr_login.set_status("Code Telegram par"
                                                     " bhej diya - upar daalo"), 0),
            on_password=lambda: Clock.schedule_once(
                lambda dt: self.scr_login.set_status("2FA password daalo"), 0),
            on_ready=lambda name: Clock.schedule_once(
                lambda dt: self.after_login(name), 0),
            on_dialogs=lambda items: Clock.schedule_once(
                lambda dt: self.scr_chats.show_dialogs(items), 0),
            on_error=lambda m: Clock.schedule_once(
                lambda dt: self.scr_login.set_status("[ERR] " + m), 0),
        )
        self.mgr.start_engine()

        self.scr_login = LoginScreen(self, name="login")
        self.scr_home = HomeScreen(self, name="home")
        self.scr_chats = ChatScreen(self, name="chats")
        self.scr_mic = MicScreen(self, name="mic")
        for s in (self.scr_login, self.scr_home, self.scr_chats, self.scr_mic):
            self.sm.add_widget(s)
        return self.sm

    def after_login(self, name):
        self.scr_login.set_status("Logged in: " + str(name))
        self.scr_home.hello.text = "Namaste, %s!" % name
        self.goto("home")

    def goto(self, name):
        self.sm.current = name
        if name == "chats":
            self.scr_chats.load()

    def on_stop(self):
        try:
            self.mgr.loop.call_soon_threadsafe(self.mgr.loop.stop)
        except Exception:
            pass


if __name__ == "__main__":
    AndromatMobileApp().run()
