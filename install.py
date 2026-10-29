#!/usr/bin/env python3
import os
import re
import sys
import time
import threading

sys.path.append('./pironman')
from app_info import __app_name__, __version__, username, config_file

if os.geteuid() != 0:
    print("Script must be run as root. Try 'sudo python3 install.py'")
    sys.exit(1)

errors = []
warnings = []

avaiable_options = [
    '-h', '--help', '--no-dep', '--skip-config-txt', '--skip-auto-startup',
    '--skip-reboot', '--with-ws281x'
]

usage = '''
Usage:
    sudo python3 install.py [option]

Options:
               --no-dep             Do not download dependencies
               --skip-config-txt    Skip config /boot/firmware/config.txt
               --skip-auto-startup  Skip enable auto startup
               --skip-reboot        Skip reboot after install
               --with-ws281x        Also build the rpi-ws281x library. Only
                                    needed to drive the LED strip from the
                                    PWM (GPIO12) or PCM (GPIO21) pin; the
                                    default SPI pin (GPIO10) does not use it.
    -h         --help               Show this help text and exit
'''

# Everything comes from apt. On Debian trixie /usr is marked
# EXTERNALLY-MANAGED (PEP 668), so "pip3 install" either refuses to run or
# has to be forced with --break-system-packages, which then shadows the
# distribution packages. All runtime dependencies exist as .deb, so pip is
# no longer used for them:
#   python3-pil       was built from source via pip ("pillow --no-cache-dir"),
#                     which needed libtiff5-dev, libfreetype6-dev and friends
#   python3-smbus2    pure python I2C, lets the OLED frame go out in one
#                     transaction
#   python3-spidev    drives the WS2812 strip on GPIO10 without rpi-ws281x
#   python3-lgpio     backend gpiozero uses on kernel 6.6 and later
# The old list also pulled in libfreetype6-dev, which no longer exists in
# trixie (it is libfreetype-dev now), so "apt install" failed there.
APT_INSTALL_LIST = [
    'i2c-tools',
    'python3-smbus',
    'python3-smbus2',
    'python3-spidev',
    'python3-pil',
    'python3-psutil',
    'python3-requests',
    'python3-gpiozero',
    'python3-lgpio',
]

# only for --with-ws281x
APT_WS281X_LIST = [
    'build-essential',
    'python3-dev',
]
PIP_WS281X_LIST = [
    'rpi-ws281x',
]


def run_command(cmd=""):
    import subprocess
    p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, universal_newlines=True)
    return p.returncode, p.stdout


at_work_tip_sw = False


def working_tip():
    char = ['/', '-', '\\', '|']
    i = 0
    global at_work_tip_sw
    while at_work_tip_sw:
        i = (i + 1) % 4
        sys.stdout.write('\033[?25l')  # cursor invisible
        sys.stdout.write('%s\033[1D' % char[i])
        sys.stdout.flush()
        time.sleep(0.5)

    sys.stdout.write(' \033[1D')
    sys.stdout.write('\033[?25h')  # cursor visible
    sys.stdout.flush()


def do(msg="", cmd="", fatal=True):
    print(" - %s... " % (msg), end='', flush=True)
    # at_work_tip start
    global at_work_tip_sw
    at_work_tip_sw = True
    _thread = threading.Thread(target=working_tip)
    _thread.daemon = True
    _thread.start()
    # process run
    status, result = run_command(cmd)
    # at_work_tip stop
    at_work_tip_sw = False
    while _thread.is_alive():
        time.sleep(0.01)
    # status
    if status == 0:
        print('Done')
    elif fatal:
        print('\033[1;35mError\033[0m')
        errors.append("%s error:\n  Status:%s\n  Error:%s" %
                      (msg, status, result))
    else:
        print('\033[1;33mSkipped\033[0m')
        warnings.append("%s skipped:\n  Status:%s\n  Output:%s" %
                        (msg, status, result))
    return status


def set_config(msg="", name="", value="", config=None):
    print(" - %s... " % (msg), end='', flush=True)
    try:
        (config or Config()).set(name, value)
        print('Done')
    except Exception as e:
        print('\033[1;35mError\033[0m')
        errors.append("%s error:\n Error:%s" % (msg, e))


SECTION_RE = re.compile(r'^\[[^\]]+\]$')


