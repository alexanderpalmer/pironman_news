import os
import pwd

__app_name__ = 'pironman'
__version__ = '2.3.0'


def _get_username():
    '''
    Determine the name of the user that owns the installation.

    os.getlogin() needs a controlling terminal and raises OSError when the
    program is started by systemd, so it can only be a first guess. Under
    sudo the original user is in SUDO_USER, and as a last resort the owner
    of /home/* or the first regular login account is used. "who -m" (used
    up to 2.2.9) returns nothing under systemd and left the name empty.
    '''
    for name in (os.environ.get('SUDO_USER'), os.environ.get('PIRONMAN_USER')):
        if name:
            return name
    try:
        return os.getlogin()
    except Exception:
        pass
    # owner of the first regular home directory
    try:
        homes = sorted(os.listdir('/home'))
        for home in homes:
            try:
                return pwd.getpwuid(os.stat(f'/home/{home}').st_uid).pw_name
            except Exception:
                continue
    except Exception:
        pass
    # first regular login account
    try:
        for entry in pwd.getpwall():
            if 1000 <= entry.pw_uid < 65534:
                return entry.pw_name
    except Exception:
        pass
    return 'root'


username = _get_username()

# PIRONMAN_CONFIG / PIRONMAN_LOG let the program run from a checkout
# without touching the installed copy under /opt.
config_file = os.environ.get('PIRONMAN_CONFIG',
                             f'/opt/{__app_name__}/config.txt')
log_file = os.environ.get('PIRONMAN_LOG', f'/opt/{__app_name__}/log')
