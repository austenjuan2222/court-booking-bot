// CUA browser adapter. Credentials stay inside this module and the local browser.
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const execute = promisify(execFile);
const origin = 'https://fe.xuanen.com.tw';
const loginUrl = `${origin}/fe03.aspx?module=login_page&files=login`;
const helperPath = fileURLToPath(new URL('./login_credentials.py', import.meta.url));

function allowedUrl(value) {
  try {
    const url = new URL(value);
    return url.origin === origin && url.pathname.toLowerCase() === '/fe03.aspx';
  } catch { return false; }
}

async function loadLocalCredentials() {
  try {
    const pending = execute('python', [helperPath, '--for-browser'], {
      windowsHide: true, timeout: 10000, maxBuffer: 16384,
    });
    pending.child.stdin.end('COURT_BROWSER_PIPE_V1');
    const result = await pending;
    const credentials = JSON.parse(result.stdout);
    result.stdout = '';
    if (credentials.origin !== origin || !credentials.username || !credentials.password) {
      throw new Error('Invalid credentials');
    }
    return credentials;
  } catch {
    // Child-process errors can carry stdout; never forward those errors to the caller.
    throw new Error('LOCAL_CREDENTIALS_UNAVAILABLE');
  }
}

export async function ensureLogin(tab, options = {}) {
  const load = options.loadCredentials || loadLocalCredentials;
  const sleep = options.sleep || (ms => new Promise(resolve => setTimeout(resolve, ms)));
  const timeout = options.verificationTimeoutMs ?? 45000;
  const signedIn = () => tab.playwright.getByRole('link', { name: '[登出]', exact: true }).isVisible();
  if (!allowedUrl(await tab.url())) return { status: 'WRONG_SITE', attempted: false };
  if (await signedIn()) return { status: 'ALREADY_LOGGED_IN', attempted: false };
  let credentials;
  let submitted = false;
  try {
    const current = new URL(await tab.url());
    if ((current.searchParams.get('module') || '').toLowerCase() !== 'login_page') {
      const loginLink = tab.playwright.getByRole('link', { name: '會員註冊/登入', exact: true });
      if (await loginLink.isVisible()) await loginLink.click();
      else await tab.goto(loginUrl);
    }
    // Browser-native alerts can block CDP/DOM calls. Read AX privately and dismiss
    // only the two known non-binding notices, using a fresh observed button ID.
    if (typeof tab.getAXState === 'function') {
      for (let count = 0; count < 3; count++) {
        const ax = await tab.getAXState({ emit: false });
        const knownNotice = ax.includes('請勿開啟2個網頁') || ax.includes('近期詐騙猖獗');
        if (!knownNotice) break;
        const button = ax.match(/^\s*(\d+) button OK\s*$/m);
        if (!button) return { status: 'USER_CONFIRMATION_REQUIRED', attempted: false };
        await tab.click(Number(button[1]));
      }
    }
    const dialog = await tab.getJsDialog();
    if (dialog) return { status: 'USER_CONFIRMATION_REQUIRED', attempted: false };
    await tab.playwright.locator('#ContentPlaceHolder1_loginid').waitFor({ state: 'visible', timeoutMs: 15000 });
    const notice = tab.playwright.getByRole('button', { name: 'OK', exact: true });
    if (await notice.isVisible()) await notice.click();
    // Passively observe the website's own verification; never solve/click/invoke it.
    const deadline = Date.now() + timeout;
    let verified = false;
    do {
      if (!allowedUrl(await tab.url())) return { status: 'WRONG_SITE', attempted: false };
      verified = await tab.playwright.evaluate(() => {
        const response = document.querySelector('input[name="cf-turnstile-response"]');
        return Boolean(response && response.value);
      });
      if (!verified && Date.now() < deadline) await sleep(1000);
    } while (!verified && Date.now() < deadline);
    if (!verified) return { status: 'VERIFICATION_REQUIRED', attempted: false };
    credentials = await load();
    if (credentials.origin !== origin || !credentials.username || !credentials.password) {
      return { status: 'LOCAL_CREDENTIALS_UNAVAILABLE', attempted: false };
    }
    if (!allowedUrl(await tab.url())) return { status: 'WRONG_SITE', attempted: false };
    await tab.playwright.locator('#ContentPlaceHolder1_loginid').fill(credentials.username);
    await tab.playwright.locator('#loginpw').fill(credentials.password);
    await tab.playwright.locator('#login_but').click();
    submitted = true;
    // No snapshots/screenshots while a login form contains credentials.
    const loginDeadline = Date.now() + (options.loginTimeoutMs ?? 15000);
    do {
      try {
        if (allowedUrl(await tab.url()) && await signedIn()) {
          return { status: 'LOGGED_IN', attempted: true };
        }
      } catch { /* A redirect can temporarily invalidate a DOM locator. */ }
      if (Date.now() < loginDeadline) await sleep(500);
    } while (Date.now() < loginDeadline);
    return { status: 'LOGIN_NOT_CONFIRMED', attempted: true };
  } catch (error) {
    return { status: error?.message === 'LOCAL_CREDENTIALS_UNAVAILABLE'
      ? 'LOCAL_CREDENTIALS_UNAVAILABLE' : 'LOGIN_NOT_CONFIRMED', attempted: submitted };
  } finally {
    if (credentials) { credentials.username = ''; credentials.password = ''; }
    // Clear failed form values before returning any control to the chat.
    try {
      if (allowedUrl(await tab.url()) && !await signedIn()) {
        for (const selector of ['#ContentPlaceHolder1_loginid', '#loginpw']) {
          const field = tab.playwright.locator(selector);
          if (await field.isVisible()) await field.fill('');
        }
      }
    } catch { /* Never expose browser error objects that could contain filled data. */ }
  }
}
