# config.py -- Parse sensors.cfg text file
#
# Reads sensor-to-sound mappings from /sd/sensors.cfg (SD card)
# or falls back to sensors.cfg on internal flash.

import os

# Timing (milliseconds)
TONE_DURATION_MS = 200
DEBOUNCE_MS = 50
POLL_MS = 5


def _parse_config(path):
    """Parse a sensors.cfg file into (hub_addresses, sensors) tuple."""
    hubs = set()
    sensors = []
    pin_map = {"A": 0, "a": 0, "B": 1, "b": 1}

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            hub_addr = int(parts[0], 16)
            channel = int(parts[1])
            pin_idx = pin_map.get(parts[2])
            sound = parts[3]
            if pin_idx is None:
                continue
            hubs.add(hub_addr)
            sensors.append((hub_addr, channel, pin_idx, sound))

    return sorted(hubs), sensors


# Try SD card first, then internal flash
_cfg_path = None
for p in ["/sd/sensors.cfg", "sensors.cfg"]:
    try:
        os.stat(p)
        _cfg_path = p
        break
    except OSError:
        pass

if _cfg_path:
    print("Config: {}".format(_cfg_path))
    HUB_ADDRESSES, SENSORS = _parse_config(_cfg_path)
else:
    print("Config: sensors.cfg not found, using defaults")
    HUB_ADDRESSES = [0x70]
    SENSORS = [
        (0x70, 0, 0, "C4"),
        (0x70, 0, 1, "E4"),
        (0x70, 1, 0, "G4"),
        (0x70, 1, 1, "C5"),
    ]
