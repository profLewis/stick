#!/usr/bin/env python3
"""install_sounds.py -- Deploy WAV files to Pico 2 internal flash.

Copies WAV files from sounds_source/ to /sounds_source/ on the Pico's
internal flash via mpremote.  If free space is tight, downsamples files
to fit (halve sample rate, then reduce to 8-bit, then both).

Usage:
    python install_sounds.py              # Install WAV files
    python install_sounds.py --force      # Force re-copy all files
    python install_sounds.py --list       # List WAVs on device

Requirements:
    pip install mpremote
"""

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SOUNDS_DIR = REPO_ROOT / "sounds_source"
FLASH_TARGET = "/sounds_source"
FLASH_MARGIN_KB = 20  # keep some headroom

NOTE_PATTERN = re.compile(r"^([A-G])(s?)(\d+)$")
NOTE_NAMES = ["C", "Cs", "D", "Ds", "E", "F", "Fs", "G", "Gs", "A", "As", "B"]

# Range of notes to generate (MIDI 48=C3 to MIDI 84=C6)
TARGET_OCTAVE_LOW = 3
TARGET_OCTAVE_HIGH = 6


def run(cmd, check=True):
    """Run a shell command, print it, return result."""
    print("  $ {}".format(" ".join(cmd)))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print("    {}".format(line))
    if result.returncode != 0 and check:
        print("    ERROR: {}".format(result.stderr.strip()))
        sys.exit(1)
    return result


def check_mpremote():
    if shutil.which("mpremote") is None:
        print("ERROR: mpremote not found.  pip install mpremote")
        sys.exit(1)


def query_pico(code):
    """Run MicroPython code on the Pico via mpremote exec, return stdout."""
    result = subprocess.run(
        ["mpremote", "exec", code], capture_output=True, text=True
    )
    return result.stdout.strip(), result.returncode


def get_flash_free_kb():
    """Return free KB on Pico internal flash, or None."""
    out, rc = query_pico(
        "import os\ns=os.statvfs('/')\nprint(s[0]*s[3]//1024)\n"
    )
    try:
        return int(out.split("\n")[-1].strip())
    except (ValueError, IndexError):
        return None


def get_remote_file_info(filename):
    """Get (size, first16hex, last16hex) for a file on the Pico, or None."""
    code = (
        "import os\n"
        "try:\n"
        " s=os.stat('{d}/{fn}')\n"
        " sz=s[6]\n"
        " f=open('{d}/{fn}','rb')\n"
        " first=f.read(16).hex()\n"
        " f.seek(max(0,sz-16))\n"
        " last=f.read(16).hex()\n"
        " f.close()\n"
        " print(sz,first,last)\n"
        "except:\n"
        " print('MISSING')\n"
    ).format(d=FLASH_TARGET, fn=filename)
    out, rc = query_pico(code)
    line = out.split("\n")[-1].strip()
    if "MISSING" in line or rc != 0:
        return None
    parts = line.split()
    if len(parts) == 3:
        return int(parts[0]), parts[1], parts[2]
    return None


def get_local_file_info(path):
    """Get (size, first16hex, last16hex) for a local file."""
    sz = path.stat().st_size
    with open(path, "rb") as f:
        first = f.read(16).hex()
        f.seek(max(0, sz - 16))
        last = f.read(16).hex()
    return sz, first, last


def downsample_wav(src_path, dest_path, decimate=2, eight_bit=False):
    """Downsample a WAV file to reduce size.

    decimate:  factor to reduce sample rate (1=none, 2=halve, 4=quarter)
    eight_bit: convert 16-bit to 8-bit unsigned
    """
    with wave.open(str(src_path), "rb") as src:
        params = src.getparams()
        n_frames = src.getnframes()
        raw = src.readframes(n_frames)

    n_samples = n_frames * params.nchannels
    samples = list(struct.unpack("<{}h".format(n_samples), raw))

    # Mono mixdown if stereo
    if params.nchannels == 2:
        samples = [
            (samples[i] + samples[i + 1]) // 2
            for i in range(0, len(samples), 2)
        ]

    new_rate = params.framerate
    if decimate > 1:
        samples = samples[::decimate]
        new_rate = params.framerate // decimate

    with wave.open(str(dest_path), "wb") as out:
        out.setnchannels(1)
        if eight_bit:
            out.setsampwidth(1)
            out.setframerate(new_rate)
            out.writeframes(bytes((s >> 8) + 128 for s in samples))
        else:
            out.setsampwidth(2)
            out.setframerate(new_rate)
            out.writeframes(struct.pack("<{}h".format(len(samples)), *samples))