class Config(object):
    '''
    Minimal editor for the Raspberry Pi boot config.

    The 2.2.9 version matched keys with "name in config", a plain substring
    test over the whole file. That had two consequences: setting
    "core_freq" could hit an existing "core_freq_min" line and destroy it,
    and a key inside a conditional block such as [pi5] or [cm4] could be
    rewritten even though it does not apply to this board. Keys are now
    matched as whole assignments and only inside the target section.
    '''
    DEFAULT_FILE = "/boot/firmware/config.txt"
    BACKUP_FILE = "/boot/config.txt"

    def __init__(self, file=None):
        # check if file exists
        if file is None:
            if os.path.exists(self.DEFAULT_FILE):
                self.file = self.DEFAULT_FILE
            elif os.path.exists(self.BACKUP_FILE):
                self.file = self.BACKUP_FILE
            else:
                raise FileNotFoundError(
                    f"{self.DEFAULT_FILE} or {self.BACKUP_FILE} are not found."
                )
        else:
            self.file = file
            if not os.path.exists(file):
                raise FileNotFoundError(f"{self.file} is not found.")
        # read config file
        with open(self.file, 'r') as f:
            self.configs = f.read()
        self.configs = self.configs.split('\n')
        self._backed_up = False

    def _backup(self):
        '''Keep one copy of the untouched file next to the original.'''
        if self._backed_up:
            return
        backup = self.file + '.pironman-bak'
        if not os.path.exists(backup):
            with open(backup, 'w') as f:
                f.write('\n'.join(self.configs))
        self._backed_up = True

    def _section_of(self, index):
        '''
        Which conditional block line `index` belongs to.

        Lines before the first [filter] apply to every board, so they count
        as "[all]".
        '''
        section = '[all]'
        for i in range(index):
            stripped = self.configs[i].strip()
            if SECTION_RE.match(stripped):
                section = stripped
        return section

    @staticmethod
    def _is_entry(line, name):
        '''True when line assigns exactly `name` (commented out or not).'''
        bare = line.strip().lstrip('#').strip()
        return bare == name or bare.startswith(name + '=')

    def remove(self, expected):
        # build a new list instead of removing from the list being iterated
        self._backup()
        self.configs = [c for c in self.configs if expected not in c]
        return self.write_file()

    def set(self, name, value=None, device="[all]"):
        '''
        device : "[all]", "[pi3]", "[pi4]" or other
        '''
        self._backup()
        entry = name if value is None else f'{name}={value}'

        active = None     # an uncommented assignment we can update
        commented = None  # a commented out one we can revive
        for i, line in enumerate(self.configs):
            if SECTION_RE.match(line.strip()):
                continue
            if not self._is_entry(line, name):
                continue
            if self._section_of(i) != device:
                continue
            if line.strip().startswith('#'):
                if commented is None:
                    commented = i
            else:
                active = i
                break

        if active is not None:
            self.configs[active] = entry
        elif commented is not None:
            self.configs[commented] = entry
        else:
            # append at the end, opening the section only when the file does
            # not already end inside it, so repeated installs do not stack up
            # [all] headers
            while self.configs and self.configs[-1].strip() == '':
                self.configs.pop()
            if self._section_of(len(self.configs)) != device:
                self.configs.append(device)
            self.configs.append(entry)
            self.configs.append('')
        return self.write_file()

    def get(self, name, device="[all]"):
        for i, line in enumerate(self.configs):
            if SECTION_RE.match(line.strip()):
                continue
            if line.strip().startswith('#'):
                continue
            if self._is_entry(line, name) and self._section_of(i) == device:
                return line.strip()
        return None

    def write_file(self):
        try:
            config = '\n'.join(self.configs)
            with open(self.file, 'w') as f:
                f.write(config)
            return 0, config
        except Exception as e:
            return -1, e


