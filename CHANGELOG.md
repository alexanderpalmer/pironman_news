# Change Log

## [2.3.0] - 2026-10-29

Port to Debian 13 "trixie" / kernel 6.6+ / Python 3.13. The 2.2.9 version
no longer installs or runs on trixie.

### Fixed

- Installation aborted on trixie: `libfreetype6-dev` does not exist there
  any more (it is `libfreetype-dev`), so `apt install` failed
- Installation fought PEP 668: `/usr` is marked EXTERNALLY-MANAGED, so
  `pip3 install pillow/psutil/requests` either refused to run or shadowed
  the distribution packages. All runtime dependencies are now installed
  from apt (`python3-pil`, `python3-psutil`, `python3-requests`,
  `python3-smbus2`, `python3-spidev`, `python3-lgpio`) and no compiler is
  needed for the default setup
- `rpi-ws281x` is no longer required: the LED strip on the default pin
  GPIO10 is driven through the kernel SPI driver (see "Added"). The library
  is still used for the PWM (12) and PCM (21) pins and can be built with
  `sudo python3 install.py --with-ws281x`
- `run_command()` read the exit status with `Popen.poll()` without waiting,
  which returns `None` instead of a code, so every `if status == 0` check
  silently failed and the kernel/OS/PCB information never reached the log
- The systemd unit had a trailing comment on the `After=` line. systemd
  does not allow that and parsed the words of the comment as unit names
- The unit used `Type=forking` around a shell script that backgrounded
  python with `&`, so systemd never learned the real PID and could not
  stop or restart the service reliably. It is now `Type=simple` and runs
  `main.py` directly, so `systemctl stop` performs a clean shutdown
- `pironman log` showed nothing while the service was running: journald is
  a pipe and not a terminal, so python block-buffered stdout and the log
  lines only reached the journal when the process exited. The unit now sets
  `Environment=PYTHONUNBUFFERED=1`
- `pironman stop` built its kill list with `ps aux | grep $main | awk
  '{print $2}'`, which also matched the `grep` itself and any unrelated
  process whose command line contained the path
- The exit handler did all its work in a single `try`/`except`: when no
  power key was present the very first line raised `NameError` and the
  screen, the fan and the LEDs were never switched off. Every resource is
  now released on its own
- Several crashes when hardware is missing: `oled.on()` was called even
  though OLED initialization had failed
- `pironman -u F` made the fan run non-stop, because the celsius threshold
  `fan_temp` was compared against the fahrenheit reading. `temp_unit` now
  only selects the unit shown on the screen
- A missing or new config key made the whole config file be overwritten
  with defaults, wiping every user setting. Missing keys are now appended
  individually
- `Config.set()` in `install.py` matched keys as a plain substring over the
  whole file, so setting `core_freq` could destroy an existing
  `core_freq_min` line, and keys inside `[pi5]`/`[cm4]` blocks could be
  rewritten although they do not apply to this board
- `Config.remove()` deleted items from the list it was iterating over
- The IP address was read by parsing `ifconfig` output. net-tools is
  deprecated and not installed by default on trixie, and the output is
  locale dependent; psutil is used instead
- The CPU temperature came from a single hard coded psutil sensor key; it
  now falls back through the known key names to the sysfs thermal zone
- Waiting for the power key to be released was a busy loop that pegged a
  CPU core at 100%
- The RGB animation thread kept writing to the strip while the shutdown
  code was clearing it; the thread is now stopped first and reacts
  immediately
- The service unit was installed to `/usr/lib/systemd/system`, which
  belongs to .deb packages and is overwritten by distribution upgrades. It
  now goes to `/etc/systemd/system`, and a unit left there by 2.2.x is
  removed
- Reinstalling overwrote `/opt/pironman/config.txt` and truncated the log

### Added

- `rgb_backend` option (`auto` / `spi` / `ws281x`). The new `spi` backend
  clocks the WS2812 protocol out through the kernel SPI driver on GPIO10,
  encoding each LED bit as three SPI bits at 2.4 MHz. It needs no compiler,
  no `/dev/mem` and no DMA channel, which is what makes the strip work on
  current kernels
- `power_key_pin`, `power_key_pull` and `fan_pin` are configurable
- `pironman status` and `pironman log` subcommands
- `install.py --with-ws281x` to build the library for the PWM/PCM pins
- Range and value checks for `rgb_color`, `fan_temp`, `rgb_style`,
  `rgb_backend` and `temp_unit`
- Clear, actionable messages when I2C or SPI is not enabled in
  `/boot/firmware/config.txt`
- `install.py` backs up the boot config to `config.txt.pironman-bak`
- Log rotation at 1 MiB
- `PIRONMAN_CONFIG` / `PIRONMAN_LOG` environment overrides, so the program
  can be run from a checkout without touching the installed copy

### Changed

- The OLED frame is sent in a single I2C transaction via smbus2 instead of
  64 block writes
- The I2C bus is detected at runtime instead of being hard coded to bus 1,
  and the HDMI buses (20/21) are ignored
- `i2c.scan()` probes the bus directly instead of parsing `i2cdetect` output
- Startup logs the power key idle level, which makes a wrong
  `power_key_pull` setting obvious

## [2.2.9] - 2024-7-23

