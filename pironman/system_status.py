import os
import socket
import shutil
import psutil

# Keys psutil may use for the SoC sensor, newest kernels first.
CPU_TEMP_KEYS = ('cpu_thermal', 'coretemp', 'soc_thermal', 'bcm2835_thermal')
THERMAL_ZONE = '/sys/class/thermal/thermal_zone0/temp'


def get_cpu_temperature():
    '''
    Return the CPU temperature in degrees celsius.

    psutil is tried first, then the thermal zone in sysfs, which exists on
    every Raspberry Pi kernel and needs no library at all. Returning 0.0 on
    failure keeps the fan logic running instead of crashing the service.
    '''
    try:
        temps = psutil.sensors_temperatures()
        for key in CPU_TEMP_KEYS:
            if key in temps and temps[key]:
                return temps[key][0].current
        # unknown key name: take whatever the first sensor reports
        for entries in temps.values():
            if entries:
                return entries[0].current
    except Exception:
        pass
    try:
        with open(THERMAL_ZONE) as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def get_ram_info():
    '''
    Return RAM information in GiB plus the used percentage.
    '''
    memory_info = psutil.virtual_memory()
    memory = {
        'total': memory_info.total / 1024 / 1024 / 1024,
        'percent': memory_info.percent,
        'used': memory_info.used / 1024 / 1024 / 1024,
    }
    return memory

def get_cpu_usage():
    '''
    Return % of CPU used as a character string
    '''
    return psutil.cpu_percent()

def get_disk_info():
    total, used, free = shutil.disk_usage("/")
    disk = {
        'total': round(total / (2**30), 2),
        'used': round(used / (2**30), 2),
        'free': round(free / (2**30), 2),
        'percent': round(used/ total * 100, 2),
    }
    return(disk)

# IP address
def getIP():
    '''
    Return {interface: IPv4 address} for every up, non-loopback interface.

    Read straight from psutil instead of shelling out to "ifconfig": that
    binary comes from net-tools, which is deprecated and not installed by
    default on Debian trixie, and its output is locale dependent. Virtual
    bridges created by docker/libvirt are skipped so the OLED keeps showing
    the address of the real network interface.
    '''
    skip_prefixes = ('lo', 'docker', 'br-', 'veth', 'virbr', 'tailscale',
                     'zt', 'cni', 'flannel')
    IPs = {}
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception:
        return IPs
    for nic, addresses in addrs.items():
        if nic.startswith(skip_prefixes):
            continue
        if nic in stats and not stats[nic].isup:
            continue
        for addr in addresses:
            if addr.family == socket.AF_INET and addr.address:
                IPs[nic] = addr.address
                break
    return IPs

def getMAC():
    MACs = {}
    NIC_devices = []
    NIC_devices = os.listdir('/sys/class/net/')
    # print(NIC_devices)
    for NIC in NIC_devices:
        if NIC == 'lo':
            continue
        try:
            with open('/sys/class/net/' + NIC + '/address', 'r') as f:
                MACs[NIC] = f.readline().strip()
        except:
            continue
        # print(NIC, MACs[NIC])

    return MACs



if __name__ == '__main__':
    # CPU informatiom
    cpu_temp = get_cpu_temperature()
    cpu_usage = get_cpu_usage()
    # RAM information
    ram_info = get_ram_info()
    ram_total = ram_info['total']
    ram_used = ram_info['used']
    ram_percent = ram_info['percent']
    # Disk information
    disk_info = get_disk_info()
    disk_total = disk_info['total']
    disk_used = disk_info['used']
    disk_percent = disk_info['percent']
    # IP
    IPs = getIP()
    wlan0 = None
    eth0 = None
    if 'wlan0' in IPs and IPs['wlan0'] != None and IPs['wlan0'] != '':
        wlan0 = IPs['wlan0']
    if 'eth0' in IPs and IPs['eth0'] != None and IPs['eth0'] != '':
        eth0 = IPs['eth0']

    print(f'CPU Temperature = {cpu_temp} \'C')
    print(f'CPU Use = {cpu_usage} %')
    print('')
    print(f'RAM Total = {ram_total} GB')
    print(f'RAM Used = {ram_used} GB')
    print(f'RAM Usage = {ram_percent} %')
    print('')
    print(f'DISK Total Space = {disk_total} GB')
    print(f'DISK Used Space = {disk_used} GB')
    print(f'DISK Used Percentage = {disk_percent} %')
    print('')
    print('all IPs : %s'%IPs)
    print('wlan0 : %s'%wlan0)
    print('eth0 : %s'%eth0)
    print('')