def install():
    print(
        f"{__app_name__} {__version__} install process starts for {username}:\n"
    )

    # print Kernel Version
    status, result = run_command("uname -a")
    if status == 0:
        print(f"Kernel Version:\n{result}")
    # print OS Version
    status, result = run_command(
        ". /etc/os-release && echo \"$PRETTY_NAME\"")
    if status == 0:
        print(f"OS Version:\n{result}")
    # print PCB information
    status, result = run_command(
        "cat /proc/cpuinfo|grep -E \'Revision|Model\'")
    if status == 0:
        print(f"PCB info::\n{result}")

    options = []
    if len(sys.argv) > 1:
        options = sys.argv[1:]
        for opt in options:
            if opt not in avaiable_options:
                print("Option {} is not found.".format(opt))
                print(usage)
                sys.exit(1)
        if "-h" in options or "--help" in options:
            print(usage)
            quit()
    #
    if "--no-dep" not in options:
        # update apt
        do(msg="update apt", cmd='apt-get update')
        print("Install dependencies with apt")
        do(msg="apt --fix-broken", cmd="apt-get --fix-broken install -y")
        for dep in APT_INSTALL_LIST:
            do(msg="install %s" % dep, cmd='apt-get install %s -y' % dep)
        #
        if "--with-ws281x" in options:
            print("Install the rpi-ws281x library (PWM/PCM pin support)")
            for dep in APT_WS281X_LIST:
                do(msg="install %s" % dep, cmd='apt-get install %s -y' % dep)
            # rpi-ws281x has no .deb, so this one really does need pip and
            # has to opt out of the PEP 668 guard on /usr
            for dep in PIP_WS281X_LIST:
                do(msg="install %s" % dep,
                   cmd=f'pip3 install {dep} --break-system-packages',
                   fatal=False)
    #
    print("Config gpio")
    #
    if "--skip-config-txt" not in options:
        # raspi-config is the supported way to flip these and also creates
        # the /dev nodes right away where possible
        _status, _ = run_command("which raspi-config")
        if _status == 0:
            do(msg="enable i2c ", cmd='raspi-config nonint do_i2c 0')
            do(msg="enable spi ", cmd='raspi-config nonint do_spi 0')
        #
        config = Config()
        print(f" - boot config: {config.file}")
        set_config(msg="enable i2c in config",
                   name="dtparam=i2c_arm",
                   value="on", config=config)
        set_config(msg="enable spi in config", name="dtparam=spi", value="on",
                   config=config)
        # The SPI clock on the Pi 4 is derived from the GPU core clock, so
        # pinning it keeps the WS2812 bit timing inside spec. Without
        # core_freq_min the core drops to 200 MHz when idle and the strip
        # shows wrong colours.
        set_config(msg="set core_freq to 500", name="core_freq", value="500",
                   config=config)
        set_config(msg="set core_freq_min to 500",
                   name="core_freq_min",
                   value="500", config=config)
        # dtoverlay=gpio-poweroff,gpio_pin=26,active_low=0
        set_config(msg="config gpio-poweroff",
                   name="dtoverlay=gpio-poweroff,gpio_pin",
                   value="26,active_low=0", config=config)
        # dtoverlay=gpio-ir,gpio_pin=13
        set_config(msg="config gpio-ir",
                   name="dtoverlay=gpio-ir,gpio_pin",
                   value="13", config=config)
    #
    print('create WorkingDirectory')
    do(msg="create dir",
       cmd='mkdir -p /opt/%s' % __app_name__ +
       ' && chmod -R 774 /opt/%s' % __app_name__ + ' && chown %s:%s /opt/%s' %
       (username, username, __app_name__))
    #
    if "--skip-auto-startup" not in options:
        # /etc/systemd/system is the place for locally installed units;
        # /usr/lib/systemd/system (used up to 2.2.9) belongs to .deb packages
        # and is wiped by distribution upgrades
        do(msg='copy service file',
           cmd='cp -rpf ./bin/%s.service /etc/systemd/system/%s.service' %
           (__app_name__, __app_name__) +
           ' && chmod 644 /etc/systemd/system/%s.service' % __app_name__)
        # remove the unit a 2.2.x install left in the package directory,
        # otherwise two units with the same name shadow each other
        do(msg='remove legacy service file',
           cmd='rm -f /usr/lib/systemd/system/%s.service' % __app_name__)
    # the repository ships an empty "log" placeholder, keep the installed
    # log file instead of truncating it on every upgrade
    do(msg='copy bin file',
       cmd='cp -rpf ./bin/%s /usr/local/bin/%s' %
       (__app_name__, __app_name__) +
       r" && find ./%s -maxdepth 1 -type f ! -name log -exec cp -pf {} /opt/%s/ \;"
       % (__app_name__, __app_name__) +
       ' && touch /opt/%s/log' % __app_name__)
    do(msg="add excutable mode for bin file",
       cmd='chmod +x /usr/local/bin/%s' % __app_name__ +
       ' && chmod -R 774 /opt/%s' % __app_name__ +
       ' && chown -R %s:%s /opt/%s' % (username, username, __app_name__))
    # never clobber a config the user has already tuned
    if os.path.exists(config_file):
        print(f" - keep existing config file {config_file}... Done")
    else:
        do(msg='copy config file', cmd=f'cp -rpf ./config.txt {config_file}')
    #
    if "--skip-auto-startup" not in options:
        do(msg='enable the service to auto-start at boot',
           cmd='systemctl daemon-reload' +
           f' && systemctl enable {__app_name__}.service')
    #
    do(msg='run the service', cmd='pironman restart')

    if warnings:
        print('\n\033[1;33mSome optional steps were skipped:\033[0m')
        for warning in warnings:
            print(warning)

    if len(errors) == 0:
        print("Finished.")
        if "--skip-reboot" not in options:
            print(
                "\033[1;32mWhether to restart for the changes to take effect(Y/N):\033[0m"
            )
            while True:
                key = input()
                if key == 'Y' or key == 'y':
                    print(f'reboot')
                    run_command('reboot')
                elif key == 'N' or key == 'n':
                    print(f'exit')
                    sys.exit(0)
                else:
                    continue
        else:
            print(
                "\033[1;32mPlease reboot for the changes to take effect.\033[0m"
            )
            sys.exit(0)
    else:
        print('\n\n\033[1;35mError happened in install process:\033[0m')
        for error in errors:
            print(error)
        print(
            "Try to fix it yourself, or contact service@sunfounder.com with this message"
        )
        sys.exit(1)


if __name__ == "__main__":
    try:
        install()
    except KeyboardInterrupt:
        print("\n\nCanceled.")
    finally:
        sys.stdout.write(' \033[1D')
        sys.stdout.write('\033[?25h')  # cursor visible
        sys.stdout.flush()
