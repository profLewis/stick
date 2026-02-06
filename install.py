#!/usr/bin/env python3
"""install.py -- Deploy stick firmware to Pico 2 and WAV files to SD card.

Usage:
    python install.py                  # Full install: firmware + WAV files
    python install.py --firmware-only  # Deploy firmware only (skip WAV files)
    python install.py --wav-only       # Copy WAV files to SD card only
    python install.py --force          # Force re-copy all WAV files
    python install.py --sd-path /Volumes/SD  # Use physical card reader

Requirements:
    pip install mpremote
"""

import argparse
import os
import re
import struct
import subprocess
import sys
import shutil
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
SOUNDS_DIR = REPO_ROOT / "sounds_source"
SDCARD_DRIVER_URL = (
    "https://raw.githubusercontent.com/micropython/micropython-lib/"
    "master/micropython/drivers/storage/sdcard/sdcard.py"
)
NOTE_PATTERN = re.compile(r"^([A-G])(s?)(\d+)$")

FIRMWARE_FILES = [
    ("boot.py", ":boot.py"),
    ("main.py", ":main.py"),
    ("config.py", ":config.py"),
    ("sensors.cfg", ":sensors.cfg"),
    ("lib/notes.py", ":lib/notes.py"),
    ("lib/midi.py", ":lib/midi.py"),
    ("lib/sdcard.py", ":lib/sdcard.py"),
    ("lib/tca9548a.py", ":lib/tca9548a.py"),
]


def parse_note_name(name):
    """Parse 'C4', 'Cs5', 'Fs6' into (letter, sharp, octave) or None."""
    m = NOTE_PATTERN.match(name)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    return None


def parse_sensor_config(cfg_path):
    """Parse sensors.cfg and return list of referenced sound names."""
    sounds = []
    with open(cfg_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                sounds.append(parts[3])
    return sounds


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

    direction = "up" if octaves > 0 else "down"
    print(
        "  Generated {} ({} {} octave(s) from {})".format(
            dest_path.name, direction, abs(octaves), src_path.name
        )
    )


def generate_missing_wavs():
    """Generate WAV files for notes in sensors.cfg missing from sounds_source.

    Returns set of all available WAV stems after generation.
    """
    cfg_path = FIRMWARE_DIR / "sensors.cfg"
    existing_stems = {p.stem for p in SOUNDS_DIR.glob("*.wav")}

    if not cfg_path.exists():
        return existing_stems

    referenced = parse_sensor_config(cfg_path)

    # Build index: (letter, sharp) -> [(octave, stem)]
    source_index = {}
    for stem in existing_stems:
        parsed = parse_note_name(stem)
        if parsed:
            letter, sharp, octave = parsed
            source_index.setdefault((letter, sharp), []).append((octave, stem))

    generated = set()
    for sound in referenced:
        if sound in existing_stems or sound + "_synth" in existing_stems:
            continue

        parsed = parse_note_name(sound)
        if not parsed:
            continue

        letter, sharp, target_octave = parsed
        candidates = source_index.get((letter, sharp), [])
        if not candidates:
            print(
                "  WARNING: No source for note '{}{}'".format(
                    letter, "#" if sharp else ""
                )
            )
            continue

        candidates.sort(key=lambda x: abs(x[0] - target_octave))
        src_octave, src_stem = candidates[0]
        shift = target_octave - src_octave

        src_path = SOUNDS_DIR / "{}.wav".format(src_stem)
        dest_path = SOUNDS_DIR / "{}_synth.wav".format(sound)
        octave_shift_wav(src_path, dest_path, shift)
        generated.add(sound + "_synth")

    if generated:
        print("  Generated {} synth WAV file(s)".format(len(generated)))

    return existing_stems | generated


def validate_sounds(available_wavs):
    """Check that every sound in sensors.cfg has a WAV file."""
    cfg_path = FIRMWARE_DIR / "sensors.cfg"
    if not cfg_path.exists():
        return

    referenced = parse_sensor_config(cfg_path)
    present = []
    synth = []
    missing = []

    for sound in referenced:
        if sound in available_wavs:
            present.append(sound)
        elif sound + "_synth" in available_wavs:
            synth.append(sound)
        else:
            missing.append(sound)

    print("\n== Sound file validation ==")
    print("  sensors.cfg references {} sounds".format(len(referenced)))
    if present:
        print("  OK:      {} ({})".format(len(present), ", ".join(present)))
    if synth:
        print("  Synth:   {} ({})".format(len(synth), ", ".join(synth)))
    if missing:
        print("  MISSING: {} ({})".format(len(missing), ", ".join(missing)))
    if not missing:
        print("  All sounds accounted for.")


def run(cmd, check=True):
    """Run a command, printing it first."""
    print("  $ {}".format(" ".join(cmd)))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print("    {}".format(result.stdout.strip()))
    if result.returncode != 0 and check:
        print("    ERROR: {}".format(result.stderr.strip()))
        sys.exit(1)
    return result


def check_mpremote():
    """Verify mpremote is installed."""
    if shutil.which("mpremote") is None:
        print("ERROR: mpremote not found. Install with:")
        print("  pip install mpremote")
        sys.exit(1)


def ensure_sdcard_driver():
    """Download sdcard.py if not present."""
    target = FIRMWARE_DIR / "lib" / "sdcard.py"
    if target.exists():
        print("  sdcard.py already present")
        return
    print("  Downloading sdcard.py from micropython-lib...")
    import urllib.request

    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SDCARD_DRIVER_URL, str(target))
    print("  Saved to {}".format(target))


