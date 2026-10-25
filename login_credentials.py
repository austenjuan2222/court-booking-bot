"""Local court credential setup. Internal browser pipe mode must never be logged."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import warnings

from send_notice import protect

ORIGIN = 'https://fe.xuanen.com.tw'


def credential_path():
    return Path(os.environ['LOCALAPPDATA']) / 'XuanenCourtBot' / 'court.dpapi'


def save_credentials(username, password, destination=None):
    if not username.strip() or not password:
        raise ValueError('Empty credentials')
    path = destination or credential_path()
    payload = json.dumps({'origin': ORIGIN, 'username': username.strip(),
                          'password': password}).encode('utf-8')
    encrypted = protect(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    temporary.replace(path)


def load_credentials(source=None):
    payload = json.loads(protect((source or credential_path()).read_bytes(), decrypt=True))
    if payload.get('origin') != ORIGIN or not payload.get('username') or not payload.get('password'):
        raise ValueError('Invalid credential file')
    return payload


def main():
    parser = argparse.ArgumentParser(description='Set up encrypted local court login credentials.')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--setup', action='store_true')
    mode.add_argument('--status', action='store_true')
    mode.add_argument('--for-browser', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.status:
        try:
            load_credentials()
        except Exception:
            print('Court auto-login: credentials not configured or unavailable.')
            return 1
        print('Court auto-login: encrypted credentials available.')
        return 0
    if args.for_browser:
        # Consumed by auto_login.mjs through an in-memory child-process pipe only.
        # Never run this option in a chat/terminal tool: it returns secret material.
        if sys.stdin.isatty() or sys.stdout.isatty() or sys.stdin.read(128) != 'COURT_BROWSER_PIPE_V1':
            return 1
        sys.stdout.write(json.dumps(load_credentials(), ensure_ascii=True))
        return 0
    print('Local court login setup: https://fe.xuanen.com.tw')
    print('Input is hidden. Credentials are encrypted for this Windows user only.')
    print('They will be used only for this court website. Nothing is uploaded to GitHub.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        username = getpass.getpass('Court username: ')
        password = getpass.getpass('Court password: ')
        confirmation = getpass.getpass('Confirm court password: ')
    if password != confirmation:
        print('Passwords do not match. Nothing saved.')
        return 1
    save_credentials(username, password)
    config_path = Path(__file__).with_name('config.json')
    settings = json.loads(config_path.read_text(encoding='utf-8'))
    settings.setdefault('auto_login', {})['credential_setup_required'] = False
    config_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved encrypted court credentials. No booking created. Return to the chat for login verification.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print('\nSetup cancelled.')
        sys.exit(1)
    except Exception:
        print('Court credential setup/read failed. Use an interactive terminal under your Windows account.')
        sys.exit(1)
