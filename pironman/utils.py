#!/usr/bin/env python3
import os
import subprocess
import sys
import time
from app_info import log_file

LOG_MAX_BYTES = 1024 * 1024

def _rotate_log():
    '''Keep the log from growing without bound (one .old generation).'''
    try:
        if os.path.getsize(log_file) > LOG_MAX_BYTES:
            os.replace(log_file, log_file + '.old')
    except OSError:
        pass

def log(msg:str=None,level='DEBUG',end='\n',flush=False,timestamp=True):
    if timestamp == True:
        _time = time.strftime("%y/%m/%d %H:%M:%S", time.localtime())
        ct = time.time()
        _msecs = '%03d '%((ct - int(ct)) * 1000)
        line = '%s,%s[%s] %s'%(_time,_msecs,level,msg)
    else:
        line = '%s'%msg
    # stdout goes to the journal when started by systemd
    print(line, end=end, flush=flush, file=sys.stdout)
    try:
        _rotate_log()
        with open(log_file,'a+') as f:
            print(line, end=end, flush=flush, file=f)
    except OSError:
        # a missing or read-only log file must never kill the service
        pass

def run_command(cmd):
    '''
    Run cmd in a shell and return (exit status, combined output).

    Up to 2.2.9 the status came from Popen.poll() without waiting, which
    returns None instead of an exit code, so every "if status == 0" check
    silently failed.
    '''
    try:
        p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode(errors='replace')
    except Exception as e:
        return -1, str(e)
