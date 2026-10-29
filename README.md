# SunFounder Pironman for Raspberry Pi
This repository is for SunFounder Pironman - A PC case for Raspberry Pi. you can buy it on [our website](https://www.sunfounder.com/products/raspberry-pi-4-case), or search sunfounder in Amazon.

Quick Links:

- [SunFounder Pironman for Raspberry Pi](#sunfounder-pironman-for-raspberry-pi)
  - [About pironman:](#about-pironman)
  - [Install](#install)
  - [Usage](#usage)
  - [Update](#update)
  - [Compatible Systems](#compatible-systems)
  - [About SunFounder](#about-sunfounder)
  - [License](#license)
  - [Contact us](#contact-us)

<a id="about_pironman"></a>
## About pironman:
<div align="center">
    <img src="https://github.com/sunfounder/pironman/blob/docs/docs/source/img/pironman.png" width="50%"  align="center" title="pironman"/>
    &nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp&nbsp
    <!-- <img src="./img/Nano_Sloth_V2.png" width="212" height="261" align="center" title="Nano_Sloth_V2"/> -->
</div>
The pironman is used on Raspberry Pi to control OLED to display system status information, control cooling fan and RGB light strip and so on.


<a id="update"></a>

## Install
- For systems that don't have git and python3 pre-installed you need to install them first
  ```bash
  sudo apt-get update
  sudo apt-get install git python3 -y
  ```
- Execute the installation script
  ```bash
  cd ~
  git clone -b v2.0 https://github.com/sunfounder/pironman.git
  cd ~/pironman
  sudo python3 install.py
  ```
- Reboot when the installer asks for it. I2C and SPI are switched on in
  `/boot/firmware/config.txt`, and those only take effect after a restart.

All dependencies come from apt, so no compiler is needed. Only driving the
strip from the PWM (GPIO12) or PCM (GPIO21) pin requires the `rpi-ws281x`
library, which is built on request:
```bash
sudo python3 install.py --with-ws281x
```

## Usage
```bash
Usage:
  pironman <OPTION> <input>

Options:
  start            start pironman service
  stop             stop pironman service
  restart          restart pironman service
  status           show service status
  log              follow the service log
  -h,--help        help, show this help
  -c,--check       show all configurations
  -a,--auto        [ on ],enable auto-start at boot
                   [ off ], disable auto-start at boot
  -u,--unit        [ C/F ], unit of the temperature shown on the screen,
                   C or F (Celsius/Fahrenheit). The fan threshold stays
                   in celsius.
  -f,--fan         [ temp ], Temperature at which the fan switches on,
                   in celsius (default 50),in range (30 ~ 80)
  -al,--always_on  [on/true/off/false], whether the screen is always on,
                   default False
  -s,--staty_time  [time], screen display duration in second,
                   in second, default 60
  -re,--rgb-enable [on/true/off/false], rgb strip enable
  -rw,--rgb_sw     [on/true/off/false], rgb strip switch
  -rs,--rgb_style  rgb strip display style, default: breath,
                   in [breath / static / leap / flow / raise_up /
                   colorful / colorful_static / colorful_leap]
  -rc,--rgb_color  [(HEX)color], set the color of rgb strip,
                   default: 0a1aff
  -rb,--rgb_speed  [speed], rgb blink speed (0 ~ 100, default 50)
  -pwm,--rgb_pwm   [frequency], rgb signal frequency (400 ~ 1600, default
                   1000 kHz), only used by the ws281x backend
  -rp,--rgb_pin    [pin], rgb signal pin, could be [10 / spi/ SPI / 12 / pwm/ PWM] or
                   [21 / pcm / PCM], default 10
  -bk,--rgb_backend [auto/spi/ws281x], how the WS2812 signal is generated,
                   default auto
  -F,--foreground  run in foreground

```
## Update
https://github.com/sunfounder/pironman/blob/master/CHANGELOG.md

## Compatible Systems
Systems that passed the test on the Raspberry Pi 4B:
<font size=1>
<!-- https://apps.timwhitlock.info/emoji/tables/unicode#block-6c-other-additional-symbols -->
  | system |   is compatible ? |
  | :---   | :---:   |
  | Raspberry Pi OS - Trixie (64 bit), kernel 6.6 ... 6.18 | &#x2705; (since 2.3.0) |
  | Raspberry Pi OS - Bookworm (32/64 bit) | &#x2705; |
  | Raspberry Pi OS - Bullseye (32/64 bit) | &#x2705; |
  | Raspberry Pi OS lite - Bullseye (32/64 bit) | &#x2705; |
  | Raspberry Pi OS - Buster (32 bit) | &#x2705; |
  | Raspberry Pi OS lite - Buster (32 bit) | &#x2705; |
  | Ubuntu Server 22.10 (32/64 bit) | &#x2705; |
  | Ubuntu Desktop 22.10 (64 bit) | &#x2705; |
  | Kali Linux (32/64 bit) | &#x2705; |
  | OSMC | &#x2705; |
  | RetroPie | &#x2705; |
  | OctoPi | &#x2705; |
  | Homebridge | &#x2705; |
  | LibreELEC | &#x274C; |
  | <a href="https://pironman-v2.readthedocs.io/en/latest/home_assistant.html">HassOS</a> | &#x2705; |
</font>

## How the RGB strip is driven

The WS2812 strip needs a tightly timed 800 kHz signal. There are two ways
to produce it, selected with `rgb_backend`:

- **`spi`** (default on GPIO10) bit-bangs the waveform through the kernel
  SPI driver: every LED bit becomes three SPI bits at 2.4 MHz, so a `0` is
  `100` and a `1` is `110`. It only needs `python3-spidev`, works on any
  kernel and does not touch `/dev/mem`. `core_freq=500` and
  `core_freq_min=500` are set in the boot config because the Pi 4 derives
  the SPI clock from the GPU core clock, which would otherwise drop to
  200 MHz when idle and distort the timing.
- **`ws281x`** uses the `rpi-ws281x` C library and is required for GPIO12
  (PWM) and GPIO21 (PCM). It maps `/dev/mem`, claims a DMA channel and has
  to be compiled, so install it with `sudo python3 install.py --with-ws281x`.

## Troubleshooting

```bash
sudo pironman status      # is the service running?
sudo pironman log         # live log
sudo pironman -c          # current configuration
```

- **Screen stays dark.** The log says which bus it tried. Check that I2C is
  on (`ls /dev/i2c-1`) and that the panel answers:
  `sudo i2cdetect -y 1` should show a device at `3c`.
- **LEDs stay dark.** Check that SPI is on (`ls /dev/spidev0.0`). If
  `rgb_pin` is 12 or 21 the `rpi-ws281x` library has to be installed.
- **Nothing happens at all after an upgrade.** I2C and SPI only come up
  after a reboot.
- **The power key seems stuck.** The log prints the idle level at startup
  (`power_key init success (pull=down, idle value=1)`). It has to read `1`
  while the key is not pressed; if it reads `0`, set
  `power_key_pull = up` in `/opt/pironman/config.txt`.
- **Running from a checkout** without disturbing the installed copy:
  ```bash
  sudo PIRONMAN_CONFIG=/tmp/pironman.conf PIRONMAN_LOG=/tmp/pironman.log \
       python3 pironman/main.py
  ```

<a id="about_sunfounder"></a>
## About SunFounder
SunFounder is a company focused on STEAM education with products like open source robots, development boards, STEAM kit, modules, tools and other smart devices distributed globally. In SunFounder, we strive to help elementary and middle school students as well as hobbyists, through STEAM education, strengthen their hands-on practices and problem-solving abilities. In this way, we hope to disseminate knowledge and provide skill training in a full-of-joy way, thus fostering your interest in programming and making, and exposing you to a fascinating world of science and engineering. To embrace the future of artificial intelligence, it is urgent and meaningful to learn abundant STEAM knowledge.

<a id="license"></a>
## License
This is the code for SunFounder PiArm.
This program is free software; you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation; either version 2 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with this program; if not, write to the Free Software Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

piarm comes with ABSOLUTELY NO WARRANTY; for details run ./show w. This is free software, and you are welcome to redistribute it under certain conditions; run ./show c for details.

SunFounder, Inc., hereby disclaims all copyright interest in the program 'piarm' (which makes passes at compilers).

Mike Huang, 21 August 2020

Mike Huang, Chief Executive Officer

Email: service@sunfounder.com

<a id="contact_us"></a>
## Contact us
website:
    www.sunfounder.com

E-mail:
    service@sunfounder.com
