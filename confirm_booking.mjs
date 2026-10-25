// CUA adapter: receive the native dialog concurrently with the booking click.
// Never override confirm(), call website internals or repeat an uncertain click.
export async function confirmBooking(tab, { date, court, hour, price, maxPrice = 450 }) {
  if (!/^\d{4}\/\d{2}\/\d{2}$/.test(date) || !/^匹克\d+$/.test(court)
      || ![15, 16].includes(hour) || !Number.isInteger(price) || price <= 0 || price > maxPrice) {
    return {status:'INVALID_EXPECTATION'};
  }
  const url = new URL(await tab.url());
  if (url.origin !== 'https://fe.xuanen.com.tw' || url.pathname.toLowerCase() !== '/fe03.aspx'
      || url.searchParams.get('D') !== date || url.searchParams.get('D2') !== '2'
      || url.searchParams.get('PT') !== '13' || url.searchParams.get('StepFlag') !== '2') {
    return {status:'WRONG_PAGE'};
  }
  if (await tab.getJsDialog()) return {status:'PREEXISTING_DIALOG_REVIEW_REQUIRED'};
  const label = `${court} ${hour}:00~${hour + 1}:00`;
  const button = tab.playwright.locator(`img[name="PlaceBtn"][onclick*="${label}"]`);
  if (await button.count() !== 1) return {status:'SLOT_NOT_AVAILABLE'};
  const observed = await button.evaluate(element => ({
    handler:element.getAttribute('onclick'),
    cells:Array.from(element.closest('tr').cells).map(c=>c.innerText.trim()),
  }));
  if (!observed.handler?.includes(`confirm('您是否確定預約「${label}」？')`)
      || !observed.cells.includes(court) || !observed.cells.includes(String(price))) {
    return {status:'CONFIRMATION_OR_PRICE_MISMATCH'};
  }
  let clicked = false, accepted = false, unexpected = false;
  // Awaiting click first can deadlock the native modal. Poll in the same call.
  const click = button.click({timeoutMs:4000}).then(()=>{clicked=true;},()=>{});
  const receive = (async()=>{
    for (let i=0;i<20;i++) {
      const dialog = await tab.getJsDialog();
      if (dialog) {
        if (dialog.type === 'confirm') { await dialog.accept(); accepted=true; }
        else { unexpected=true; await dialog.dismiss(); }
        return;
      }
      await new Promise(resolve=>setTimeout(resolve,250));
    }
  })();
  try { await Promise.all([click,receive]); }
  catch { return {status:'UNCERTAIN_CHECK_ORDERS_DO_NOT_RETRY',accepted,clicked}; }
  return {status:accepted && !unexpected ? 'CONFIRM_ACCEPTED_VERIFY_ORDER' : 'UNCERTAIN_CHECK_ORDERS_DO_NOT_RETRY',accepted,clicked};
}
