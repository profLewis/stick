# stick

Plays tones and sends MIDI when triggered by piezo sensors.

## Hardware Stack

1. **Raspberry Pi Pico 2** (RP2350) — 4 MB flash
2. **[Seengreat Pico Expansion Mini Rev 2.1](https://seengreat.com/wiki/167/pico-expansion-mini)** — buzzer, SD card, RGB LED, Grove connectors
3. **TCA9548A V1.0** — I2C multiplexer hub, used as digital signal mux for sensors
4. **Piezo A2D boards** — comparator modules with D0 digital trigger output

## Board Layout

```
  Seengreat Pico Expansion Mini Rev 2.1
  ┌─────────────────────────────────────────────────────────┐
  │                                                         │
  │  [Grove 1]     [Grove 2]     [Grove 3]                  │
  │  GP0/GP1       GP2/GP3       GP10/GP11                  │
  │  MIDI OUT      (free)        (SD card aux)              │
  │                                                         │
  │  ┌───────────────────────────────────────┐   ┌───────┐  │
  │  │                                       │   │ SD    │  │
  │  │       Raspberry Pi Pico 2             │   │ Card  │  │
  │  │           (RP2350)                    │   │ Slot  │  │
  │  │                                       │   │       │  │
  │  │  USB-C                                │   │ SPI1  │  │
  │  └───┤   ├───────────────────────────────┘   └───────┘  │
  │                                                         │
  │  [Grove 4]     [Grove 5]     [Grove 6]     🔊   🟢     │
  │  GP16/GP17     GP18/GP19     GP20/GP21     BUZ  RGB     │
  │  I2C→TCA       (buzzer)      (free)                     │
  │                                                         │
  │  [K1]  [K2]                                             │
  └─────────────────────────────────────────────────────────┘
```

## Pin Allocation

| Module | GPIOs | Connector | Notes |
|--------|-------|-----------|-------|
| MIDI Out (UART0) | GP0 TX | Grove 1 | 31250 baud, DIN-5 connector |
| SD Card (SPI1) | GP10 SCK, GP11 MOSI, GP12 MISO, GP15 CS | Built-in slot | FAT32 |
| Buzzer (PWM) | GP18 | Built-in | Passive, BUZZER_SW jumper ON |
| Audio Jack (PWM) | GP19 | Built-in | Boot tune + future audio output |
| I2C → TCA9548A | GP16 SDA, GP17 SCL | Grove 4 | Sensor hub (SoftI2C) |
| RGB LED (WS2812) | GP22 | Built-in | Status indicator |
| RTC (DS1302) | GP6, GP7, GP8 | Built-in | Not used yet |

### Available for expansion

| Grove | GPIOs | Status |
|-------|-------|--------|
| 2 | GP2, GP3 | Free |
| 6 | GP20, GP21 | Free |

### Pin conflicts

- **GP18**: shared by buzzer, audio module, and Grove 5. Only use one at a time.
- **GP10/GP11/GP15**: used by SD card SPI1. Don't use Grove 3 while SD is active.
- **GP0/GP1**: reserved for MIDI UART.
- **GP16/GP17**: reserved for I2C to TCA9548A sensor hub.

## Wiring Diagram

```
  ┌─────────────────────────────────────────────────────────────────┐
  │ Seengreat Pico Expansion Mini                                   │
  │                                                                 │
  │  Grove 1 (GP0/GP1)                                              │
  │  ├── 3.3V ──[220Ω]──→ DIN-5 Pin 4 ─┐                          │
  │  ├── GP0  ──[220Ω]──→ DIN-5 Pin 5  ├── MIDI OUT                │
  │  └── GND  ──────────→ DIN-5 Pin 2 ─┘   (to synth/player)      │
  │                                                                 │
  │  Grove 4 (GP16/GP17)                                            │
  │  ├── GP16 (SDA) ────┐                                          │
  │  ├── GP17 (SCL) ──┐ │                                          │
  │  ├── 3.3V ───────┐│ │                                          │
  │  └── GND  ──────┐││ │                                          │
  │                  ││││                                           │
  │                  ▼▼▼▼                                           │
  │           ┌──────────────┐                                      │
  │           │ TCA9548A V1.0│                                      │
  │           │  I2C Hub     │                                      │
  │           │  addr: 0x70  │                                      │
  │           ├──────────────┤                                      │
  │           │ Ch 0         │──→ SDA wire ──→ S1a D0 (active-HIGH) │
  │           │              │──→ SCL wire ──→ S1b D0              │
  │           │ Ch 1         │    (available)                       │
  │           │ Ch 2         │    (available)                       │
  │           │  ...         │                                      │
  │           │ Ch 7         │    (available)                       │
  │           └──────────────┘                                      │
  │                                                                 │
  │  Built-in                                                       │
  │  ├── Buzzer (GP18 PWM) ── BUZZER_SW jumper ON                   │
  │  ├── SD Card (SPI1)    ── FAT32 micro SD                       │
  │  └── RGB LED (GP22)    ── WS2812 status                        │
  │                                                                 │
  └─────────────────────────────────────────────────────────────────┘
```

### Sensor wiring detail

```
Piezo ──→ A2D comparator board ──→ D0 output (active-HIGH)

Channel 0:                           Channel 1:
  Sensor A D0 ──→ SDA wire             Sensor A D0 ──→ SDA wire
  Sensor B D0 ──→ SCL wire             Sensor B D0 ──→ SCL wire
         │                                    │
    TCA9548A Ch 0                        TCA9548A Ch 1
              \                           /
               ──→ TCA9548A (0x70) ←────
                        │
              SoftI2C GP16(SDA)/GP17(SCL)
                    Grove 4 on Pico
```

The TCA9548A's FET switches pass signals bidirectionally. By selecting
a channel via I2C, the Pico can read the raw D0 state on GP16/GP17.

## MIDI Out Wiring

Wire a standard [5-pin DIN MIDI connector](https://www.midi.org/specifications-old/item/midi-din-electrical-specification)
to the Grove 1 4-pin header (3.3V, GND, GP0, GP1):

```
Grove 1 3.3V --[220 ohm]--> DIN-5 Pin 4
Grove 1 GP0  --[220 ohm]--> DIN-5 Pin 5
Grove 1 GND  ─────────────→ DIN-5 Pin 2  (shield)
                              DIN-5 Pins 1, 3 --> not connected
```

Pin numbering viewed from solder side of connector. The MIDI standard uses a
5-pin DIN connector even though only 3 pins are wired. Two 220-ohm resistors
and a DIN-5 female connector are all you need.

## Sensor Configuration

Sensor-to-sound mappings are defined in `firmware/sensors.cfg`:

```
# Direct GPIO (sensors wired to Pico pins):
gpio  16  C4
gpio  17  E4

# TCA9548A hub (sensors via I2C mux):
0x70  0  A  G4
0x70  0  B  C5
```

**Direct GPIO mode:**

| Field | Description |
|-------|-------------|
| `gpio` | Keyword for direct GPIO mode |
| pin | Pico GPIO pin number |
| `sound` | Note name from `lib/notes.py` (C4-E6) |

**TCA9548A hub mode:**

| Field | Description |
|-------|-------------|
| `hub_addr` | TCA9548A I2C address (`0x70`, `0x71`, etc.) |
| `channel` | TCA9548A channel 0-7 |
| `pin` | `A` = SDA wire (sensor A), `B` = SCL wire (sensor B) |
| `sound` | Note name from `lib/notes.py` (C4-E6) |

The config is loaded from `/sd/sensors.cfg` on the SD card first, falling back
to `sensors.cfg` on internal flash. Lines starting with `#` are comments.

### Sensors

Piezo sensors with A2D comparator boards (GND, VCC, AD0, D0). D0 is
**active-HIGH**: normally LOW, goes HIGH on hit.

**Important:** At 3.3V, these A2D boards need a **~10K pull-down resistor**
between D0 and GND. Without it, D0 floats HIGH and won't trigger correctly.
The boards are designed for 5V; at 3.3V the comparator threshold is marginal.

Sensors can be wired directly to GPIO pins (simplest) or through a TCA9548A
I2C multiplexer for more channels.

Rising-edge detection with 50ms debounce. On boot, a status report shows all
configured sensors and their current state (IDLE/TRIGGERED).

### Adding more sensors

Each TCA9548A has 8 channels x 2 wires = 16 sensors. Supports daisy-chaining
**2 hubs** on the same I2C bus for up to **32 sensors**.

To add a sensor pair on the first hub:

1. Connect sensor A D0 → SDA wire on a new TCA channel
2. Connect sensor B D0 → SCL wire on the same channel
3. Add entries to `firmware/sensors.cfg`:
   ```
   0x70  2  A  E5
   0x70  2  B  G5
   ```
4. Redeploy: `python install.py --firmware-only`

### Daisy-chaining a second hub

1. Set A0 HIGH on the second TCA9548A board (address becomes 0x71).
   Most TCA9548A boards have solder jumper pads for A0/A1/A2 — bridge the
   A0 pad with a blob of solder. See your board's datasheet for the exact
   pad location. ([TCA9548A datasheet](https://www.ti.com/lit/ds/symlink/tca9548a.pdf), section 9.3.1)
2. Connect SDA/SCL/VCC/GND in parallel with the first hub
3. Add entries to `firmware/sensors.cfg`:
   ```
   0x71  0  A  A4
   0x71  0  B  B4
   ```
4. Redeploy: `python install.py --firmware-only`

## Disk Space

- **Internal flash**: 4 MB total, ~2.8 MB usable with MicroPython
- **SD card**: depends on card (typically 2-32 GB)
- **WAV files**: 29 files, ~12 MB total (stored on SD card)

`boot.py` prints exact flash and SD free space on every startup.

Check space any time with:
```
python install.py --disk-space
```

## File Layout

```
stick/
  install.py              # Host-side deploy script (macOS, uses mpremote)
  sounds_source/*.wav     # 29 WAV files (C4-E6, 16-bit mono 44100 Hz)
  firmware/               # MicroPython code deployed to Pico
    boot.py               #   Mounts SD card, reports disk space, boot tune
    main.py               #   Sensor loop, buzzer PWM, MIDI out
    config.py             #   Parses sensors.cfg into runtime config
    sensors.cfg           #   Sensor-to-sound mappings (text file)
    lib/
      notes.py            #   Note name -> frequency + MIDI number
      midi.py             #   MidiOut class (UART 31250 baud)
      tca9548a.py         #   TCA9548A I2C mux driver
      sdcard.py           #   micropython-lib SD driver (auto-downloaded)
  archive/
    main_i2s.py           # Old I2S firmware (Waveshare Audio HAT)
```

## Installation

Requires MicroPython on the Pico 2 and `mpremote` on the host:

```bash
pip install mpremote
```

### Full install (firmware + WAV files to SD card)

```bash
python install.py
```

### Firmware only (fast, for code iterations)

```bash
python install.py --firmware-only
```

### WAV files only

```bash
python install.py --wav-only
```

### Force re-copy all WAV files

```bash
python install.py --wav-only --force
```

By default, WAV files are skipped if they already exist on the SD card with
the same size and matching first/last bytes. Use `--force` to overwrite all.

### Loading files via SD card reader

If you have a USB card reader (or a built-in SD slot on your computer), you
can copy files directly to the SD card — much faster than transferring through
the Pico. Insert the micro SD card into your reader and either:

**Drag and drop** in Finder/Explorer: open the SD card volume and drag the
WAV files from `sounds_source/` and `firmware/sensors.cfg` onto it.

**From the command line:**

```bash
# Via install script (validates files and skips duplicates):
python install.py --sd-path /Volumes/SD

# Or copy manually (macOS example):
cp sounds_source/*.wav /Volumes/SD/
cp firmware/sensors.cfg /Volumes/SD/
```

Eject the SD card safely before removing it. The Pico reads `sensors.cfg`
from the SD card first (`/sd/sensors.cfg`), falling back to the copy on
internal flash.

### Missing WAV files

The install script checks that every sound referenced in `sensors.cfg` has a
matching WAV file. If a note is missing (e.g. `C3.wav`), it will try to
generate one by octave-shifting from an existing file (e.g. `C4.wav`).
Generated files are named with a `_synth` suffix (e.g. `C3_synth.wav`).

## Boot Tune

On every power-up, after mounting the SD card, the Pico plays a tune through
both the **buzzer** (GP18) and the **audio jack** (GP19). Three tunes are
available: **Tetris** (Korobeiniki), **In the Mood** (Glenn Miller), and
**Star Wars** (Main Theme). By default one is chosen at random.

To set a specific tune, add to `sensors.cfg`:
```
boot_tune  tetris
```
Options: `tetris`, `mood`, `starwars`, `random` (default).

Boot tune melodies are derived from MIDI files on
[midis101.com](https://www.midis101.com).

## Jumper Settings

- **BUZZER_SW**: ON (connect jumper cap)
- **Grove VCC**: 3.3V
