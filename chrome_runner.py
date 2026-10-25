"""Local headed Chrome runner. Default is read-only; --scheduled enables bookings."""
import argparse
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys

from core import TAIPEI, choose_courts, send_notice
from login_credentials import load_credentials
from send_notice import credential_path, protect

ROOT = Path(__file__).resolve().parent
BASE = 'https://fe.xuanen.com.tw/fe03.aspx'
ORDERS = BASE + '?module=member&files=orderx_mt'
PROFILE = Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'XuanenCourtBot' / 'chrome-profile'


class StopRun(Exception):
    pass


def permitted_url(url):
    from urllib.parse import urlsplit
    u = urlsplit(url)
    return u.scheme == 'https' and u.netloc == 'fe.xuanen.com.tw' and u.path.lower() == '/fe03.aspx'


class DialogGate:
    """Accept only a matching, explicitly armed reservation confirmation."""
    def __init__(self):
        self.expected = None
        self.accepted = False
        self.blocked = False

    def handle(self, dialog):
        message = dialog.message.strip()
        if dialog.type == 'alert' and ('請勿開啟2個網頁' in message or '近期詐騙猖獗' in message):
            dialog.accept()
            return
        match = re.fullmatch(r'您是否確定預約「(匹克\d+) (\d{2}:00~\d{2}:00)」[？?]', message)
        if dialog.type == 'confirm' and self.expected and match and tuple(match.groups()) == self.expected:
            self.expected = None  # single use, before handling the dialog
            self.accepted = True
            dialog.accept()
        else:
            self.blocked = True
            dialog.dismiss()


def email(config, subject, body):
    saved = json.loads(protect(credential_path().read_bytes(), decrypt=True))
    if saved['sender'] != config['sender_email']:
        raise StopRun('GMAIL_SENDER_MISMATCH')
    send_notice(config['smtp_host'], config['smtp_port'], saved['sender'], saved['password'],
                config['notification_email'], subject, body)


def signed_in(page):
    return page.get_by_role('link', name='[登出]', exact=True).is_visible()


def login(page, gate, verification_timeout=45000):
    page.goto(BASE + '?Module=ind&files=ind', wait_until='domcontentloaded')
    if signed_in(page):
        return 'ALREADY_LOGGED_IN'
    page.goto(BASE + '?module=login_page&files=login', wait_until='domcontentloaded')
    page.locator('#ContentPlaceHolder1_loginid').wait_for(state='visible')
    popup = page.get_by_role('button', name='OK', exact=True)
    if popup.is_visible():
        popup.click()
    # Observe natural verification only; never solve or bypass the widget.
    try:
        page.wait_for_function("""() => {
          const r = document.querySelector('input[name="cf-turnstile-response"]');
          return !!r && !!r.value;
        }""", timeout=verification_timeout)
    except Exception:
        page.screenshot(path=str(ROOT / 'chrome-verification-required.png'))
        raise StopRun('VERIFICATION_REQUIRED') from None
    if gate.blocked or not permitted_url(page.url):
        raise StopRun('LOGIN_PAGE_NOT_VERIFIED')
    creds = load_credentials()
    try:
        page.locator('#ContentPlaceHolder1_loginid').fill(creds['username'])
        page.locator('#loginpw').fill(creds['password'])
        page.locator('#login_but').click()
        page.get_by_role('link', name='[登出]', exact=True).wait_for(state='visible', timeout=20000)
    except Exception:
        # No raw Playwright exception, screenshot or trace may expose credentials.
        for selector in ('#ContentPlaceHolder1_loginid', '#loginpw'):
            try:
                if page.locator(selector).is_visible():
                    page.locator(selector).fill('')
            except Exception:
                pass
        raise StopRun('LOGIN_NOT_CONFIRMED') from None
    finally:
        creds.clear()
    return 'LOGGED_IN'


def order_rows(page):
    page.goto(ORDERS, wait_until='domcontentloaded')
    if not signed_in(page):
        raise StopRun('SESSION_EXPIRED')
    text = page.locator('body').inner_text()
    pages = re.findall(r'共\s*(\d+)\s*頁', text)
    if not pages or any(int(n) != 1 for n in pages):
        raise StopRun('ORDER_PAGINATION_REQUIRES_REVIEW')
    raw = page.locator('table').evaluate_all("""tables => {
      for (const table of tables) {
        const rows = Array.from(table.rows);
        const index = rows.findIndex(r => r.innerText.includes('訂單編號') && r.innerText.includes('產品名稱'));
        if (index < 0) continue;
        const headers = Array.from(rows[index].cells).map(c => c.innerText.replace(/\\s/g,''));
        if (headers.length < 8) continue;
        return rows.slice(index+1).map(r => Array.from(r.cells).map(c => c.innerText.trim()))
          .filter(c => c.length === headers.length).map(c => Object.fromEntries(headers.map((h,i)=>[h,c[i]])));
      }
      return null;
    }""")
    if raw is None:
        # Empty orders must still expose a table with the expected header.
        raise StopRun('ORDER_TABLE_NOT_VERIFIED')
    result = []
    for r in raw:
        if not re.fullmatch(r'\d{10,}', r.get('訂單編號', '')):
            continue
        court = re.fullmatch(r'匹克球場(\d+)', r.get('產品名稱', ''))
        if not court:
            continue
        try:
            result.append({'number': r['訂單編號'], 'court': '匹克' + court[1],
                           'date': date.fromisoformat(r['日期'].replace('/', '-')).isoformat(),
                           'hour': int(r['時間'].split(':')[0]),
                           'price': int(r['金額'].replace(',', '')), 'status': r['狀態']})
        except Exception:
            raise StopRun('ORDER_ROW_NOT_VERIFIED') from None
    return result


