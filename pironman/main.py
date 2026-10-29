import os
import sys
import time
import threading
import signal

from configparser import ConfigParser

from utils import log, run_command
from app_info import __app_name__, __version__, username, config_file
from system_status import (get_cpu_temperature, get_cpu_usage, get_ram_info,
                           get_disk_info, getIP)
from ws2812_RGB import WS2812, RGB_styles, RGB_backends

# Check if the environment is Home Assistant
# =================================================================
NORMAL = 0
HOME_ASSISTANT_ADDON = 1

mode = NORMAL
ha = None

if 'SUPERVISOR_TOKEN' in os.environ:
    try:
        from ha_api import HomeAssistantSupervisorAPI
        mode = HOME_ASSISTANT_ADDON
        ha = HomeAssistantSupervisorAPI(
            "http://supervisor/",
            os.environ['SUPERVISOR_TOKEN']
        )
        log('Home Assistant Addon mode')
    except Exception as e:
        log(f'Home Assistant API unavailable, running in normal mode: {e}')
        mode = NORMAL

# print info
# =================================================================
line = '-'*24
_time = time.strftime("%y/%m/%d %H:%M:%S", time.localtime())
log('\n%s%s%s'%(line,_time,line), timestamp=False)
log('%s version: %s'%(__app_name__, __version__), timestamp=False)
log('username: %s'%username, timestamp=False)
log('config_file: %s'%config_file, timestamp=False)
# Kernel Version
status, result = run_command("uname -a")
if status == 0:
    log("\nKernel Version:", timestamp=False)
    log(f"{result}", timestamp=False)
# OS Version
status, result = run_command(
    ". /etc/os-release 2>/dev/null && echo \"$PRETTY_NAME\"")
if status == 0:
    log("OS Version:", timestamp=False)
    log(f"{result}", timestamp=False)
# PCB information
status, result = run_command("cat /proc/cpuinfo|grep -E \'Revision|Model\'")
if status == 0:
    log("PCB info:", timestamp=False)
    log(f"{result}", timestamp=False)

# read config
# =================================================================
update_frequency = 0.5  # second
temp_lower_set = 2 # celsius, lower the fan temperature setting ( fan_temp ), the fan will turn off
POWER_KEY_HOLD_TIME = 2 # second, hold the power key this long to shut down

DEFAULTS = {
    'power_key_pin': 16,
    'power_key_pull': 'down',
    'fan_pin': 6,
    'temp_unit': 'C',
    'fan_temp': 50.0,
    'screen_always_on': False,
    'screen_off_time': 60,
    'rgb_enable': True,
    'rgb_style': 'breath',
    'rgb_color': '0a1aff',
    'rgb_blink_speed': 50,
    'rgb_pwm_freq': 1000,
    'rgb_pin': 10,
    'rgb_backend': 'auto',
}


def _as_bool(value, default):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes')


def read_config():
    '''
    Read the config file, falling back to the default for every single key.

    Up to 2.2.9 one missing or malformed key raised an exception that made
    the whole file be overwritten with defaults, so adding a new option
    silently wiped every setting the user had made. Now only the missing
    keys are appended.
    '''
    config = ConfigParser()
    values = dict(DEFAULTS)

    if not os.path.exists(config_file):
        log('Configuration file does not exist, recreating ...')
        try:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
        except OSError as e:
            log(f'cannot create config directory: {e}')

    try:
        config.read(config_file)
    except Exception as e:
        log(f'config file unreadable, using defaults: {e}')

    section = config['all'] if config.has_section('all') else {}
    missing = []
    casts = {
        'power_key_pin': int, 'fan_pin': int, 'fan_temp': float,
        'screen_off_time': int, 'rgb_blink_speed': int,
        'rgb_pwm_freq': int, 'rgb_pin': int,
        'screen_always_on': lambda v: _as_bool(v, False),
        'rgb_enable': lambda v: _as_bool(v, True),
    }
    for key, default in DEFAULTS.items():
        if key not in section:
            missing.append(key)
            continue
        raw = section[key]
        try:
            values[key] = casts.get(key, str)(raw)
            if isinstance(values[key], str):
                values[key] = values[key].strip()
        except Exception as e:
            log(f'config key {key}={raw!r} invalid ({e}), using {default!r}')

    # validate the values that can break hardware access
    if values['rgb_style'] not in RGB_styles:
        log(f"rgb_style {values['rgb_style']!r} unknown, using 'breath'")
        values['rgb_style'] = 'breath'
    if values['rgb_backend'] not in RGB_backends:
        log(f"rgb_backend {values['rgb_backend']!r} unknown, using 'auto'")
        values['rgb_backend'] = 'auto'
    if values['temp_unit'] not in ('C', 'F'):
        log(f"temp_unit {values['temp_unit']!r} unknown, using 'C'")
        values['temp_unit'] = 'C'
    if not 30 <= values['fan_temp'] <= 80:
        log(f"fan_temp {values['fan_temp']} out of range (30~80), using 50")
        values['fan_temp'] = 50.0

    if missing:
        log(f'adding missing config keys: {", ".join(missing)}')
        if not config.has_section('all'):
            config.add_section('all')
        for key in missing:
            config['all'][key] = str(DEFAULTS[key])
        try:
            with open(config_file, 'w') as f:
                config.write(f)
        except OSError as e:
            log(f'cannot write config file: {e}')

    return values


