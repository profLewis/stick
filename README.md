# stick

Plays tones and sends MIDI when triggered by piezo sensors.

## Hardware Stack

1. **Raspberry Pi Pico 2** (RP2350) — 4 MB flash
2. **[Seengreat Pico Expansion Mini Rev 2.1](https://seengreat.com/wiki/167/pico-expansion-mini)** — buzzer, SD card, RGB LED, Grove connectors

## Pin Allocation

| Module | GPIOs | Notes |
|--------|-------|-------|
| Buzzer (PWM) | GP18 | Passive buzzer, BUZZER_SW jumper ON |
| SD Card (SPI1) | GP14 SCK, GP15 MOSI, GP12 MISO, GP13 CS | FAT32 formatted |
| RGB LED (WS2812) | GP22 | Status indicator |
| MIDI Out (UART0) | GP0 TX | Grove 1, 31250 baud |
| Piezo S1a | GP16 | Grove 4 pin 1 |
| Piezo S1b | GP17 | Grove 4 pin 2 |
| RTC (DS1302) | GP6, GP7, GP8 | Not used yet |

### Available for expansion

| Grove | GPIOs | Use |
|-------|-------|-----|
| 2 | GP2, GP3 | Sensors or I2C |
| 6 | GP20, GP21 | Sensors |

Up to 4 more digital triggers (2 more sensor pairs).

### Pin conflicts

- GP18: shared by buzzer, audio module, and Grove 5. Only use one at a time.
- GP10/GP11: shared by SD card block and Grove 3. Don't use Grove 3 while SD is active.
- GP0/GP1: reserved for MIDI UART.

## MIDI Out Wiring

Connect a 5-pin DIN connector to Grove 1 (GP0/GP1/3.3V/GND):

```
Pico 3.3V --[220 ohm]--> DIN-5 Pin 4
Pico GP0  --[220 ohm]--> DIN-5 Pin 5
                          DIN-5 Pin 2 --> GND (shield)
                          DIN-5 Pins 1, 3 --> not connected
```

Pin numbering viewed from solder side of connector. Two 220-ohm resistors and a DIN-5 female connector are all you need.

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
    boot.py               #   Mounts SD card, reports disk space
    main.py               #   Sensor loop, buzzer PWM, MIDI out
    lib/
      notes.py            #   Note name -> frequency + MIDI number
      midi.py             #   MidiOut class (UART 31250 baud)
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

### With physical card reader (faster for WAV files)

```bash
python install.py --sd-path /Volumes/SD
```

## Jumper Settings

- **BUZZER_SW**: ON (connect jumper cap)
- **Grove VCC**: 3.3V

## Sensors

Piezo sensors with digital trigger output, wired in pairs:

| Sensor | GPIO | Default Note |
|--------|------|-------------|
| S1a | GP16 | A4 (440 Hz) |
| S1b | GP17 | C5 (523 Hz) |

Edit `SENSOR_MAP` in `firmware/main.py` to change note assignments.

Uses rising-edge detection with pull-down resistors and 50ms debounce.