def live_orders(rows, target, hours):
    result = [r for r in rows if r['date'] == target.isoformat() and r['hour'] in hours
              and r['status'] != '取消']
    if any(r['status'] not in ('未繳費', '已繳費', '已付款') for r in result):
        raise StopRun('UNKNOWN_ORDER_STATUS')
    return result


def listing(page, target):
    page.goto(BASE + '?module=net_booking&files=booking_place&PT=13', wait_until='domcontentloaded')
    button = page.locator(f'img[onclick*="{target:%Y/%m/%d}"]')
    if button.count() != 1:
        raise StopRun('DATE_UNAVAILABLE_OR_TERMS_REQUIRED')
    button.click()
    page.get_by_text('下午', exact=True).click()
    table = page.locator('#ContentPlaceHolder1_Step2_data')
    table.wait_for(state='visible')
    return table.evaluate("""root => {
      let hour = null; const out=[];
      for (const row of root.querySelectorAll('tr')) {
        const cells=Array.from(row.cells);
        const m=cells[0]?.innerText.trim().match(/^(\\d{2}):00~(\\d{2}):00$/);
        if (m) hour=Number(m[1]);
        const c=cells.find(c=>/^匹克\\d+$/.test(c.innerText.trim()));
        if(c && [15,16].includes(hour)) out.push({hour,court:c.innerText.trim(),
          price:Number(c.nextElementSibling.innerText.trim()),
          available:!!row.querySelector('img[name="PlaceBtn"]')});
      } return out;
    }""")