def deploy_firmware():
    """Deploy firmware files to Pico via mpremote."""
    print("\n== Deploying firmware to Pico ==")
    check_mpremote()
    ensure_sdcard_driver()

    # Create lib directory on Pico
    run(["mpremote", "fs", "mkdir", ":lib"], check=False)

    for local_rel, remote in FIRMWARE_FILES:
        local_path = str(FIRMWARE_DIR / local_rel)
        if not os.path.exists(local_path):
            print("  WARNING: {} not found, skipping".format(local_path))
            continue
        run(["mpremote", "fs", "cp", local_path, remote])

    print("  Firmware deployed. Reset Pico to start.")


def _get_remote_file_info(filename):
    """Get size and first/last 16 bytes of a file on the SD card.

    Returns (size, first_bytes_hex, last_bytes_hex) or None if file missing.
    """
    code = (
        "import os\n"
        "try:\n"
        " s=os.stat('/sd/{fn}')\n"
        " sz=s[6]\n"
        " f=open('/sd/{fn}','rb')\n"
        " first=f.read(16).hex()\n"
        " f.seek(max(0,sz-16))\n"
        " last=f.read(16).hex()\n"
        " f.close()\n"
        " print(sz,first,last)\n"
        "except:\n"
        " print('MISSING')\n"
    ).format(fn=filename)
    result = subprocess.run(
        ["mpremote", "exec", code], capture_output=True, text=True
    )
    output = result.stdout.strip().split("\n")[-1].strip()
    if "MISSING" in output or result.returncode != 0:
        return None
    parts = output.split()
    if len(parts) == 3:
        return int(parts[0]), parts[1], parts[2]
    return None


def _get_local_file_info(path):
    """Get size and first/last 16 bytes of a local file."""
    sz = path.stat().st_size
    with open(path, "rb") as f:
        first = f.read(16).hex()
        f.seek(max(0, sz - 16))
        last = f.read(16).hex()
    return sz, first, last


def deploy_wavs_mpremote(force=False):
    """Copy WAV files to SD card via mpremote (through the Pico)."""
    print("\n== Copying WAV files to SD card via mpremote ==")
    check_mpremote()

    # Verify SD is mounted by listing /sd
    result = run(["mpremote", "fs", "ls", ":/sd"], check=False)
    if result.returncode != 0:
        print("  ERROR: SD card not mounted at /sd on Pico.")
        print("  Make sure SD card is inserted and boot.py has run.")
        print("  Try: mpremote soft-reset")
        sys.exit(1)

    wav_files = sorted(SOUNDS_DIR.glob("*.wav"))
    if not wav_files:
        print("  No .wav files found in {}".format(SOUNDS_DIR))
        sys.exit(1)

    print("  Found {} WAV files to sync".format(len(wav_files)))
    copied = 0
    skipped = 0

    for wav in wav_files:
        remote_path = ":/sd/{}".format(wav.name)

        if not force:
            local_info = _get_local_file_info(wav)
            remote_info = _get_remote_file_info(wav.name)
            if remote_info and local_info == remote_info:
                print("  {} -- up to date, skipping".format(wav.name))
                skipped += 1
                continue

        print("  Copying {} ...".format(wav.name), end=" ", flush=True)
        run(["mpremote", "fs", "cp", str(wav), remote_path])
        print("done")
        copied += 1

    print("  {} copied, {} skipped (up to date).".format(copied, skipped))

    # Deploy sensors.cfg to SD card
    cfg_src = str(FIRMWARE_DIR / "sensors.cfg")
    if os.path.exists(cfg_src):
        print("  Copying sensors.cfg to SD card ...", end=" ", flush=True)
        run(["mpremote", "fs", "cp", cfg_src, ":/sd/sensors.cfg"])
        print("done")


