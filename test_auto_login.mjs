import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureLogin } from './auto_login.mjs';

function fakeTab({ url = 'https://fe.xuanen.com.tw/fe03.aspx', signedIn = false, verified = true, success = true } = {}) {
  const events = [];
  let authenticated = signedIn;
  return {
    events, url: async () => url, goto: async target => { events.push('navigate'); url = target; },
    getJsDialog: async () => undefined,
    playwright: {
      evaluate: async () => verified,
      getByRole: (role, { name }) => ({
        isVisible: async () => name === '[登出]' && authenticated,
        waitFor: async () => { if (!authenticated) throw new Error('Timed out'); },
      }),
      locator: selector => ({
        waitFor: async () => {}, isVisible: async () => !authenticated,
        fill: async value => { events.push([selector, value ? 'filled' : 'cleared']); },
        click: async () => { events.push('submit'); authenticated = success; },
      }),
    },
  };
}
const credential = () => ({ origin: 'https://fe.xuanen.com.tw', username: 'synthetic-user', password: 'synthetic-password' });

test('wrong origin never loads credentials', async () => {
  let loaded = false;
  const result = await ensureLogin(fakeTab({ url: 'https://example.com/fe03.aspx' }), { loadCredentials: async () => { loaded = true; } });
  assert.equal(result.status, 'WRONG_SITE'); assert.equal(loaded, false);
});
test('existing session never reads credentials', async () => {
  const result = await ensureLogin(fakeTab({ signedIn: true }), { loadCredentials: async () => { throw new Error('must not load'); } });
  assert.equal(result.status, 'ALREADY_LOGGED_IN');
});
test('pending verification never loads credentials or submits', async () => {
  const tab = fakeTab({ verified: false });
  const result = await ensureLogin(tab, { verificationTimeoutMs: 0, loadCredentials: async () => { throw new Error('must not load'); } });
  assert.equal(result.status, 'VERIFICATION_REQUIRED'); assert.ok(!tab.events.includes('submit'));
});
test('successful login submits once', async () => {
  const tab = fakeTab();
  const result = await ensureLogin(tab, { loadCredentials: async () => credential() });
  assert.equal(result.status, 'LOGGED_IN'); assert.equal(tab.events.filter(x => x === 'submit').length, 1);
});
test('failed login clears both fields and does not retry', async () => {
  const tab = fakeTab({ success: false });
  const result = await ensureLogin(tab, { loadCredentials: async () => credential(), loginTimeoutMs: 0 });
  assert.equal(result.status, 'LOGIN_NOT_CONFIRMED'); assert.equal(tab.events.filter(x => x === 'submit').length, 1);
  assert.ok(tab.events.some(x => Array.isArray(x) && x[0] === '#loginpw' && x[1] === 'cleared'));
});
test('known native reminder is dismissed using its observed AX button', async () => {
  const tab = fakeTab();
  let dismissed = false;
  tab.getAXState = async options => {
    assert.equal(options.emit, false);
    return dismissed ? '會員登入' : '請勿開啟2個網頁\n  4 button OK';
  };
  tab.click = async id => { assert.equal(id, 4); dismissed = true; };
  const result = await ensureLogin(tab, { loadCredentials: async () => credential() });
  assert.equal(result.status, 'LOGGED_IN'); assert.equal(dismissed, true);
});
test('transient locator error during redirect does not report failed login', async () => {
  const tab = fakeTab();
  const original = tab.playwright.getByRole;
  let interrupted = false;
  tab.playwright.getByRole = (...args) => {
    const locator = original(...args);
    const visible = locator.isVisible;
    locator.isVisible = async () => {
      if (tab.events.includes('submit') && !interrupted) {
        interrupted = true;
        throw new Error('Synthetic navigation interruption');
      }
      return visible();
    };
    return locator;
  };
  const result = await ensureLogin(tab, { loadCredentials: async () => credential(), sleep: async () => {} });
  assert.equal(result.status, 'LOGGED_IN');
  assert.equal(tab.events.filter(x => x === 'submit').length, 1);
});
