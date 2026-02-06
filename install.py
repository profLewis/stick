#!/usr/bin/env python3
"""install.py -- Deploy stick firmware to Pico 2 and WAV files to SD card.

Usage:
    python install.py                  # Full install: firmware + WAV files
    python install.py --firmware-only  # Deploy firmware only (skip WAV files)
    python install.py --wav-only       # Copy WAV files to SD card only
    python install.py --sd-path /Volumes/SD  # Use physical card reader

Requirements:
    pip install mpremote
"""

import argparse
import os
import subprocess
import sys
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
SOUNDS_DIR = REPO_ROOT / "sounds_source"
SDCARD_DRIVER_URL = (
    "https://raw.githubusercontent.com/micropython/micropython-lib/"
    "master/micropython/drivers/storage/sdcard/sdcard.py"
)

FIRMWARE_FILES = [
    ("boot.py", ":boot.py"),
    ("main.py", ":main.py"),
    ("lib/notes.py", ":lib/notes.py"),
    ("lib/midi.py", ":lib/midi.py"),
    ("lib/sdcard.py", ":lib/sdcard.py"),
    ("lib/tca9548a.py", ":lib/tca9548a.py"),
]


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


def deploy_wavs_mpremote():
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

    print("  Found {} WAV files to copy".format(len(wav_files)))
    for wav in wav_files:
        remote_path = ":/sd/{}".format(wav.name)
        print("  Copying {} ...".format(wav.name), end=" ", flush=True)
        run(["mpremote", "fs", "cp", str(wav), remote_path])
        print("done")

    print("  All WAV files copied to SD card.")


def deploy_wavs_cardreader(sd_path):
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

    print("  Found {} WAV files to copy".format(len(wav_files)))
    for wav in wav_files:
        dest = sd / wav.name
        print("  Copying {} ...".format(wav.name), end=" ", flush=True)
        shutil.copy2(str(wav), str(dest))
        print("done")

    print("  All WAV files copied. Eject SD card safely before inserting in Pico.")


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
        if args.sd_path:
            deploy_wavs_cardreader(args.sd_path)
        else:
            deploy_wavs_mpremote()

    print("\nDone!")


if __name__ == "__main__":
    main()