def choose_plan(rows, hours, cap):
    available = {h: [r['court'] for r in rows if r['hour'] == h and r['available']
                    and isinstance(r['price'], int) and 0 < r['price'] <= cap] for h in hours}
    courts = choose_courts(available, hours)
    if not courts:
        return None
    plan = [next(r for r in rows if r['hour'] == h and r['court'] == courts[h] and r['available']) for h in hours]
    return plan if sum(r['price'] for r in plan) <= cap else None


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def run(args):
    from playwright.sync_api import sync_playwright
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    now = datetime.now(TAIPEI)
    if args.scheduled:
        if not config.get('enabled') or now.weekday() != 5 or now.hour != 0 or now.minute >= 10:
            raise StopRun('OUTSIDE_AUTHORIZED_SCHEDULE')
        target = (now + timedelta(days=7)).date()
    else:
        target = date.fromisoformat(args.date) if args.date else (now + timedelta(days=(5-now.weekday()) % 7)).date()
    if target.weekday() != 5:
        raise StopRun('TARGET_MUST_BE_SATURDAY')
    booking = args.scheduled
    if booking and target.isoformat() in config.get('excluded_booking_dates', []):
        raise StopRun('EXCLUDED_DATE')
    hours = [15, 16]
    state_path = ROOT / ('chrome-orders-' + target.isoformat() + '.json')
    if booking:
        # Validate/decrypt notification credentials before creating expiring orders.
        saved = json.loads(protect(credential_path().read_bytes(), decrypt=True))
        if saved.get('sender') != config['sender_email'] or not saved.get('password'):
            raise StopRun('GMAIL_NOT_CONFIGURED')
        saved.clear()
    gate = DialogGate()
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(str(PROFILE), channel='chrome', headless=False,
                    locale='zh-TW', timezone_id='Asia/Taipei', viewport={'width':1280, 'height':900})
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(15000)
            page.on('dialog', gate.handle)
            if args.setup:
                print('SETUP: Chrome will wait up to 3 minutes for user-completed site verification. No booking.', flush=True)
            print('LOGIN: ' + login(page, gate, 180000 if args.setup else 45000), flush=True)
            if args.login_only or args.setup:
                page.screenshot(path=str(ROOT / 'chrome-login-verified.png'))
                return {'status':'LOGIN_VERIFIED', 'booked':False}
            existing = live_orders(order_rows(page), target, hours)
            if existing:
                complete = len(existing) == 2 and {r['hour'] for r in existing} == set(hours)
                result = {'status':'EXISTING_ORDERS' if complete else 'PARTIAL_ORDERS_REVIEW_REQUIRED',
                          'booked':False, 'orders':existing}
                page.screenshot(path=str(ROOT / 'chrome-orders-verified.png'))
                if booking:
                    email(config, '匹克球訂場：既有訂單，未重複預約', json.dumps(result, ensure_ascii=False) + '\n' + ORDERS)
                return result
            if booking and state_path.exists():
                raise StopRun('PRIOR_ATTEMPT_REQUIRES_REVIEW')
            rows = listing(page, target)
            plan = choose_plan(rows, hours, config['max_total_twd'])
            if not booking:
                page.screenshot(path=str(ROOT / 'chrome-preview.png'))
                return {'status':'PREVIEW', 'date':target.isoformat(), 'booked':False, 'plan':plan}
            if not plan:
                raise StopRun('NO_COMPLETE_PLAN_WITHIN_BUDGET')
            journal = {'date':target.isoformat(), 'plan':plan, 'orders':[], 'status':'STARTED'}
            write_json(state_path, journal)
            for item in plan:
                # Recheck live listing and price immediately before each mutation.
                if journal['orders']:
                    fresh = listing(page, target)
                    if not any(all(r[k] == item[k] for k in ('hour','court','price')) and r['available'] for r in fresh):
                        raise StopRun('SECOND_SLOT_CHANGED_PARTIAL_ORDER_EXISTS')
                hour, court = item['hour'], item['court']
                label = f'{hour:02}:00~{hour+1:02}:00'
                if not permitted_url(page.url) or f'D={target:%Y/%m/%d}' not in page.url or 'D2=2' not in page.url:
                    raise StopRun('WRONG_BOOKING_PAGE')
                if gate.blocked:
                    raise StopRun('UNEXPECTED_DIALOG')
                gate.expected, gate.accepted = (court, label), False
                journal['status'] = 'SUBMISSION_UNCERTAIN'
                write_json(state_path, journal)  # persist before click; never blindly retry
                page.locator(f'img[name="PlaceBtn"][onclick*="{court} {label}"]').click()
                if not gate.accepted or gate.blocked:
                    raise StopRun('CONFIRMATION_NOT_MATCHED')
                page.get_by_text('回我的訂單', exact=False).first.wait_for(state='visible')
                found = live_orders(order_rows(page), target, hours)
                matching = [r for r in found if r['hour'] == hour and r['court'] == court
                            and r['price'] == item['price'] and r['status'] == '未繳費']
                if len(matching) != 1:
                    raise StopRun('SUBMISSION_RESULT_UNCERTAIN')
                journal['orders'].append(matching[0])
                journal['status'] = 'PARTIAL' if len(journal['orders']) < 2 else 'VERIFIED_UNPAID'
                write_json(state_path, journal)
                page.screenshot(path=str(ROOT / 'chrome-orders-verified.png'))
                lines = [f"{r['date']} {r['court']} {r['hour']:02}:00–{r['hour']+1:02}:00 NT${r['price']} 訂單 {r['number']}" for r in journal['orders']]
                email(config, '匹克球待付款：' + ('兩時段已建立' if len(lines)==2 else '第一時段已建立'),
                      '\n'.join(lines) + '\n請立即付款。各訂單須於建立後10分鐘內結帳，期限不從收到Email起算。\n' + ORDERS)
            return {'status':'VERIFIED_UNPAID_EMAIL_ACCEPTED', 'booked':True, 'orders':journal['orders']}
        finally:
            context.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--login-only', action='store_true')
    p.add_argument('--setup', action='store_true', help='Login only; allow 3 minutes for manual site verification')
    p.add_argument('--date', help='Read-only preview date (YYYY-MM-DD)')
    p.add_argument('--scheduled', action='store_true', help='Book only Saturday 00:00–00:09 Taiwan time')
    args = p.parse_args()
    if args.scheduled and (args.date or args.login_only or args.setup):
        p.error('--scheduled cannot be combined with --date/--login-only')
    # Windows byte lock released automatically if the process exits or crashes.
    import msvcrt
    with (ROOT / 'chrome-run.lock').open('a+b') as lock:
        if lock.seek(0, 2) == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('STOPPED: ANOTHER_RUN_IS_ACTIVE')
            return 1
        try:
            result = run(args)
            write_json(ROOT / 'chrome-last-result.json', result)
            print(json.dumps(result, ensure_ascii=True), flush=True)
            return 0
        except Exception as error:
            reason = str(error) if isinstance(error, StopRun) else 'BROWSER_OR_EMAIL_FAILED'
            write_json(ROOT / 'chrome-last-result.json', {'status':reason, 'booked':'unconfirmed'})
            print('STOPPED: ' + reason, flush=True)
            if args.scheduled:
                try:
                    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
                    email(config, '匹克球自動訂場需要處理', reason + '\n可能已有部分訂單，請先查看我的訂單，勿重複預約。\n' + ORDERS)
                except Exception:
                    print('EMAIL_FAILED', flush=True)
            return 1


if __name__ == '__main__':
    sys.exit(main())
