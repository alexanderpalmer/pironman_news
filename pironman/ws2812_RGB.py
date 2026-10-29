import os
import threading
import time

from utils import log

# LED strip configuration:
# LED_COUNT      = 16      # Number of LED pixels.
# LED_PIN        = 10      # GPIO pin connected to the pixels
#                          # 10 = SPI0 MOSI, 12 = PWM0, 21 = PCM_DOUT
# LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
# LED_DMA        = 10      # DMA channel to use for generating signal (try 5)
# LED_BRIGHTNESS = 255     # Set to 0 for darkest and 255 for brightest
# LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)

RGB_styles = [
    'breath',
    'static',
    'leap',
    'flow',
    'raise_up',
    'colorful',
    'colorful_static',
    'colorful_leap',
]
colorful_leds = [
    "#ff0000",
    "#e71164",
    "#ffa500",
    "#0000ff",
    "#ffC800",
    "#00ff00",
    "#0000ff",
    "#00ffb4",
    "#ff0000",
    "#00ff00",
    "#00ff00",
    "#8b00ff",
    "#8b00ff",
    "#8b00ff",
    "#0000ff",
    "#0000ff",
]

RGB_backends = ['auto', 'spi', 'ws281x']


def Color(red, green, blue, white=0):
    '''24/32 bit colour value, kept for compatibility with rpi_ws281x.'''
    return (white << 24) | (red << 16) | (green << 8) | blue


# ---------------------------------------------------------------- backends
#
# Two ways to clock out the WS2812 protocol:
#
# "spi"     bit-bangs the waveform through the kernel SPI driver on GPIO10
#           (SPI0 MOSI). Each WS2812 bit becomes three SPI bits at 2.4 MHz,
#           so a 0 is 100 (0.42 us high) and a 1 is 110 (0.83 us high),
#           which is inside the WS2812B timing window. This needs nothing
#           but python3-spidev, no compiler, no /dev/mem and no DMA channel.
#           It is the default because the Pironman strip sits on GPIO10.
#
# "ws281x"  the original rpi_ws281x C library, required for the PWM (12) and
#           PCM (21) pin options. It has to be built with pip and maps
#           /dev/mem, so it only works as root.


class _SpiBackend:
    '''WS2812 driver on top of the kernel SPI driver (GPIO10 / SPI0 MOSI).'''

    BITS_PER_BIT = 3
    # 0 -> 100, 1 -> 110
    _LUT = None
    # WS2812B-V5 wants the data line low for >280 us to latch a frame.
    # One SPI byte at 2.4 MHz lasts 3.33 us, so 96 bytes give ~320 us.
    RESET_BYTES = 96

    def __init__(self, led_count, led_pin, brightness, freq_hz):
        import spidev
        if led_pin != 10:
            raise ValueError(
                f'the SPI backend only drives GPIO10 (SPI0 MOSI), not GPIO{led_pin}')
        self.led_count = led_count
        self.brightness = brightness
        self.freq_hz = freq_hz
        self._pixels = [(0, 0, 0)] * led_count
        if _SpiBackend._LUT is None:
            _SpiBackend._LUT = self._build_lut()
        self._device = os.environ.get('PIRONMAN_SPI_DEV', '/dev/spidev0.0')
        if not os.path.exists(self._device):
            raise FileNotFoundError(
                f"{self._device} not found. Enable SPI with "
                "'sudo raspi-config nonint do_spi 0' or add 'dtparam=spi=on' "
                "to /boot/firmware/config.txt and reboot.")
        bus, dev = (int(x) for x in self._device.rsplit('spidev', 1)[1].split('.'))
        self._spi = spidev.SpiDev()
        self._spi.open(bus, dev)
        self._spi.mode = 0
        self._spi.bits_per_word = 8
        self._spi.max_speed_hz = int(freq_hz * self.BITS_PER_BIT)
        try:
            # Leaves CE0 alone. spi-bcm2835 uses its native chip select and
            # may reject SPI_NO_CS; the strip does not care either way.
            self._spi.no_cs = True
        except OSError:
            pass
        # The driver rounds the clock to an even divisor of the core clock,
        # so log what we actually got: WS2812B tolerates about +/-150 ns,
        # which is roughly 2.0 to 2.8 MHz here.
        actual = self._spi.max_speed_hz
        log(f'rgb backend: spi ({self._device} @ {actual} Hz, '
            f'{actual / self.BITS_PER_BIT / 1000:.1f} kHz bit rate)')
        if not 2_000_000 <= actual <= 2_900_000:
            log(f'warning: SPI clock {actual} Hz is outside the WS2812 '
                f'timing window, colours may be wrong')

    @staticmethod
    def _build_lut():
        lut = []
        for byte in range(256):
            out = 0
            for i in range(7, -1, -1):
                out = (out << 3) | (0b110 if (byte >> i) & 1 else 0b100)
            lut.append(out.to_bytes(3, 'big'))
        return lut

    def begin(self):
        pass

    def setPixelColor(self, index, color):
        if not 0 <= index < self.led_count:
            return
        self._pixels[index] = ((color >> 16) & 0xff,
                               (color >> 8) & 0xff,
                               color & 0xff)

    def show(self):
        lut = self._LUT
        scale = self.brightness
        buf = bytearray()
        for r, g, b in self._pixels:
            if scale != 255:
                r = r * scale // 255
                g = g * scale // 255
                b = b * scale // 255
            # WS2812 expects green first
            buf += lut[g]
            buf += lut[r]
            buf += lut[b]
        buf += bytes(self.RESET_BYTES)
        self._spi.writebytes2(buf)

    def cleanup(self):
        try:
            self._spi.close()
        except Exception:
            pass


