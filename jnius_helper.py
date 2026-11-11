"""
================================================================
 ANDROMAT MOBILE - Android Audio I/O (pyjnius) + Desktop fallback
================================================================
Phone par: android.media.AudioRecord (mic capture, RAW amplitude)
           android.media.AudioTrack (loud playback, MUSIC stream)
Desktop test par: graceful fallback (no crash).
Format: 16-bit PCM mono, 48000 Hz.
================================================================
"""
import numpy as np

FS = 48000
BLOCK = 1920  # 40 ms

_android_ok = None


def android_available():
    global _android_ok
    if _android_ok is None:
        try:
            from jnius import autoclass  # noqa: F401
            _android_ok = True
        except Exception:
            _android_ok = False
    return _android_ok


def ensure_mic_permission():
    """Request RECORD_AUDIO at runtime. Non-blocking on Android."""
    if not android_available():
        return False
    try:
        from android.permissions import request_permissions, Permission
        request_permissions([Permission.RECORD_AUDIO])
        return True
    except Exception:
        return False


class AndroidMic:
    """Real Android mic via AudioRecord. Mono 16-bit @48k."""

    def __init__(self, fs=FS):
        self.fs = fs
        self.last_error = None
        self.rec = None
        if not android_available():
            self.last_error = "pyjnius not available (desktop mode)"
            return
        try:
            from jnius import autoclass
            AudioRecord = autoclass("android.media.AudioRecord")
            MediaRecorder = autoclass("android.media.MediaRecorder")
            AudioFormat = autoclass("android.media.AudioFormat")
            CHANNEL_IN_MONO = AudioFormat.CHANNEL_IN_MONO
            ENC_PCM16 = AudioFormat.ENCODING_PCM_16BIT
            SOURCE_MIC = MediaRecorder.AudioSource.MIC
            minbuf = AudioRecord.getMinBufferSize(fs, CHANNEL_IN_MONO, ENC_PCM16)
            if minbuf <= 0:
                self.last_error = "getMinBufferSize failed"
                return
            self.rec = AudioRecord(
                SOURCE_MIC, fs, CHANNEL_IN_MONO, ENC_PCM16, max(minbuf * 4, BLOCK * 8)
            )
            if self.rec.getState() != 1:  # STATE_INITIALIZED
                self.last_error = "AudioRecord not initialized (permission?)"
                self.rec = None
                return
        except Exception as e:
            self.last_error = str(e)
            self.rec = None

    @property
    def ok(self):
        return self.rec is not None

    def start(self):
        if self.ok:
            try:
                self.rec.startRecording()
                return True
            except Exception as e:
                self.last_error = str(e)
        return False

    def read_block(self):
        """Returns int16 numpy block, or None on failure.
        Uses direct ByteBuffer (pyjnius cannot map short[] from numpy)."""
        if not self.ok:
            return None
        try:
            from jnius import autoclass
            ByteBuffer = autoclass("java.nio.ByteBuffer")
            nbytes = BLOCK * 2
            bb = ByteBuffer.allocateDirect(nbytes)
            got = self.rec.read(bb, nbytes)
            if got <= 0:
                return None
            bb.rewind()
            raw = bytearray(nbytes)
            bb.get(raw)
            return np.frombuffer(bytes(raw), dtype="<i2").copy()
        except Exception as e:
            self.last_error = str(e)
            return None

    def stop(self):
        if self.ok:
            try:
                self.rec.stop()
                self.rec.release()
            except Exception:
                pass
            self.rec = None


class AndroidSpeaker:
    """Loud playback via AudioTrack (MUSIC stream)."""

    def __init__(self, fs=FS):
        self.fs = fs
        self.last_error = None
        self.track = None
        if not android_available():
            self.last_error = "pyjnius not available (desktop mode)"
            return
        try:
            from jnius import autoclass
            AudioTrack = autoclass("android.media.AudioTrack")
            AudioManager = autoclass("android.media.AudioManager")
            AudioFormat = autoclass("android.media.AudioFormat")
            CHANNEL_OUT_MONO = AudioFormat.CHANNEL_OUT_MONO
            ENC_PCM16 = AudioFormat.ENCODING_PCM_16BIT
            STREAM_MUSIC = AudioManager.STREAM_MUSIC
            MODE_STREAM = AudioTrack.MODE_STREAM
            bufsize = max(BLOCK * 8, 8192)
            self.track = AudioTrack(
                STREAM_MUSIC, fs, CHANNEL_OUT_MONO, ENC_PCM16, bufsize, MODE_STREAM
            )
            if self.track.getState() != 1:
                self.last_error = "AudioTrack not initialized"
                self.track = None
        except Exception as e:
            self.last_error = str(e)
            self.track = None

    @property
    def ok(self):
        return self.track is not None

    def start(self):
        if self.ok:
            try:
                self.track.play()
                return True
            except Exception as e:
                self.last_error = str(e)
        return False

    def write_block(self, block_int16):
        """block_int16: numpy int16 array -> plays loud."""
        if not self.ok:
            return False
        try:
            from jnius import autoclass
            ByteBuffer = autoclass("java.nio.ByteBuffer")
            data = block_int16.tobytes()
            bb = ByteBuffer.allocateDirect(len(data))
            bb.put(bytearray(data))
            bb.rewind()
            self.track.write(bb, len(data), AudioTrackWriteMode())
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def stop(self):
        if self.ok:
            try:
                self.track.stop()
                self.track.release()
            except Exception:
                pass
            self.track = None


def AudioTrackWriteMode():
    """WRITE_BLOCKING constant."""
    if android_available():
        try:
            from jnius import autoclass
            return autoclass("android.media.AudioTrack").WRITE_BLOCKING
        except Exception:
            pass
    return 0
