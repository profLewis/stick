# i2s_midi.py -- MIDI-triggered WAV playback via I2S
#
# Hardware: RPi Pico 2 + Waveshare Pico Audio (PCM5101A)
#
# I2S pins (directly wired on the Pico Audio board):
#   DIN  = GP26  (serial data)
#   BCK  = GP27  (bit clock)       -- I2S sck
#   LRCK = GP28  (word select)     -- I2S ws  (must be sck+1 on RP2)
#
# MIDI input: UART0 RX = GP1, 31250 baud
# MIDI output: UART0 TX = GP0 (optional thru)

import machine
import struct
import time
import os

# ---------- Pin configuration ----------
PIN_I2S_SD  = 26   # DIN  (serial data out)
PIN_I2S_SCK = 27   # BCK  (bit clock)
PIN_I2S_WS  = 28   # LRCK (word select)

MIDI_UART   = 0
PIN_MIDI_RX = 1
PIN_MIDI_TX = 0

SOUNDS_DIR  = "/sounds_source"
I2S_BUF     = 4096   # internal I2S ring buffer
CHUNK       = 1024   # read chunk size

# ---------- Note name table ----------
_NAMES = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]


def midi_to_path(note):
    """MIDI note number -> WAV path  (60 = C4.wav, 61 = Cs4.wav, ...)"""
    octave = (note // 12) - 1
    return "{}/{}{}.wav".format(SOUNDS_DIR, _NAMES[note % 12], octave)


def parse_wav_header(f):
    """Read WAV header from an open file.

    Returns (channels, sampwidth_bytes, framerate, data_size)
    and leaves the file positioned at the start of audio data.
    Returns None on bad header.
    """
    hdr = f.read(12)
    if len(hdr) < 12 or hdr[:4] != b'RIFF' or hdr[8:12] != b'WAVE':
        return None

    fmt_info = None
    while True:
        chunk_hdr = f.read(8)
        if len(chunk_hdr) < 8:
            break
        cid = chunk_hdr[:4]
        csz = struct.unpack('<I', chunk_hdr[4:8])[0]

        if cid == b'fmt ':
            fmt = f.read(csz)
            channels  = struct.unpack('<H', fmt[2:4])[0]
            framerate = struct.unpack('<I', fmt[4:8])[0]
            sampwidth = struct.unpack('<H', fmt[14:16])[0] // 8
            fmt_info = (channels, sampwidth, framerate)
        elif cid == b'data':
            if fmt_info is None:
                return None
            return fmt_info[0], fmt_info[1], fmt_info[2], csz
        else:
            f.seek(csz, 1)

    return None


class Player:
    def __init__(self):
        # Detect audio format from the first WAV on flash
        self.sample_rate = 44100
        self.sampwidth = 2
        self._detect_format()

        # I2S output (PCM5101A -- no MCLK needed)
        self.audio = machine.I2S(
            0,
            sck=machine.Pin(PIN_I2S_SCK),
            ws=machine.Pin(PIN_I2S_WS),
            sd=machine.Pin(PIN_I2S_SD),
            mode=machine.I2S.TX,
            bits=16,
            format=machine.I2S.MONO,
            rate=self.sample_rate,
            ibuf=I2S_BUF,
        )
        print("  I2S  DIN=GP{} BCK=GP{} LRCK=GP{}  {}Hz 16-bit mono".format(
            PIN_I2S_SD, PIN_I2S_SCK, PIN_I2S_WS, self.sample_rate))

        # MIDI UART
        self.uart = machine.UART(
            MIDI_UART, baudrate=31250,
            tx=machine.Pin(PIN_MIDI_TX),
            rx=machine.Pin(PIN_MIDI_RX),
            timeout=10,
        )
        print("  MIDI UART{} RX=GP{} TX=GP{}".format(
            MIDI_UART, PIN_MIDI_RX, PIN_MIDI_TX))

        # Buffers
        self.buf = bytearray(CHUNK)
        self.buf16 = bytearray(CHUNK * 2)  # for 8-bit -> 16-bit expansion

        # Silence to flush I2S pipeline
        self.silence = bytearray(512)

    def _detect_format(self):
        """Read format from the first WAV file found."""
        try:
            for fn in os.listdir(SOUNDS_DIR):
                if fn.endswith(".wav"):
                    with open("{}/{}".format(SOUNDS_DIR, fn), "rb") as f:
                        info = parse_wav_header(f)
                    if info:
                        _, self.sampwidth, self.sample_rate, _ = info
                        print("  Format: {}Hz {}-bit".format(
                            self.sample_rate, self.sampwidth * 8))
                        return
        except OSError:
            pass
        print("  No WAVs found, defaults: {}Hz {}-bit".format(
            self.sample_rate, self.sampwidth * 8))

    def play(self, path):
        """Stream a WAV file to I2S.  Aborts early if new MIDI arrives."""
        try:
            f = open(path, "rb")
        except OSError:
            return

        info = parse_wav_header(f)
        if info is None:
            f.close()
            return

        _ch, sw, _rate, data_size = info
        remaining = data_size
        is_8bit = (sw == 1)

        while remaining > 0:
            # Let new notes interrupt the current one
            if self.uart.any():
                break

            n = f.readinto(self.buf, min(CHUNK, remaining))
            if n == 0:
                break

            if is_8bit:
                # Unsigned 8-bit -> signed 16-bit
                for i in range(n):
                    val = (self.buf[i] - 128) << 8
                    self.buf16[i * 2] = val & 0xFF
                    self.buf16[i * 2 + 1] = (val >> 8) & 0xFF
                self.audio.write(self.buf16[:n * 2])
            else:
                self.audio.write(self.buf[:n])

            remaining -= n

        # Flush a little silence so the last samples get clocked out
        self.audio.write(self.silence)
        f.close()

    def run(self):
        """Main loop: read MIDI, play WAVs."""
        print("\nReady -- send MIDI notes!")
        status = 0  # running status

        while True:
            if not self.uart.any():
                time.sleep_ms(1)
                continue

            b = self.uart.read(1)
            if b is None:
                continue
            b = b[0]

            if b & 0x80:
                # Status byte
                status = b
                data1 = self.uart.read(1)
                if data1 is None:
                    continue
                data1 = data1[0] & 0x7F
            else:
                # Running status: b is first data byte
                data1 = b & 0x7F

            msg = status & 0xF0

            if msg in (0x90, 0x80, 0xA0, 0xB0, 0xE0):
                # Two data-byte messages
                data2 = self.uart.read(1)
                if data2 is None:
                    continue
                data2 = data2[0] & 0x7F

                if msg == 0x90 and data2 > 0:
                    # Note On with velocity
                    path = midi_to_path(data1)
                    print("Note {} -> {}".format(data1, path))
                    self.play(path)

            elif msg in (0xC0, 0xD0):
                pass  # one data byte already consumed

            elif status == 0xF0:
                # SysEx: skip until F7
                while True:
                    sx = self.uart.read(1)
                    if sx is None or sx[0] == 0xF7:
                        break


# ---------- Entry point ----------
print("i2s_midi -- MIDI WAV player")
print("Waveshare Pico Audio (PCM5101A)\n")

player = Player()
player.run()
