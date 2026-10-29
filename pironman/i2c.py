import os
import re
from time import sleep

from utils import log, run_command

# smbus2 is pure python, actively maintained and ships with Debian trixie
# (python3-smbus2). It also exposes i2c_msg, which lets the OLED buffer go
# out in a single transaction instead of 64 block writes. The classic
# python3-smbus binding stays as a fallback.
try:
    from smbus2 import SMBus, i2c_msg
    _HAVE_I2C_MSG = True
except ImportError:
    from smbus import SMBus
    i2c_msg = None
    _HAVE_I2C_MSG = False

# On the Pi 4 the buses numbered 20 and 21 are the HDMI DDC channels, they
# never carry the Pironman OLED. /dev/i2c-1 is the GPIO2/GPIO3 header bus
# that "dtparam=i2c_arm=on" creates.
PREFERRED_BUSES = (1, 0)
IGNORED_BUSES = (20, 21, 22)


def available_buses():
    '''Numbers of all /dev/i2c-* buses that can carry header devices.'''
    buses = []
    try:
        for name in os.listdir('/dev'):
            m = re.fullmatch(r'i2c-(\d+)', name)
            if m:
                num = int(m.group(1))
                if num not in IGNORED_BUSES:
                    buses.append(num)
    except OSError:
        pass
    return sorted(buses)


def pick_bus():
    '''
    Choose the I2C bus to talk to the OLED on.

    Raises a FileNotFoundError with an actionable message when the ARM I2C
    bus is missing, which is the normal state of a fresh Debian trixie
    image: "dtparam=i2c_arm=on" is commented out in /boot/firmware/config.txt
    so only the HDMI buses exist.
    '''
    env = os.environ.get('PIRONMAN_I2C_BUS')
    if env:
        return int(env)
    buses = available_buses()
    for num in PREFERRED_BUSES:
        if num in buses:
            return num
    if buses:
        return buses[0]
    raise FileNotFoundError(
        "no usable /dev/i2c-* bus found. Enable I2C with "
        "'sudo raspi-config nonint do_i2c 0' or add 'dtparam=i2c_arm=on' to "
        "/boot/firmware/config.txt and reboot.")


class I2C():
    MASTER = 0
    SLAVE  = 1
    RETRY = 5

    def __init__(self, bus=None, *args, **kargs):
        super().__init__()
        self._bus = pick_bus() if bus is None else bus
        self._smbus = SMBus(self._bus)
        log(f'i2c bus: {self._bus} (smbus2: {_HAVE_I2C_MSG})')

    @property
    def bus(self):
        return self._bus

    def close(self):
        try:
            self._smbus.close()
        except Exception:
            pass

    def _i2c_write_byte(self, addr, data):                      # i2C write function
        return self._smbus.write_byte(addr, data)

    def _i2c_write_byte_data(self, addr, reg, data):
        return self._smbus.write_byte_data(addr, reg, data)

    def _i2c_write_word_data(self, addr, reg, data):
        return self._smbus.write_word_data(addr, reg, data)

    def _i2c_write_i2c_block_data(self, addr, reg, data):
        return self._smbus.write_i2c_block_data(addr, reg, data)

    def write_block_large(self, addr, reg, data):
        '''
        Write reg followed by an arbitrary amount of data.

        With smbus2 this is one I2C_RDWR transaction, which is what makes a
        full 1024 byte OLED frame cheap. Without it the caller has to fall
        back to chunked write_i2c_block_data() calls.
        '''
        if not _HAVE_I2C_MSG:
            raise NotImplementedError('smbus2 required for large block writes')
        msg = i2c_msg.write(addr, bytes([reg]) + bytes(data))
        self._smbus.i2c_rdwr(msg)

    @property
    def has_large_block_write(self):
        return _HAVE_I2C_MSG

    def _i2c_read_byte(self, addr):                             # i2C read functions
        return self._smbus.read_byte(addr)

    def _i2c_read_i2c_block_data(self, addr, reg, num):
        return self._smbus.read_i2c_block_data(addr, reg, num)

    def is_ready(self, addr):
        addresses = self.scan()
        if addr in addresses:
            return True
        else:
            return False

    def scan(self):
        '''
        Scan the bus for devices.

        Probing is done with smbus itself instead of parsing i2cdetect
        output, so the scan no longer depends on i2c-tools being installed
        or on its output format and locale.
        '''
        addresses = []
        for addr in range(0x03, 0x78):
            try:
                self._smbus.write_quick(addr)
                addresses.append(addr)
            except OSError:
                continue
        return addresses

    def send(self, send, addr, timeout=0):                      # sending data. `send`: data to be sent, `addr`: receiver's address 
        if isinstance(send, bytearray):
            data_all = list(send)
        elif isinstance(send, int):
            data_all = []
            d = "{:X}".format(send)
            d = "{}{}".format("0" if len(d)%2 == 1 else "", d)  
            # print(d)
            for i in range(len(d)-2, -1, -2):                   # taking two chars in each iteration from right to left 
                tmp = int(d[i:i+2], 16)                         # convert 2-digit decimal to hex
                # print(tmp)
                data_all.append(tmp)                            
            data_all.reverse()
        elif isinstance(send, list):
            data_all = send
        else:
            raise ValueError("send data must be int, list, or bytearray, not {}".format(type(send)))

        if len(data_all) == 1:                    
            data = data_all[0]
            self._i2c_write_byte(addr, data)
        elif len(data_all) == 2:                   
            reg = data_all[0]
            data = data_all[1]
            self._i2c_write_byte_data(addr, reg, data)
        elif len(data_all) == 3:                    
            reg = data_all[0]
            data = (data_all[2] << 8) + data_all[1]
            self._i2c_write_word_data(addr, reg, data)
        else:
            reg = data_all[0]
            data = list(data_all[1:])
            self._i2c_write_i2c_block_data(addr, reg, data)

    def recv(self, recv, addr=0x00, timeout=0):                 # receive data
        if isinstance(recv, int):                               # convert `recv` to bytearray
            result = bytearray(recv)
        elif isinstance(recv, bytearray):
            result = recv
        else:
            return False
        for i in range(len(result)):
            result[i] = self._i2c_read_byte(addr)
        return result

    def mem_write(self, data, addr, memaddr, timeout=5000, addr_size=8): # memaddr match to chn
        if isinstance(data, bytearray):
            data_all = list(data)
        elif isinstance(data, list):
            data_all = data
        elif isinstance(data, int):
            data_all = []
            data = "%x"%data
            if len(data) % 2 == 1:
                data = "0" + data
            # print(data)
            for i in range(0, len(data), 2):
                # print(data[i:i+2])
                data_all.append(int(data[i:i+2], 16))
        else:
            raise ValueError("memery write require arguement of bytearray, list, int less than 0xFF")
        # print(data_all)
        self._i2c_write_i2c_block_data(addr, memaddr, data_all)

    def mem_read(self, data, addr, memaddr, timeout=5000, addr_size=8):  # read data
        if isinstance(data, int):
            num = data
        elif isinstance(data, bytearray):
            num = len(data)
        else:
            return False
        result = bytearray(self._i2c_read_i2c_block_data(addr, memaddr, num))
        return result

    def readfrom_mem_into(self, addr, memaddr, buf):
        buf = self.mem_read(len(buf), addr, memaddr)
        return buf

    def writeto_mem(self, addr, memaddr, data):
        self.mem_write(data, addr, memaddr)
