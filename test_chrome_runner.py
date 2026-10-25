import unittest
from datetime import date
from chrome_runner import DialogGate, choose_plan, live_orders, permitted_url, StopRun, order_rows, ORDERS


class Dialog:
    def __init__(self, message, kind='confirm'):
        self.message, self.type, self.action = message, kind, None
    def accept(self): self.action = 'accept'
    def dismiss(self): self.action = 'dismiss'


class SafetyTests(unittest.TestCase):
    def test_confirmation_requires_exact_armed_slot_and_is_single_use(self):
        gate = DialogGate()
        gate.expected = ('匹克6', '15:00~16:00')
        d = Dialog('您是否確定預約「匹克6 15:00~16:00」？')
        gate.handle(d)
        self.assertEqual(d.action, 'accept')
        self.assertTrue(gate.accepted)
        d2 = Dialog(d.message)
        gate.handle(d2)
        self.assertEqual(d2.action, 'dismiss')
        self.assertTrue(gate.blocked)

    def test_wrong_court_time_payment_and_unknown_dialog_rejected(self):
        for text in ('您是否確定預約「匹克5 15:00~16:00」？',
                     '您是否確定預約「匹克6 16:00~17:00」？', '確認付款', '同意條款'):
            gate = DialogGate()
            gate.expected = ('匹克6', '15:00~16:00')
            d = Dialog(text)
            gate.handle(d)
            self.assertEqual(d.action, 'dismiss')
            self.assertFalse(gate.accepted)

    def test_plan_prefers_same_court_and_obeys_cap(self):
        rows = [dict(hour=h, court=c, price=450, available=True)
                for h,c in [(15,'匹克3'),(15,'匹克6'),(16,'匹克6')]]
        self.assertEqual([r['court'] for r in choose_plan(rows,[15,16],900)], ['匹克6']*2)
        self.assertIsNone(choose_plan(rows,[15,16],899))
        self.assertIsNone(choose_plan(rows[:2],[15,16],900))

    def test_cancelled_orders_ignored_but_unknown_status_stops(self):
        rows = [dict(date='2026-10-31',hour=15,status='取消')]
        self.assertEqual(live_orders(rows,date(2026,10,31),[15,16]), [])
        rows[0]['status']='未知'
        with self.assertRaises(StopRun): live_orders(rows,date(2026,10,31),[15,16])

    def test_origin_is_exact(self):
        self.assertTrue(permitted_url('https://fe.xuanen.com.tw/fe03.aspx?module=login_page'))
        self.assertFalse(permitted_url('https://fe.xuanen.com.tw.evil.test/fe03.aspx'))
        self.assertFalse(permitted_url('http://fe.xuanen.com.tw/fe03.aspx'))

    def test_real_browser_confirm_event_is_handled(self):
        from playwright.sync_api import sync_playwright
        gate = DialogGate()
        gate.expected = ('匹克6', '15:00~16:00')
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page()
            page.on('dialog', gate.handle)
            page.set_content('''<button onclick="this.textContent=confirm('您是否確定預約「匹克6 15:00~16:00」？')?'accepted':'rejected'">test</button>''')
            page.get_by_role('button').click()
            self.assertEqual(page.get_by_role('button').inner_text(), 'accepted')
            self.assertTrue(gate.accepted)
            browser.close()

    def test_order_table_parser_with_empty_cells_and_cancelled_order(self):
        from playwright.sync_api import sync_playwright
        html = '''<a href="#">[登出]</a><p>第 1 頁，共 1 頁</p><table>
          <tr><td>訂購日期</td><td>訂單編號</td><td>銷售單號<br>發票號碼</td><td>產品名稱</td><td>金額</td><td>日期</td><td>時間</td><td>狀態</td><td>備註</td><td>操作</td></tr>
          <tr><td>2026/10/25</td><td>900000000002</td><td></td><td>匹克球場6</td><td>450</td><td>2026-10-31</td><td>16</td><td>未繳費</td><td></td><td></td></tr>
          <tr><td>2026/10/25</td><td>900000000001</td><td></td><td>匹克球場6</td><td>450</td><td>2026-10-31</td><td>15</td><td>取消</td><td></td><td></td></tr></table>'''
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page()
            page.route(ORDERS, lambda route: route.fulfill(content_type='text/html; charset=utf-8', body=html))
            orders = order_rows(page)
            self.assertEqual(len(orders),2)
            self.assertEqual(orders[0]['court'], '匹克6')
            self.assertEqual([r['hour'] for r in live_orders(orders,date(2026,10,31),[15,16])],[16])
            browser.close()


if __name__ == '__main__': unittest.main()
