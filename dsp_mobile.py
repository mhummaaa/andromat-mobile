"""
================================================================
 ANDROMAT MOBILE - v8 LOUD DSP ENGINE (Pure NumPy, Android-safe)
================================================================
SciPy Android par heavy hai isliye poora engine pure NumPy +
Python se likha gaya hai. Same philosophy as desktop v8:

    mic -> HP filter -> presence boost -> compressor (SLAM)
        -> AGC (auto gain to target) -> soft limiter -> out

Modes: VOICE SLAM / MAXIMIZE / NUKE / GODMODE
Sample format: float32 mono, 48000 Hz (Android native).
No silent failures: every error is reported via last_error.
================================================================
"""
import math
import numpy as np


# ----------------------------------------------------------------
# Biquad IIR filter (RBJ cookbook) - sample by sample DF1
# ----------------------------------------------------------------
class Biquad:
    def __init__(self, fs, f0, q=0.707, kind="peak", gain_db=0.0):
        self.fs = fs
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * min(f0, fs * 0.45) / fs
        cw = math.cos(w0)
        sw = math.sin(w0)
        alpha = sw / (2.0 * q)

        if kind == "peak":
            b0 = 1 + alpha * A
            b1 = -2 * cw
            b2 = 1 - alpha * A
            a0 = 1 + alpha / A
            a1 = -2 * cw
            a2 = 1 - alpha / A
        elif kind == "highpass":
            b0 = (1 + cw) / 2
            b1 = -(1 + cw)
            b2 = (1 + cw) / 2
            a0 = 1 + alpha
            a1 = -2 * cw
            a2 = 1 - alpha
        elif kind == "lowpass":
            b0 = (1 - cw) / 2
            b1 = (1 - cw)
            b2 = (1 - cw) / 2
            a0 = 1 + alpha
            a1 = -2 * cw
            a2 = 1 - alpha
        elif kind == "lowshelf":
            sqA = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) - (A - 1) * cw + sqA)
            b1 = 2 * A * ((A - 1) - (A + 1) * cw)
            b2 = A * ((A + 1) - (A - 1) * cw - sqA)
            a0 = (A + 1) + (A - 1) * cw + sqA
            a1 = -2 * ((A - 1) + (A + 1) * cw)
            a2 = (A + 1) + (A - 1) * cw - sqA
        elif kind == "highshelf":
            sqA = 2.0 * math.sqrt(A) * alpha
            b0 = A * ((A + 1) + (A - 1) * cw + sqA)
            b1 = -2 * A * ((A - 1) + (A + 1) * cw)
            b2 = A * ((A + 1) + (A - 1) * cw - sqA)
            a0 = (A + 1) - (A - 1) * cw + sqA
            a1 = 2 * ((A - 1) - (A + 1) * cw)
            a2 = (A + 1) - (A - 1) * cw - sqA
        else:  # allpass fallback
            b0, b1, b2 = 1, 0, 0
            a0, a1, a2 = 1, 0, 0

        # normalize
        self.b0 = b0 / a0
        self.b1 = b1 / a0
        self.b2 = b2 / a0
        self.a1 = a1 / a0
        self.a2 = a2 / a0
        self.z1 = 0.0
        self.z2 = 0.0

    def process(self, x):
        """x: 1-D numpy float32 array, returns filtered array."""
        b0 = self.b0; b1 = self.b1; b2 = self.b2
        a1 = self.a1; a2 = self.a2
        z1 = self.z1; z2 = self.z2
        out = np.empty_like(x)
        for i in range(x.shape[0]):
            xn = x[i]
            yn = b0 * xn + z1
            z1 = b1 * xn - a1 * yn + z2
            z2 = b2 * xn - a2 * yn
            out[i] = yn
        self.z1 = z1
        self.z2 = z2
        return out


# ----------------------------------------------------------------
# Mobile DSP engine
# ----------------------------------------------------------------
MODES = ("VOICE SLAM", "MAXIMIZE", "NUKE", "GODMODE")