cfg = read_config()

power_key_pin = cfg['power_key_pin']
power_key_pull = cfg['power_key_pull']
fan_pin = cfg['fan_pin']
temp_unit = cfg['temp_unit']
fan_temp = cfg['fan_temp']
screen_always_on = cfg['screen_always_on']
screen_off_time = cfg['screen_off_time']
rgb_enable = cfg['rgb_enable']
rgb_style = cfg['rgb_style']
rgb_color = cfg['rgb_color']
rgb_blink_speed = cfg['rgb_blink_speed']
rgb_pwm_freq = cfg['rgb_pwm_freq']
rgb_pin = cfg['rgb_pin']
rgb_backend = cfg['rgb_backend']

for key in ('power_key_pin', 'power_key_pull', 'fan_pin', 'temp_unit',
            'fan_temp', 'screen_always_on', 'screen_off_time', 'rgb_enable',
            'rgb_style', 'rgb_color', 'rgb_blink_speed', 'rgb_pwm_freq',
            'rgb_pin', 'rgb_backend'):
    log('%s : %s' % (key, cfg[key]))
log('update_frequency : %s' % update_frequency)
log(">>>", timestamp=False)

# rgb_strip init
# =================================================================
try:
    strip = WS2812(LED_COUNT=16, LED_PIN=rgb_pin,
                   LED_FREQ_HZ=rgb_pwm_freq*1000, LED_BACKEND=rgb_backend)
    log('rgb_strip init success')
except Exception as e:
    log('rgb_strip init failed:\n%s'%e)
    strip = None

def rgb_show():
    log('rgb_show')
    try:
        if rgb_style in RGB_styles:
            log('rgb_show: %s'%rgb_style)
            strip.display(rgb_style, rgb_color, rgb_blink_speed, 255)
        else:
            log('rgb_style not in RGB_styles')
    except Exception as e:
        log(e,level='rgb_strip')

# close rgb
if 'close_rgb' in sys.argv:
    log('close_rgb in sys.argv')
    if strip != None:
        log('rgb_strip clear')
        strip.close()
    sys.exit(0)

# oled init
# =================================================================
oled_ok = False
oled_stat = False
oled = None
draw = None
image = None
font_8 = font_12 = None
width = height = 0

try:
    from PIL import Image, ImageDraw, ImageFont
    from oled import SSD1306_128_64

    oled = SSD1306_128_64()
    width = oled.width
    height = oled.height
    oled.begin()
    oled.clear()
    oled.on()

    image = Image.new('1', (width, height))
    draw = ImageDraw.Draw(image)
    _font = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'Minecraftia-Regular.ttf')
    font_8 = ImageFont.truetype(_font, 8)
    font_12 = ImageFont.truetype(_font, 12)

    oled_ok = True
    oled_stat = True
    log('oled init success')
except Exception as e:
    log('oled init failed:\n%s'%e)
    oled_ok = False
    oled_stat = False
    oled = None


def draw_text(text, x, y, fill=1):
    draw.text((x, y), text=str(text), font=font_8, fill=fill)


def oled_on():
    '''Switch the panel on, ignoring the call when there is no panel.'''
    global oled_stat
    if oled_ok:
        oled.on()
        oled_stat = True


def oled_off():
    global oled_stat
    if oled_ok:
        oled.off()
        oled_stat = False


# fan io  init
# =================================================================
fan_ok = False
fan = None
try:
    from gpiozero import DigitalOutputDevice as Fan
    fan = Fan(fan_pin)
    fan_ok = True
    log('fan init success')
except Exception as e:
    fan_ok = False
    log(f'fan init failed:\n {e}')


# powerkey io init
# =================================================================
power_key_ok = False
power_key = None

try:
    from gpiozero import InputDevice
    # pull_up=False keeps the fix from 2.2.9: gpiozero's Button uses edge
    # callbacks, which stopped working on kernel 6.6 and later, so the pin
    # is polled instead. The pull direction is configurable because it
    # depends on the Pironman board revision.
    _pull = {'down': False, 'up': True, 'none': None}.get(
        str(power_key_pull).strip().lower(), False)
    if _pull is None:
        power_key = InputDevice(power_key_pin, pull_up=None, active_state=True)
    else:
        power_key = InputDevice(power_key_pin, pull_up=_pull)
    power_key_ok = True
    log(f'power_key init success (pull={power_key_pull}, '
        f'idle value={power_key.value})')
