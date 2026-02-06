# tca9548a.py -- TCA9548A I2C multiplexer driver
#
# The TCA9548A has 8 downstream I2C channels (0-7).
# Write a single byte to select which channel(s) are active.
# Default I2C address: 0x70 (A0=A1=A2=GND).

from machine import I2C


class TCA9548A:
    def __init__(self, i2c, address=0x70):
        self.i2c = i2c
        self.address = address
        self._channel = -1

    def select(self, channel):
        """Enable a single downstream channel (0-7)."""
        if channel < 0 or channel > 7:
            raise ValueError("channel must be 0-7")
        if channel != self._channel:
            self.i2c.writeto(self.address, bytes([1 << channel]))
            self._channel = channel

    def disable_all(self):
        """Disable all downstream channels."""
        self.i2c.writeto(self.address, bytes([0]))
        self._channel = -1

    def scan_channel(self, channel):
        """Select a channel and scan for devices on it."""
        self.select(channel)
        addrs = self.i2c.scan()
        # Filter out the mux's own address
        return [a for a in addrs if a != self.address]
