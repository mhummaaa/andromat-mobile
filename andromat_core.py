"""
================================================================
 ANDROMAT MOBILE - Telegram Core (Telethon userbot, thread-safe)
================================================================
Own asyncio loop in a background thread. Kivy UI talks to it via
plain method calls; results come back through callables which the
UI wraps with Clock.schedule_once (main-thread safe).

Flow: connect -> (code / password) -> ready -> dialogs / send msg.
Session file lives in the app's private storage (user_data_dir).
================================================================
"""
import os
import threading
import asyncio

# Telethon is a hard requirement only when actually connecting.
try:
    from telethon import TelegramClient, events
    HAVE_TELETHON = True
except Exception:
    TelegramClient = None
    events = None
    HAVE_TELETHON = False

from telethon.errors import SessionPasswordNeededError  # noqa


class TGManager(threading.Thread):
    """Runs its own asyncio loop. UI-safe: fire-and-forget methods."""

    def __init__(self, session_dir, on_status=None, on_code=None,
                 on_password=None, on_ready=None, on_dialogs=None,
                 on_error=None, on_message=None):
        super().__init__(daemon=True)
        self.session_path = os.path.join(session_dir, "andromat_mobile")
        self.loop = None
        self.client = None
        self.phone = None
        self._code_event = threading.Event()
        self._pw_event = threading.Event()
        self._code_value = None
        self._pw_value = None
        # callbacks (will be wrapped by UI for main thread)
        self.on_status = on_status
        self.on_code = on_code
        self.on_password = on_password
        self.on_ready = on_ready
        self.on_dialogs = on_dialogs
        self.on_error = on_error
        self.on_message = on_message
        self._stop = False

    # ---------- callbacks ----------
    def _status(self, msg):
        if self.on_status:
            self.on_status(msg)

    def _error(self, msg):
        if self.on_error:
            self.on_error(msg)

    # ---------- thread main ----------
    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _submit(self, coro):
        """Schedule a coroutine on our loop from any thread."""
        if self.loop is None or self.loop.is_closed():
            coro.close()  # avoid 'never awaited' warning
            self._error("Engine band hai - pehle CONNECT dabao")
            return
        asyncio.run_coroutine_threadsafe(coro, self.loop)

    # ---------- public API (called from UI thread) ----------
    def start_engine(self):
        if not self.is_alive():
            self.start()

    def connect(self, api_id, api_hash, phone):
        self.start_engine()
        self._submit(self._connect(int(api_id), api_hash.strip(), phone.strip()))

    def submit_code(self, code):
        self._code_value = code.strip()
        self._code_event.set()

    def submit_password(self, pw):
        self._pw_value = pw
        self._pw_event.set()

    def fetch_dialogs(self):
        self._submit(self._fetch_dialogs())

    def send_message(self, chat_id, text):
        self._submit(self._send(chat_id, text))

    def logout(self):
        self._submit(self._logout())

    # ---------- coroutines (on our loop) ----------
    async def _connect(self, api_id, api_hash, phone):
        try:
            if not HAVE_TELETHON:
                self._error("Telethon install nahi hua - requirements check karo")
                return
            if not api_id or not api_hash or not phone:
                self._error("API ID / API HASH / phone - teeno bharo")
                return
            self._status("Connecting...")
            self.phone = phone
            self.client = TelegramClient(
                self.session_path, api_id, api_hash,
                device_model="ANDROMAT MOBILE", system_version="1.0",
                app_version="1.0",
            )
            await self.client.connect()
            if not await self.client.is_user_authorized():
                self._status("Code bhej raha hoon...")
                await self.client.send_code_request(phone)
                self._status("Telegram code daalo")
                if self.on_code:
                    self.on_code()
                self._code_event.clear()
                await asyncio.get_event_loop().run_in_executor(
                    None, self._code_event.wait)
                code = self._code_value
                try:
                    await self.client.sign_in(phone=phone, code=code)
                except SessionPasswordNeededError:
                    self._status("2FA password chahiye")
                    if self.on_password:
                        self.on_password()
                    self._pw_event.clear()
                    await asyncio.get_event_loop().run_in_executor(
                        None, self._pw_event.wait)
                    await self.client.sign_in(password=self._pw_value)
            me = await self.client.get_me()
            name = getattr(me, "first_name", "?") or "?"
            self._status("Logged in: " + name)
            if self.on_ready:
                self.on_ready(name)
        except Exception as e:
            self._error("Connect fail: %s" % e)

    async def _fetch_dialogs(self):
        try:
            if not self.client:
                self._error("Pehle login karo")
                return
            self._status("Chats laa raha hoon...")
            items = []
            async for d in self.client.iter_dialogs(limit=60):
                items.append({
                    "id": d.id,
                    "name": d.name or "???",
                    "unread": getattr(d, "unread_count", 0),
                })
            if self.on_dialogs:
                self.on_dialogs(items)
            self._status("%d chats mile" % len(items))
        except Exception as e:
            self._error("Dialogs fail: %s" % e)

    async def _send(self, chat_id, text):
        try:
            if not self.client or not text:
                return
            await self.client.send_message(int(chat_id), text)
        except Exception as e:
            self._error("Send fail: %s" % e)

    async def _logout(self):
        try:
            if self.client:
                await self.client.log_out()
                self.client = None
                self._status("Logged out")
        except Exception as e:
            self._error("Logout fail: %s" % e)