def octave_shift_wav(src_path, dest_path, octaves):
    """Generate a WAV by shifting octaves (decimate up, duplicate down)."""
    with wave.open(str(src_path), "rb") as src:
        params = src.getparams()
        n_frames = src.getnframes()
        raw = src.readframes(n_frames)

    samples = list(struct.unpack("<{}h".format(n_frames * params.nchannels), raw))

    if octaves > 0:
        for _ in range(octaves):
            samples = samples[::2]
    elif octaves < 0:
        for _ in range(-octaves):
            expanded = []
            for s in samples:
                expanded.append(s)
                expanded.append(s)
            samples = expanded

    with wave.open(str(dest_path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(struct.pack("<{}h".format(len(samples)), *samples))


def generate_full_range():
    """Generate WAV files for all notes from octave 2-7 by shifting existing ones.

    Returns list of all WAV files (existing + generated).
    """
    existing = {p.stem: p for p in SOUNDS_DIR.glob("*.wav")}

    # Index existing notes by (name, octave)
    source_index = {}
    for stem, path in existing.items():
        m = NOTE_PATTERN.match(stem)
        if m:
            name = m.group(1) + m.group(2)  # e.g. "C", "Cs"
            octave = int(m.group(3))
            source_index.setdefault(name, []).append((octave, path))

    generated = 0
    for name in NOTE_NAMES:
        candidates = source_index.get(name, [])
        if not candidates:
            continue

        for target_oct in range(TARGET_OCTAVE_LOW, TARGET_OCTAVE_HIGH + 1):
            stem = "{}{}".format(name, target_oct)
            if stem in existing:
                continue

            # Find closest source octave
            candidates.sort(key=lambda x: abs(x[0] - target_oct))
            src_oct, src_path = candidates[0]
            shift = target_oct - src_oct

            if abs(shift) > 3:
                continue  # too far, would sound bad

            dest_path = SOUNDS_DIR / "{}.wav".format(stem)
            direction = "up" if shift > 0 else "down"
            print("  Generating {} ({} {} from {})".format(
                stem, direction, abs(shift), src_path.stem))
            octave_shift_wav(src_path, dest_path, shift)
            existing[stem] = dest_path
            generated += 1

    if generated:
        print("  Generated {} new WAV files".format(generated))
    else:
        print("  All notes already present")

    return sorted(SOUNDS_DIR.glob("*.wav"))


def pick_compression(wav_files, free_kb):
    """Decide compression level.  Returns (halve_rate, eight_bit, label) or None if no compression needed."""
    total_kb = sum(w.stat().st_size for w in wav_files) // 1024
    available = free_kb - FLASH_MARGIN_KB

    if total_kb <= available:
        return None  # no compression needed

    # Try progressively more aggressive compression
    # (decimate_factor, eight_bit, label)
    strategies = [
        (2, False, "22050Hz 16-bit (~2x)"),
        (2, True,  "22050Hz 8-bit (~4x)"),
        (4, True,  "11025Hz 8-bit (~8x)"),
        (8, True,  "5512Hz 8-bit (~16x)"),
    ]
    for decimate, eight, label in strategies:
        ratio = decimate * (2 if eight else 1)
        # Use total bytes for more accurate estimate (avoids KB rounding)
        estimated_bytes = sum(w.stat().st_size for w in wav_files) // ratio
        if estimated_bytes // 1024 <= available:
            return decimate, eight, label

    print("  ERROR: WAV files ({} KB) won't fit even at max compression ({} KB free)".format(
        total_kb, free_kb
    ))
    sys.exit(1)


def list_remote_sounds():
    """List WAV files on the Pico."""
    code = (
        "import os\n"
        "try:\n"
        " files=sorted(f for f in os.listdir('{}') if f.endswith('.wav'))\n"
        " for f in files:\n"
        "  s=os.stat('{{}}/{{}}'.format('{}',f))\n"
        "  print('  {{:>7}} B  {{}}'.format(s[6],f))\n"
        " print('{{}} WAV files'.format(len(files)))\n"
        "except OSError:\n"
        " print('No {} directory')\n"
    ).format(FLASH_TARGET, FLASH_TARGET, FLASH_TARGET)
    run(["mpremote", "exec", code])


def deploy(force=False):
    """Deploy WAV files to Pico flash."""
    print("\n== Generating missing octaves ==")
    wav_files = generate_full_range()
    if not wav_files:
        print("  No .wav files in {}".format(SOUNDS_DIR))
        sys.exit(1)

    total_kb = sum(w.stat().st_size for w in wav_files) // 1024
    free_kb = get_flash_free_kb()
    if free_kb is None:
        print("  ERROR: Could not query flash free space")
        sys.exit(1)

    print("  WAV files: {} ({} KB total)".format(len(wav_files), total_kb))
    print("  Flash free: {} KB".format(free_kb))

    compression = pick_compression(wav_files, free_kb)
    tmpdir = None
    source_files = wav_files

    if compression is not None:
        decimate, eight, label = compression
        print("  Compressing: {}".format(label))
        tmpdir = Path(tempfile.mkdtemp())
        source_files = []
        for wav in wav_files:
            dest = tmpdir / wav.name
            downsample_wav(wav, dest, decimate=decimate, eight_bit=eight)
            source_files.append(dest)
        comp_kb = sum(f.stat().st_size for f in source_files) // 1024
        print("  Compressed total: {} KB".format(comp_kb))
    else:
        print("  Enough space -- copying at full quality")

    # Create target directory on Pico
    run(["mpremote", "fs", "mkdir", ":{}".format(FLASH_TARGET)], check=False)

    copied = 0
    skipped = 0
    for src in source_files:
        remote_path = ":{}/{}".format(FLASH_TARGET, src.name)
        if not force:
            local_info = get_local_file_info(src)
            remote_info = get_remote_file_info(src.name)
            if remote_info and local_info == remote_info:
                print("  {} -- up to date".format(src.name))
                skipped += 1
                continue
        print("  Copying {} ({} KB)...".format(src.name, src.stat().st_size // 1024), end=" ", flush=True)
        run(["mpremote", "fs", "cp", str(src), remote_path])
        print("done")
        copied += 1

    if tmpdir:
        shutil.rmtree(tmpdir)

    print("\n  {} copied, {} skipped (up to date)".format(copied, skipped))


def main():
    parser = argparse.ArgumentParser(description="Install WAV files to Pico 2 flash")
    parser.add_argument("--force", action="store_true", help="Force re-copy all files")
    parser.add_argument("--list", action="store_true", help="List WAV files on device")
    args = parser.parse_args()

    print("install_sounds -- WAV files to Pico flash")
    print("  Source: {}".format(SOUNDS_DIR))
    print("  Target: {}".format(FLASH_TARGET))

    check_mpremote()

    if args.list:
        list_remote_sounds()
        return

    deploy(force=args.force)
    print("\nDone!")


if __name__ == "__main__":
    main()
