"""Gmail notification setup without PowerShell execution-policy changes."""
import argparse
import ctypes
from ctypes import wintypes
import getpass
import json
import os
from pathlib import Path
import re
import sys
import warnings

from core import send_notice


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    """Windows DPAPI, current-user scope; never writes cleartext to disk."""
    if os.name != 'nt':
        raise RuntimeError('Windows is required for encrypted credential storage.')
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source = Blob(len(data), buffer)
    result = Blob()
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError('Windows credential encryption/decryption failed.')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def credential_path():
    return Path(os.environ['LOCALAPPDATA']) / 'XuanenCourtBot' / 'gmail.dpapi'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup', action='store_true')
    parser.add_argument('--subject', default='Court bot notification test')
    parser.add_argument('--body', default='Email delivery is configured. Automatic court booking is not enabled yet.')
    args = parser.parse_args()
    config = json.loads(Path(__file__).with_name('config.json').read_text(encoding='utf-8'))
    path = credential_path()
    if args.setup:
        print('Gmail: ' + config['sender_email'])
        print('Use a 16-letter Gmail APP PASSWORD, not your normal Google password.')
        print('Input is hidden. A test email will be sent, then the password will be encrypted locally.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = re.sub(r'\s+', '', getpass.getpass('Gmail app password: '))
        if not re.fullmatch(r'[a-zA-Z]{16}', password):
            print('Expected a 16-letter Gmail app password. Nothing was saved or sent.')
            return 1
        encrypted = protect(password.encode('utf-8'))
    else:
        if not path.is_file():
            print('Email is not configured. Run with --setup first.')
            return 1
        saved = json.loads(protect(path.read_bytes(), decrypt=True).decode('utf-8'))
        if saved['sender'] != config['sender_email']:
            print('Sender changed. Run --setup again.')
            return 1
        password = saved['password']
    try:
        send_notice(config['smtp_host'], config['smtp_port'], config['sender_email'],
                    password, config['notification_email'], args.subject, args.body)
    except Exception:
        print('Email failed. Check the network, Gmail app password and account settings. No new credentials saved.')
        return 1
    if args.setup:
        # Bind the credential to the sender and encrypt with current-user DPAPI.
        encrypted = protect(json.dumps({'sender': config['sender_email'], 'password': password}).encode('utf-8'))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(encrypted)
        temporary.replace(path)
    print('SMTP accepted the email. Check your inbox and spam folder for delivery.')
    if config.get('enabled'):
        print('Booking schedule is enabled. This email command does not create a booking.')
    else:
        print('Automatic booking remains disabled until setup is completed in the chat.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled.')
        sys.exit(1)
    except Exception:
        print('Setup failed. Run in an interactive Windows terminal under your normal user account.')
        sys.exit(1)