### Fixed

- Fix bug of gpiozero Button not working on kernel 6.6.x

## [2.2.8] - 2024-3-27

### Added

- Add rgb styles : static, colorful_static

## [2.2.7] - 2024-3-15

### Changed

- Change the default path of boot config to '/boot/firmware/config.txt'

## [2.2.6] - 2024-2-20

### Optimized

- Optimize the exit handler
- Optimize the getting of the system status

## [2.2.5] - 2024-2-19

### Fixed

- Fix the bug that the shutdown button is invalid when OLED initialization fails
- Fix the bug of getting CPU usage on bookworm system

### Optimized

- Optimize the exit handler (clean oled, close rgb strip)

## [2.2.4] - 2023-12-20

### Fixed

- Fix bug of get CPU temperature on bookworm system
- Fix bug of not error info returned when running installation

## [2.2.3] - 2023-9-4

### Fixed

- Fix bug of determining whether the run_command is executed successfully in the install.py

## [2.2.2] - 2023-8-31

### Fixed

- Fix the bug that the pironman script did not kill the process correctly
- Fix the bug of print input parameters

### Added

- Add rgb style ：'colorful_leap'

## [2.2.1] - 2023-7-28

### Changed

- merge with test branch with hassio pluggin support

### Fixed

- Fix bug of reset config file

## [2.2.0] - 2023-7-28

### Changed

- Change config.txt path to '/opt/pironman/config.txt' to solve
the problem that the user name cannot be obtained correctly

### Fixed

- Fix bug of reset config file

## [2.1.2] - 2023-7-14

### Fixed

- Fix the bug of rgb flashing in confusion when use pwm io and the
"dtparam=audio=on"

## [2.1.1] - 2023-7-12

### Fixed

- Fix the bug of the cursor does not display when the program terminates

## [2.1.0] - 2023-7-10

### Changed

Add the option "--break-system-packages" for "pip3" to "install.py" to compatibile the Ubuntu 23.0 PEP668 restrictions
Add tip "Run with sudo" for "install.py"

## [2.0.1] - 2023-7-6

### Changed

- Remove control of the "dtparam=audio" in /boot/config.txt

## [2.0.0] - 2023-6-1

### Optimized

- Compatible with python 3.10
- Optimize option command

### Added

- Add settings of rgb pin
- Add colorful_leap style

## [1.5.0] - 2023-4-7

### Modified

- Now the program is compatible with multiple systems based on debian, including Ubuntu, Kali, OSMC, RetroPie, OctoPi, Homebridge

### Optimized

- Add working_tip while installing

### Changed

- Change getCPUtemperature() fuction to compatible some othee systems

## [1.4.0] - 2023-3-23

### Changed

- Change rgb pwm default frequency to 1000 kHz, to compatible different LED components
- Now the oled initialization fails and the program won't terminate

### Added

- Add command to set pwm frequency

## [1.3.0] - 2023-2-24

### Changed

- Disable "dtparam=audio" in the /boot/config.txt
- Auto config "gpio-poweroff" and "gpio-ir" in the /boot/config.txt
- Cancel reinit for ws2812

### Added

- Add Kernel info, OS version, PCB info in the log

## [1.2.8] - 2023-2-21

### Changed

- Change ws2812 Adafruit_NeoPixel to PixelStrip

## [1.2.7] - 2023-2-14

### Fixed

- Fix the bug of showing ip address when docker is installed on the system

## [1.2.6] - 2023-1-29

### Fixed

- Fix the bug of install process and get system status in different system languages

## [1.2.4] - 2023-1-6

### Fixed

- Fix the bug of getting CPU useage rate when the system language is French

## [1.2.3] - 2022-12-27

### Fixed

- Fix the bug that the number of files overflowed when reinitializing the ws2812_rgb object

## [1.2.2] - 2022-12-22

### Fixed

- Fix the bug of rgb wrongly flash when running "pironman start"

## [1.2.1] - 2022-12-21

### Fixed

- Fix the bug of rgb init

## [1.2.0] - 2022-12-15

### Fixed

- Fix the problem of rgb wrongly flash caused by occupied rgb pwm pin

### Added

- Add "colorful" style of rgb LEDs

## [1.1.0] - 2022-5-12

### Changed

- Change the project name to "Pironman"

### Fixed

- Fix the data disorder of ws2812 RGB lights after startup

## [1.0.0] - 2022-3-23

### Added

- Add changelog.md
- Add Fahrenheit temperature unit
- Add get more network card ips, not just wlan0 or eth0
- Add shell command to view all configuration parameters
- Add shell command to change temperature unit

### Fixed

- Fix bug of shell command

### Optimized

- Optimize code redundancy
- Catch more error messages

## [0.0.3] - 2022-1-28

### Fixed

- Fix bug of log
- Fix bug of get system cpu usage

### Optimized

- Optimize code redundancy

## [0.0.2] - 2022-1-27

### Fixed

- Fix bug of auto_start at boot
- Fix bug of temperature controlled fan
- Fix bug of wrong username obtained

### Optimized

- Optimize code redundancy

## [0.0.1] - 2022-1-18

### Basic function

- Oled system status display
- Auto start at boot
- Shell commands interaction
- RGB strip control
- Cooling Fan Control
- ...
