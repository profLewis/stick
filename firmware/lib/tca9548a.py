# tca9548a.py -- TCA9548A I2C multiplexer driver
#
# The TCA9548A has 8 downstream I2C channels (0-7).
# Write a single byte to select which channel(s) are active.
# Default I2C address: 0x70 (A0=A1=A2=GND).
#
# NOTE: Uses SoftI2C because hardware I2C on RP2350 has
# compatibility issues with the TCA9548A.

from machine import SoftI2C, Pin


class TCA9548A:
    def __init__(self, sda_pin, scl_pin, address=0x70, freq=50000):
        self.sda_pin = sda_pin
        self.scl_pin = scl_pin
        self.address = address
        self.freq = freq
        self._channel = -1

    def _get_i2c(self):
        """Create a fresh SoftI2C instance."""
        return SoftI2C(sda=Pin(self.sda_pin), scl=Pin(self.scl_pin),
                       freq=self.freq)

    def select(self, channel):
        """Enable a single downstream channel (0-7)."""
        if channel < 0 or channel > 7:
            raise ValueError("channel must be 0-7")
        i2c = self._get_i2c()
        i2c.writeto(self.address, bytes([1 << channel]))
        self._channel = channel

    def read_pins(self, channel):
        """Select channel and read the SDA/SCL lines as digital inputs.

        Used when the TCA9548A is wired as a digital signal mux
        (sensor D0 outputs on SDA/SCL lines instead of I2C devices).

        Returns (sda_value, scl_value) as 0 or 1.
        """
        self.select(channel)
        sda = Pin(self.sda_pin, Pin.IN, Pin.PULL_UP)
        scl = Pin(self.scl_pin, Pin.IN, Pin.PULL_UP)
        return sda.value(), scl.value()

    def disable_all(self):
        """Disable all downstream channels."""
        i2c = self._get_i2c()
        i2c.writeto(self.address, bytes([0]))
        self._channel = -1