except Exception as e:
    power_key_ok = False
    log(f'power_key init failed:\n {e}')


# get IP
# =================================================================
def getIPAddress():
    ip = None
    IPs = {}
    if mode == HOME_ASSISTANT_ADDON:
        try:
            IPs = ha.get_ip() or {}
        except Exception as e:
            log(f'home assistant ip lookup failed: {e}')
    if not IPs:
        IPs = getIP()
    if 'wlan0' in IPs and IPs['wlan0']:
        ip = IPs['wlan0']
    elif 'eth0' in IPs and IPs['eth0']:
        ip = IPs['eth0']
    else:
        for interface in IPs:
            if IPs[interface]:
                ip = IPs[interface]
                break
    return ip or 'DISCONNECT'

# exit handler
# =================================================================
_exiting = threading.Event()

def exit_handler():
    '''
    Release every resource independently.

    Up to 2.2.9 all of this sat in one try/except, so a missing power key
    raised a NameError on the very first line and the panel, the fan and
    the LEDs were never shut down.
    '''
    if _exiting.is_set():
        return
    _exiting.set()
    # stop the animation thread first, otherwise it keeps writing to the
    # strip while we are trying to clear it
    if strip is not None:
        try:
            strip.stop()
        except Exception as e:
            log(f'exit: strip.stop failed: {e}')
    for what, device, action in (
        ('power_key', power_key, lambda: power_key.close()),
        ('oled', oled, lambda: (oled.off(), oled.close())),
        ('fan', fan, lambda: (fan.off(), fan.close())),
        ('rgb', strip, lambda: strip.close()),
    ):
        if device is None:
            continue
        try:
            action()
        except Exception as e:
            log(f'exit: {what} cleanup failed: {e}')
    log('cleanup done')

def signal_handler(signo, frame):
    if signo == signal.SIGTERM or signo == signal.SIGINT:
        log("Received SIGTERM or SIGINT signal. Cleaning up...")
        exit_handler()
        sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# main