class _Ws281xBackend:
    '''Original rpi_ws281x driver, needed for the PWM and PCM pin options.'''

    def __init__(self, led_count, led_pin, brightness, freq_hz, dma, invert):
        from rpi_ws281x import PixelStrip
        self._strip = PixelStrip(led_count, led_pin, freq_hz, dma, invert,
                                 brightness)
        time.sleep(0.01)
        self._strip.begin()
        log(f'rgb backend: ws281x (GPIO{led_pin} @ {freq_hz} Hz)')

    def begin(self):
        self._strip.begin()

    def setPixelColor(self, index, color):
        self._strip.setPixelColor(index, color)

    def show(self):
        self._strip.show()

    def cleanup(self):
        pass


class WS2812():

    lights_order = [1, 3, 5, 7, 0, 2, 4, 6, 8, 9, 10, 11, 12, 13, 14, 15]

    def __init__(
        self,
        LED_COUNT,
        LED_PIN,
        LED_BRIGHTNESS=255,
        LED_FREQ_HZ=1000000,
        LED_DMA=10,
        LED_INVERT=False,
        LED_BACKEND='auto',
    ):
        self.led_count = LED_COUNT
        self.led_pin = LED_PIN
        self.led_brightness = LED_BRIGHTNESS
        self.led_freq_hz = LED_FREQ_HZ
        self.led_dma = LED_DMA
        self.led_invert = LED_INVERT
        self.backend_name = LED_BACKEND
        self.strip = None
        # lets display() return instead of looping forever, so the service
        # can shut the strip down without racing the animation thread
        self._stop = threading.Event()
        self.init()

    def _make_backend(self, name):
        if name == 'spi':
            return _SpiBackend(self.led_count, self.led_pin,
                               self.led_brightness, 800000)
        return _Ws281xBackend(self.led_count, self.led_pin,
                              self.led_brightness, self.led_freq_hz,
                              self.led_dma, self.led_invert)

    def init(self):
        wanted = self.backend_name
        if wanted not in RGB_backends:
            log(f'unknown rgb_backend {wanted!r}, falling back to auto')
            wanted = 'auto'
        if wanted == 'auto':
            # GPIO10 is SPI0 MOSI, drive it through the kernel SPI driver;
            # the PWM and PCM pins can only be done by rpi_ws281x
            order = ['spi', 'ws281x'] if self.led_pin == 10 else ['ws281x']
        else:
            order = [wanted]

        errors = []
        for name in order:
            try:
                self.strip = self._make_backend(name)
                self.backend_name = name
                return
            except Exception as e:
                errors.append(f'{name}: {e}')
        raise RuntimeError('no usable rgb backend (' + '; '.join(errors) + ')')

    def reinit(self):
        if self.strip is None:
            self.init()

    def stop(self):
        '''Ask a running display() loop to return.'''
        self._stop.set()

    def _sleep(self, seconds):
        '''Interruptible sleep; returns True when a stop was requested.'''
        return self._stop.wait(seconds)

    # str or hex, eg: 'ffffff', '#ffffff', '#FFFFFF'
    def hex_to_rgb(self, hex):
        try:
            hex = hex.strip().replace('#', '')
            r = int(hex[0:2], 16)
            g = int(hex[2:4], 16)
            b = int(hex[4:6], 16)
            return [r, g, b]
        except Exception as e:
            log('color parameter error: \n%s' % e)
            return [0, 0, 0]

    def clear(self, color: str = '#000000'):
        r, g, b = self.hex_to_rgb(color)
        self.reinit()
        self.strip.begin()
        for i in range(self.led_count):
            self.strip.setPixelColor(i, Color(r, g, b))
        self.strip.show()

    def close(self):
        self.stop()
        try:
            self.clear()
        except Exception:
            pass
        if self.strip is not None:
            self.strip.cleanup()
            self.strip = None

    def display(self,
                style: str,
                color: str = '#0a1aff',
                speed=50,
                brightness=255):
        color = list(self.hex_to_rgb(color))
        self.clear()
        if style not in RGB_styles:
            log(f'LED strip style error: unknown style {style!r}')
            return
        try:
            fuc = getattr(self, style)
            fuc(color, speed)
        except Exception as e:
            log(f'LED display error: {e}')