def deploy_wavs_cardreader(sd_path, force=False):
    """Copy WAV files directly to SD card via physical card reader."""
    print("\n== Copying WAV files to SD card at {} ==".format(sd_path))
    sd = Path(sd_path)
    if not sd.is_dir():
        print("  ERROR: {} is not a valid directory".format(sd_path))
        sys.exit(1)

    wav_files = sorted(SOUNDS_DIR.glob("*.wav"))
    if not wav_files:
        print("  No .wav files found in {}".format(SOUNDS_DIR))
        sys.exit(1)

    print("  Found {} WAV files to sync".format(len(wav_files)))
    copied = 0
    skipped = 0

    for wav in wav_files:
        dest = sd / wav.name
        if not force and dest.exists():
            local_info = _get_local_file_info(wav)
            remote_sz = dest.stat().st_size
            with open(dest, "rb") as f:
                remote_first = f.read(16).hex()
                f.seek(max(0, remote_sz - 16))
                remote_last = f.read(16).hex()
            if local_info == (remote_sz, remote_first, remote_last):
                print("  {} -- up to date, skipping".format(wav.name))
                skipped += 1
                continue

        print("  Copying {} ...".format(wav.name), end=" ", flush=True)
        shutil.copy2(str(wav), str(dest))
        print("done")
        copied += 1

    print("  {} copied, {} skipped (up to date).".format(copied, skipped))

    # Deploy sensors.cfg to SD card
    cfg_src = FIRMWARE_DIR / "sensors.cfg"
    if cfg_src.exists():
        cfg_dest = sd / "sensors.cfg"
        print("  Copying sensors.cfg to SD card ...", end=" ", flush=True)
        shutil.copy2(str(cfg_src), str(cfg_dest))
        print("done")

    if copied:
        print("  Eject SD card safely before inserting in Pico.")


def check_disk_space():
    """Query and display Pico internal flash and SD card space."""
    print("\n== Checking disk space ==")
    check_mpremote()
    code = (
        "import os\n"
        "def di(p):\n"
        " s=os.statvfs(p);return(s[0]*s[2]//1024,s[0]*s[3]//1024)\n"
        "t,f=di('/');print('Flash: {} KB total, {} KB free'.format(t,f))\n"
        "try:\n"
        " t,f=di('/sd');print('SD:    {} KB total, {} KB free'.format(t,f))\n"
        "except:\n"
        " print('SD:    not mounted')\n"
    )
    run(["mpremote", "exec", code])


def main():
    parser = argparse.ArgumentParser(description="Deploy stick to Pico 2")
    parser.add_argument(
        "--firmware-only",
        action="store_true",
        help="Deploy firmware only, skip WAV files",
    )
    parser.add_argument(
        "--wav-only",
        action="store_true",
        help="Copy WAV files only, skip firmware",
    )
    parser.add_argument(
        "--sd-path",
        type=str,
        default=None,
        help="Path to mounted SD card (e.g., /Volumes/SD). "
        "If not set, copies via mpremote through Pico.",
    )
    parser.add_argument(
        "--disk-space",
        action="store_true",
        help="Just check and report disk space on Pico and SD card",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force copy all WAV files even if already up to date",
    )
    args = parser.parse_args()

    print("stick installer")
    print("  Firmware: {}".format(FIRMWARE_DIR))
    print("  Sounds:   {}".format(SOUNDS_DIR))

    if args.disk_space:
        check_disk_space()
        return

    if not args.wav_only:
        deploy_firmware()

    if not args.firmware_only:
        # Generate any missing WAV files before deploying
        available_wavs = generate_missing_wavs()

        if args.sd_path:
            deploy_wavs_cardreader(args.sd_path, force=args.force)
        else:
            deploy_wavs_mpremote(force=args.force)

        # Validate all referenced sounds have WAV files
        validate_sounds(available_wavs)

    print("\nDone!")


if __name__ == "__main__":
    main()