# =================================================================
def main():
    global fan_temp, power_key_pin, screen_off_time, rgb_color, rgb_pin
    global oled_stat, screen_always_on

    last_ip = None

    time_start = time.time()
    power_key_flag = False
    power_timer = 0

    # without a power key there is no way to wake the panel again,
    # so keep it on permanently
    if not power_key_ok and oled_ok:
        log('no power key, keeping the screen on')
        screen_always_on = True

    # ---- rgb_thread start ----
    if strip != None:
        if rgb_enable:
            rgb_thread = threading.Thread(target=rgb_show)
            rgb_thread.daemon = True
            rgb_thread.start()
        else:
            strip.clear()


    # ---- main loop ----
    while not _exiting.is_set():

        # ---- get CPU temperature ----
        CPU_temp_C = float(get_cpu_temperature()) # celcius
        CPU_temp_F = float(CPU_temp_C * 1.8 + 32) # fahrenheit

        # ---- fan control ----
        # fan_temp is always in celsius (as documented in config.txt);
        # temp_unit only selects the unit shown on the panel. Before 2.3.0
        # the threshold was compared against the fahrenheit value too, so
        # "pironman -u F" made the fan run non-stop.
        if fan_ok:
            if CPU_temp_C > fan_temp:
                fan.on()
            elif CPU_temp_C < fan_temp - temp_lower_set:
                fan.off()

        # ---- oled control ----
        if oled_ok and oled_stat == True:
            # ---- get system status data ----
            # CPU usage
            CPU_usage = float(get_cpu_usage())
            # clear draw buffer
            draw.rectangle((0,0,width,height), outline=0, fill=0)
            # RAM
            ram_info = get_ram_info()
            ram_total = round(ram_info['total'], 1)
            ram_used = round(ram_info['used'], 1)
            ram_percent = round(ram_info['percent'], 1)
            # Disk information
            disk_info = get_disk_info()
            disk_total = disk_info['total']
            disk_used = disk_info['used']
            disk_percent = disk_info['percent']

            disk_unit = 'G1'
            if disk_total >= 1000:
                disk_unit = 'T'
                disk_total = round(disk_total/1000, 3)
                disk_used = round(disk_used/1000, 3)
            elif disk_total >= 100:
                disk_unit = 'G2'
  
            # get ip if disconnected
            ip = getIPAddress()

            if last_ip != ip:
                last_ip = ip
                log("Get IP: %s" %ip)

            # ---- display info ----
            ip_rect = Rect(40, 0, 87, 10)
            ram_info_rect = Rect(40, 17, 87, 10)
            ram_rect = Rect(40, 29, 87, 10)
            rom_info_rect = Rect(40, 41, 87, 10)
            rom_rect = Rect(40, 53, 87, 10)
            # cpu usage
            draw_text('CPU',6,0)
            draw.pieslice((0, 12, 30, 42), start=180, end=0, fill=0, outline=1)
            draw.pieslice((0, 12, 30, 42), start=180, end=int(180+180*CPU_usage*0.01), fill=1, outline=1)
            draw_text('{:^5.1f} %'.format(CPU_usage),2,27)
            # cpu temp
            if temp_unit == 'C':
                draw_text('{:>4.1f} \'C'.format(CPU_temp_C),2,38)
                draw.pieslice((0, 33, 30, 63), start=0, end=180, fill=0, outline=1)
                draw.pieslice((0, 33, 30, 63), start=int(180-180*CPU_temp_C*0.01), end=180, fill=1, outline=1)
            elif temp_unit == 'F':
                draw_text('{:>4.1f} \'F'.format(CPU_temp_F),2,38)
                draw.pieslice((0, 33, 30, 63), start=0, end=180, fill=0, outline=1)
                pcent = (CPU_temp_F-32)/1.8
                draw.pieslice((0, 33, 30, 63), start=int(180-180*pcent*0.01), end=180, fill=1, outline=1)
            # RAM
            draw_text(f'RAM:  {ram_used:^4.1f}/{ram_total:^4.1f} G',*ram_info_rect.coord())
            draw.rectangle(ram_rect.rect(), outline=1, fill=0)
            draw.rectangle(ram_rect.rect(ram_percent), outline=1, fill=1)
            # Disk
            if disk_unit == 'G1':
                _dec = 1
                if disk_used < 10:
                    _dec = 2              
                draw_text(f'DISK: {disk_used:>2.{_dec}f}/{disk_total:<2.1f} G', *rom_info_rect.coord())
            elif disk_unit == 'G2':
                _dec = 0
                if disk_used < 100:
                    _dec = 1
                draw_text(f'DISK: {disk_used:>3.{_dec}f}/{disk_total:<3.0f} G', *rom_info_rect.coord())
            elif disk_unit == 'T':
                draw_text(f'DISK: {disk_used:>2.2f}/{disk_total:<2.2f} T', *rom_info_rect.coord())

            draw.rectangle(rom_rect.rect(), outline=1, fill=0)
            draw.rectangle(rom_rect.rect(disk_percent), outline=1, fill=1)
            # IP
            draw.rectangle((ip_rect.x-13,ip_rect.y,ip_rect.x+ip_rect.width,ip_rect.height), outline=1, fill=1)
            draw.pieslice((ip_rect.x-25,ip_rect.y,ip_rect.x-3,ip_rect.height+10), start=270, end=0, fill=0, outline=0)
            draw_text(ip,*ip_rect.coord(),0)
            # draw the image buffer.
            try:
                oled.image(image)
                oled.display()
            except OSError as e:
                # a single I2C glitch must not take the service down
                log(f'oled write failed: {e}')

            # screen off timer
            if screen_always_on == False and (time.time()-time_start) > screen_off_time:
                oled_off()

        # ---- power key event ----
        if power_key_ok:
            if power_key.value == 0:
                # screen on
                if oled_ok and oled_stat == False:
                    oled_on()
                    time_start = time.time()
                # power off
                if power_key_flag == False:
                    power_key_flag = True
                    power_timer = time.time()
                elif (time.time()-power_timer) > POWER_KEY_HOLD_TIME:
                    #
                    if oled_ok:
                        oled_on()
                        draw.rectangle((0,0,width,height), outline=0, fill=0)
                        left, top, right, bottom = font_12.getbbox('POWER OFF')
                        text_width = right - left
                        text_height = bottom - top
                        text_x = int((width - text_width)/2-1)
                        text_y = int((height - text_height)/2-1)
                        draw.text((text_x, text_y), text='POWER OFF', font=font_12, fill=1)
                        try:
                            oled.image(image)
                            oled.display()
                        except OSError as e:
                            log(f'oled write failed: {e}')
                    # wait for the key to be released; sleep instead of
                    # spinning, the old busy loop pegged a core at 100%
                    while power_key.value == 0:
                        time.sleep(0.05)
                    log("POWER OFF")
                    #
                    oled_off()
                    if mode == HOME_ASSISTANT_ADDON:
                        ha.shutdown() # shutdown homeassistant host
                    else:
                        exit_handler()
                        os.system('poweroff')
                    return
            else:
                power_key_flag = False


        time.sleep(update_frequency)

class Rect:
    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.x2 = self.x + self.width
        self.y2 = self.y + self.height

    def coord(self):
        return (self.x, self.y)
    def rect(self, pecent=100):
        return (self.x, self.y, self.x + int(self.width*pecent/100.0), self.y2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        log(f'error\n {traceback.format_exc()}')
    finally:
        exit_handler()
