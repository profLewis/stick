# stick

Plays tones and sends MIDI when triggered by piezo sensors.

## Hardware Stack

1. **Raspberry Pi Pico 2** (RP2350) — 4 MB flash
2. **[Seengreat Pico Expansion Mini Rev 2.1](https://seengreat.com/wiki/167/pico-expansion-mini)** — buzzer, SD card, RGB LED, Grove connectors
3. **TCA9548A V1.0** — I2C multiplexer hub for sensor routing
4. **PCF8574** — I2C GPIO expander (behind TCA9548A channel 0)

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
  │  (free)        (buzzer)      I2C0→TCA                   │
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
| I2C0 → TCA9548A | GP20 SDA, GP21 SCL | Grove 6 | Sensor hub |
| RGB LED (WS2812) | GP22 | Built-in | Status indicator |
| RTC (DS1302) | GP6, GP7, GP8 | Built-in | Not used yet |

### Available for expansion

| Grove | GPIOs | Status |
|-------|-------|--------|
| 2 | GP2, GP3 | Free |
| 4 | GP16, GP17 | Free |

### Pin conflicts

- **GP18**: shared by buzzer, audio module, and Grove 5. Only use one at a time.
- **GP10/GP11/GP15**: used by SD card SPI1. Don't use Grove 3 while SD is active.
- **GP0/GP1**: reserved for MIDI UART.
- **GP20/GP21**: reserved for I2C0 to TCA9548A.

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
  │  Grove 6 (GP20/GP21)                                            │
  │  ├── GP20 (SDA) ────┐                                          │
  │  ├── GP21 (SCL) ──┐ │                                          │
  │  ├── 3.3V ───────┐│ │                                          │
  │  └── GND  ──────┐││ │                                          │
  │                  ││││                                           │
  │                  ▼▼▼▼                                           │
  │           ┌──────────────┐                                      │
  │           │ TCA9548A V1.0│                                      │
  │           │  I2C Hub     │                                      │
  │           │  addr: 0x70  │                                      │
  │           ├──────────────┤                                      │
  │           │ Ch 0 (I2C0)  │──→ PCF8574 (0x20) ──→ S1a (P0)     │
  │           │              │                   ──→ S1b (P1)      │
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
Piezo sensor ──→ comparator board ──→ PCF8574 GPIO expander
                                       │
                 S1a digital ──────→ P0 (bit 0, active-low)
                 S1b digital ──────→ P1 (bit 1, active-low)
                                       │
                         I2C (SDA/SCL) ─┘
                              │
                    TCA9548A channel 0
                              │
                    I2C0 (GP20/GP21) on Pico
```

## MIDI Out Wiring

Connect a 5-pin DIN connector to Grove 1 (GP0/GP1/3.3V/GND):

```
Pico 3.3V --[220 ohm]--> DIN-5 Pin 4
Pico GP0  --[220 ohm]--> DIN-5 Pin 5
                          DIN-5 Pin 2 --> GND (shield)
                          DIN-5 Pins 1, 3 --> not connected
```

Pin numbering viewed from solder side of connector. Two 220-ohm resistors and a DIN-5 female connector are all you need.

## Sensors

Piezo sensors with digital trigger output, routed through I2C:

| Sensor | TCA9548A Ch | PCF8574 Pin | Default Note |
|--------|-------------|-------------|-------------|
| S1a | 0 | P0 | A4 (440 Hz) |
| S1b | 0 | P1 | C5 (523 Hz) |

Edit `SENSOR_MAP` in `firmware/main.py` to change note assignments.

Rising-edge detection with 50ms debounce. PCF8574 inputs are active-low (sensor trigger pulls pin LOW).

### Adding more sensors

The TCA9548A has 8 channels. Add more PCF8574 expanders on other channels for additional sensor pairs. Each PCF8574 provides 8 digital inputs.

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

### With physical card reader (faster for WAV files)

```bash
python install.py --sd-path /Volumes/SD
```

## Boot Test Tune

On every power-up, after mounting the SD card, the Pico plays a 5-note test
sequence (C4 E4 G4 C5 G4) through both the **buzzer** (GP18) and the **audio
jack** (GP19). This confirms audio output is working. The tune plays before
`main.py` starts.

## Jumper Settings

- **BUZZER_SW**: ON (connect jumper cap)
- **Grove VCC**: 3.3V
