# midi.py -- MIDI output over UART
#
# Hardware: UART0 TX on GP0 (Grove connector 1), 31250 baud
# Circuit:
#   3.3V --[220 ohm]--> DIN-5 Pin 4
#   GP0  --[220 ohm]--> DIN-5 Pin 5
#   DIN-5 Pin 2 --> GND (shield)

from machine import UART, Pin

_MIDI_BAUD = 31250
_NOTE_ON = 0x90
_NOTE_OFF = 0x80
_PROG_CHG = 0xC0


class MidiOut:
    def __init__(self, uart_id=0, tx_pin=0, channel=0):
        self.channel = channel & 0x0F
        self.uart = UART(uart_id, baudrate=_MIDI_BAUD, tx=Pin(tx_pin))

    def note_on(self, note, velocity=127):
        """Send Note On. note: 0-127, velocity: 0-127."""
        self.uart.write(bytes([_NOTE_ON | self.channel, note & 0x7F, velocity & 0x7F]))

    def note_off(self, note, velocity=0):
        """Send Note Off."""
        self.uart.write(bytes([_NOTE_OFF | self.channel, note & 0x7F, velocity & 0x7F]))

    def program_change(self, program):
        """Send Program Change. program: 0-127."""
        self.uart.write(bytes([_PROG_CHG | self.channel, program & 0x7F]))