# mode -> (comp_ratio, comp_thresh, agc_target_db, max_gain_db, drive)
MODE_PARAMS = {
    "VOICE SLAM": (3.0, -26.0, -12.0, 30.0, 1.0),
    "MAXIMIZE":   (4.0, -22.0, -10.0, 36.0, 1.2),
    "NUKE":       (8.0, -28.0, -8.0,  42.0, 1.5),
    "GODMODE":    (10.0, -30.0, -6.0, 48.0, 1.8),
}


class MobileDSP:
    """One instance = one continuous stream. Call .process(block)."""

    def __init__(self, fs=48000, mode="VOICE SLAM", gain_db=12.0,
                 presence_db=8.0, receive_boost_db=0.0):
        self.fs = fs
        self.mode = mode
        self.gain_db = gain_db
        self.presence_db = presence_db
        self.receive_boost_db = receive_boost_db
        self.last_error = None
        self._agc_gain = 1.0
        self._env = 0.0
        self._build_chain()

    def _build_chain(self):
        fs = self.fs
        self.hp = Biquad(fs, 65, 0.707, "highpass")
        self.presence = Biquad(fs, 2800, 0.9, "peak", self.presence_db)
        self.air = Biquad(fs, 8000, 0.707, "highshelf", min(3.0, self.presence_db * 0.4))
        self.mud = Biquad(fs, 500, 1.0, "peak", -2.5)

    def set_mode(self, mode):
        if mode in MODE_PARAMS:
            self.mode = mode

    def _compress_block(self, x, ratio, thresh_db, attack_ms, release_ms):
        """Per-sample envelope compressor (RMS-ish peak follower)."""
        a_att = math.exp(-1.0 / (self.fs * attack_ms / 1000.0))
        a_rel = math.exp(-1.0 / (self.fs * release_ms / 1000.0))
        env = self._env
        out = np.empty_like(x)
        thresh = 10.0 ** (thresh_db / 20.0)
        slope = 1.0 - 1.0 / ratio
        for i in range(x.shape[0]):
            ax = x[i]
            if ax < 0:
                ax = -ax
            if ax > env:
                env = a_att * env + (1 - a_att) * ax
            else:
                env = a_rel * env + (1 - a_rel) * ax
            if env > thresh:
                g = (thresh + (env - thresh) * (1 - slope)) / env
            else:
                g = 1.0
            out[i] = x[i] * g
        self._env = env
        return out

    def _agc_block(self, x, target_db, max_gain_db):
        """Slow block-RMS auto gain toward target, smoothed."""
        rms = float(np.sqrt(np.mean(np.square(x)) + 1e-12))
        if rms < 1e-6:
            return x  # silence: don't pump noise
        cur_db = 20.0 * math.log10(rms)
        want = target_db - cur_db
        want_gain = min(10.0 ** (want / 20.0), 10.0 ** (max_gain_db / 20.0))
        # smooth 30% per block
        self._agc_gain = self._agc_gain * 0.7 + want_gain * 0.3
        return x * self._agc_gain

    def process(self, block):
        """block: int16 numpy array -> processed int16 numpy array."""
        try:
            x = block.astype(np.float32) / 32768.0
            ratio, thresh, target, maxg, drive = MODE_PARAMS[self.mode]
            x = self.hp.process(x)
            x = self.mud.process(x)
            x = self.presence.process(x)
            x = self.air.process(x)
            x = self._compress_block(x, ratio, thresh, 8.0, 120.0)
            x = self._agc_block(x, target, maxg)
            x = x * (10.0 ** (self.gain_db / 20.0)) * drive
            # soft ceiling limiter
            x = np.tanh(x * 0.9) / 0.9
            x = np.clip(x, -0.98, 0.98)
            return (x * 32767.0).astype(np.int16)
        except Exception as e:
            self.last_error = str(e)
            return block

    def process_receive(self, block):
        """Incoming audio: just boost + protect."""
        try:
            x = block.astype(np.float32) / 32768.0
            x = x * (10.0 ** (self.receive_boost_db / 20.0))
            x = np.tanh(x * 0.95) / 0.95
            return (np.clip(x, -0.98, 0.98) * 32767.0).astype(np.int16)
        except Exception as e:
            self.last_error = str(e)
            return block
