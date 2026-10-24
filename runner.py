"""Cloud auto-login and availability preview. Does NOT create reservations."""
import json
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode

from planner import choose_plan, next_saturday

BASE = 'https://fe.xuanen.com.tw/fe03.aspx'


class PreviewError(Exception):
    pass


def required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise PreviewError('Missing secret: ' + name)
    return value


def notify(subject, body):
    sender = required('GMAIL_USER')
    password = ''.join(required('GMAIL_APP_PASSWORD').split())
    recipient = required('NOTIFY_EMAIL')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = recipient
    message['Subject'] = subject
    message.set_content(body)
    with smtplib.SMTP('smtp.gmail.com', 587, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(sender, password)
        if smtp.send_message(message):
            raise PreviewError('Email recipient rejected')


def inspect_availability():
    from playwright.sync_api import sync_playwright, expect
    username = required('COURT_USER')
    password = required('COURT_PASSWORD')
    settings = json.loads(Path(__file__).with_name('settings.json').read_text(encoding='utf-8'))
    if settings['mode'] != 'preview':
        raise PreviewError('Only preview is implemented; booking is not enabled')
    target = next_saturday()
    date_string = target.strftime('%Y/%m/%d')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(locale='zh-TW', timezone_id='Asia/Taipei')
        page = context.new_page()
        page.set_default_timeout(45000)
        # Preview never accepts reservation confirmations and never solves challenges.
        page.on('dialog', lambda dialog: dialog.dismiss())
        print('Step: open login page')
        page.goto(BASE + '?module=login_page&files=login', wait_until='domcontentloaded')
        page.locator('#ContentPlaceHolder1_loginid').wait_for(state='visible')
        popup = page.get_by_role('button', name='OK', exact=True)
        try:
            popup.wait_for(state='visible', timeout=5000)
            popup.click()
        except Exception:
            pass
        # Wait passively for the site's own widget; never click, solve or bypass it.
        print('Step: wait for site verification to finish naturally')
        try:
            page.wait_for_function('''() => {
                const response = document.querySelector('input[name="cf-turnstile-response"]');
                return !!response && !!response.value;
            }''', timeout=45000)
        except Exception:
            raise PreviewError('VERIFICATION_PENDING: site verification did not complete automatically; manual verification may be required') from None
        page.locator('#ContentPlaceHolder1_loginid').fill(username)
        page.locator('#loginpw').fill(password)
        print('Step: submit login (credentials are not logged)')
        page.locator('#login_but').click()
        try:
            expect(page.get_by_role('link', name='[登出]', exact=True)).to_be_visible(timeout=45000)
        except Exception:
            if page.locator('#showerror3').is_visible():
                raise PreviewError('LOGIN_REJECTED: website reports incorrect username or password') from None
            if page.locator('#LoginMsg').is_visible():
                raise PreviewError('LOGIN_RATE_LIMITED: website temporarily restricted login') from None
            verification_failed = page.get_by_text('驗證失敗', exact=True)
            if verification_failed.count() and verification_failed.first.is_visible():
                raise PreviewError('VERIFICATION_FAILED: website requires successful verification before login') from None
            challenge_pending = page.evaluate('''() => {
                const response = document.querySelector('input[name="cf-turnstile-response"]');
                return !!document.querySelector('#example-container iframe') && (!response || !response.value);
            }''')
            if challenge_pending:
                raise PreviewError('VERIFICATION_PENDING: cloud browser did not complete site verification') from None
            raise PreviewError('LOGIN_NOT_CONFIRMED: no authenticated page after 45 seconds') from None
        print('Step: authenticated')
        page.goto(BASE + '?module=net_booking&files=booking_place&PT=13', wait_until='domcontentloaded')
        # Only click an actual offered date. Do not fabricate an out-of-range booking URL.
        date_button = page.locator(f'img[onclick*="{date_string}"]')
        if date_button.count() != 1:
            raise PreviewError('Target date unavailable, terms required or access restricted')
        date_button.click()
        page.locator('#ContentPlaceHolder1_Step2_data').wait_for(state='visible')
        params = urlencode({'module': 'net_booking', 'files': 'booking_place',
                            'StepFlag': '2', 'PT': '13', 'D': date_string, 'D2': '2'})
        # Read-only afternoon listing; this URL shape was verified in the site UI.
        page.goto(BASE + '?' + params, wait_until='domcontentloaded')
        expect(page.get_by_role('link', name='[登出]', exact=True)).to_be_visible()
        table = page.locator('#ContentPlaceHolder1_Step2_data')
        table.wait_for(state='visible')
        rows = table.evaluate('''root => {
            let hour = null;
            const result = [];
            for (const row of root.querySelectorAll('tr')) {
                const cells = Array.from(row.querySelectorAll(':scope > td'));
                if (!cells.length) continue;
                const match = cells[0].innerText.trim().match(/^(\\d{2}):00~(\\d{2}):00$/);
                if (match) hour = Number(match[1]);
                const court = cells.find(cell => /^匹克\\d+$/.test(cell.innerText.trim()));
                if (court && [15,16].includes(hour)) result.push({
                    hour, court: court.innerText.trim(),
                    price: Number(court.nextElementSibling.innerText.trim()),
                    available: !!row.querySelector('img[name="PlaceBtn"]')
                });
            }
            return result;
        }''')
        if not rows or any(not any(r['hour'] == hour for r in rows) for hour in settings['hours']):
            raise PreviewError('Could not verify both requested slot listings')
        plan = choose_plan(rows, settings['hours'], settings['max_total_twd'])
        browser.close()
    return target, plan


def main():
    try:
        # Validate notification secrets before attempting the website.
        for name in ('GMAIL_USER', 'GMAIL_APP_PASSWORD', 'NOTIFY_EMAIL'):
            required(name)
        target, plan = inspect_availability()
        lines = ['這是雲端自動登入與查場測試，沒有建立預約，不需付款。',
                 '查詢日期：' + target.isoformat()]
        if plan:
            lines += [f"{r['hour']:02}:00–{r['hour']+1:02}:00：{r['court']}，NT${r['price']}" for r in plan]
            lines.append('合計：NT$' + str(sum(r['price'] for r in plan)))
        else:
            lines.append('沒有符合兩時段及價格上限的完整方案。')
        notify('匹克球雲端測試：僅查場，未訂場', '\n'.join(lines))
        print('PASS: cloud login and listing verified; notification accepted by SMTP. No booking created.')
        return 0
    except Exception as error:
        # Never print raw browser/HTTP exceptions, page dumps, credentials or screenshots.
        reason = str(error) if isinstance(error, PreviewError) else 'Cloud login, site access or email test failed'
        print('FAILED: ' + reason)
        try:
            notify('匹克球雲端測試失敗：未訂場', reason + '\n未建立預約。若網站要求人工驗證，不能保證無人登入。')
            print('Failure notification accepted by SMTP.')
        except Exception:
            print('Failure notification could not be sent; inspect the configured secrets.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