# styles

    def breath(self, color: list = [255, 255, 255], speed=50):
        speed = 101 - speed
        while not self._stop.is_set():
            self.reinit()
            for i in list(range(2, 101)) + list(range(100, 1, -1)):
                r, g, b = [int(x * i * 0.01) for x in color]
                for index in self.lights_order:
                    self.strip.setPixelColor(index, Color(r, g, b))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return

    def static(self, color: list = [255, 255, 255], speed=50):
        while not self._stop.is_set():
            self.reinit()
            # --- no breath ---
            r, g, b =  color
            for index in self.lights_order:
                self.strip.setPixelColor(index, Color(r,g,b))
            self.strip.show()
            if self._sleep(2):
                return

    def leap(self, color: list = [255, 255, 255], speed=50):
        speed = 101 - speed
        r, g, b = color
        while not self._stop.is_set():
            self.reinit()
            for i in range(self.led_count):
                for index in self.lights_order:
                    self.strip.setPixelColor(index, Color(0, 0, 0))
                self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return

    def flow(self, color: list = [255, 255, 255], speed=50):
        speed = 101 - speed
        r, g, b = color
        while not self._stop.is_set():
            self.reinit()
            for index in self.lights_order:
                self.strip.setPixelColor(index, Color(r, g, b))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return
            for j in range(self.led_count):
                self.strip.setPixelColor(j, Color(0, 0, 0))
            self.strip.show()
            if self._sleep(0.005 * speed):
                return

    def raise_up(self, color: list = [255, 255, 255], speed=50):
        speed = 101 - speed
        r, g, b = color
        while not self._stop.is_set():
            self.reinit()
            for first, last in ((0, 4), (4, 8), (8, 16)):
                for i in range(2, 101):
                    r, g, b = [int(x * i * 0.01) for x in color]
                    for index in range(first, last, 1):
                        self.strip.setPixelColor(self.lights_order[index],
                                                 Color(r, g, b))
                    self.strip.show()
                    if self._sleep(0.0002 * speed):
                        return
            # turn off
            if self._sleep(10 * 0.0005 * speed):
                return
            for index in self.lights_order:
                self.strip.setPixelColor(index, Color(0, 0, 0))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return

    def colorful(self, color: list = None, speed=50):
        speed = 101 - speed
        _color = list(
            self.hex_to_rgb(colorful_leds[i]) for i in range(self.led_count))
        while not self._stop.is_set():
            self.reinit()
            for i in list(range(2, 101)) + list(range(100, 1, -1)):
                for index in self.lights_order:
                    r, g, b = [int(x * i * 0.01) for x in _color[index]]
                    self.strip.setPixelColor(index, Color(r, g, b))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return

    def colorful_static(self, color: list = None, speed=50):
        _color = list(
            self.hex_to_rgb(colorful_leds[i]) for i in range(self.led_count))
        while not self._stop.is_set():
            self.reinit()
            for index in self.lights_order:
                r, g, b =  _color[index]
                self.strip.setPixelColor(index, Color(r,g,b))
            self.strip.show()
            if self._sleep(2):
                return

    def colorful_leap(self, color: list = None, speed=50):
        speed = 101 - speed
        while not self._stop.is_set():
            self.reinit()
            for i in range(self.led_count):
                r, g, b = self.hex_to_rgb(colorful_leds[i])
                for index in self.lights_order:
                    self.strip.setPixelColor(index, Color(0, 0, 0))
                self.strip.setPixelColor(i, Color(r, g, b))
                self.strip.show()
                if self._sleep(0.001 * speed):
                    return

if __name__ == "__main__":
    import sys
    style = sys.argv[1] if len(sys.argv) > 1 else 'colorful_leap'
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    strip = WS2812(16, 10)  # LED_COUNT, LED_PIN
    t = threading.Thread(target=strip.display,
                         args=(style, '#0a1aff', 80, 255), daemon=True)
    t.start()
    time.sleep(seconds)
    strip.close()
