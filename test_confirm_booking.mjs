import test from 'node:test';
import assert from 'node:assert/strict';
import {confirmBooking} from './confirm_booking.mjs';

function fixture({wrongPrice=false,wrongPage=false,preexisting=false}={}) {
  let pending=false,accepts=0,clicks=0,done;
  const button={count:async()=>1,evaluate:async()=>({handler:"if(confirm('您是否確定預約「匹克6 15:00~16:00」？')){}",cells:['匹克6',wrongPrice?'999':'450']}),
    click:()=>{clicks++;pending=true;return new Promise(r=>{done=r;});}};
  return {tab:{url:async()=>wrongPage?'https://example.com/':'https://fe.xuanen.com.tw/fe03.aspx?D=2026/10/31&D2=2&PT=13&StepFlag=2',
    getJsDialog:async()=>preexisting?{type:'confirm'}:pending?{type:'confirm',accept:async()=>{accepts++;pending=false;done();}}:undefined,
    playwright:{locator:()=>button}},counts:()=>({accepts,clicks})};
}
const expected={date:'2026/10/31',court:'匹克6',hour:15,price:450};
test('dialog accepted while click is waiting, without deadlock',async()=>{
  const f=fixture();const r=await confirmBooking(f.tab,expected);
  assert.equal(r.status,'CONFIRM_ACCEPTED_VERIFY_ORDER');assert.deepEqual(f.counts(),{accepts:1,clicks:1});
});
for(const options of [{wrongPrice:true},{wrongPage:true},{preexisting:true}]) {
  test('preflight rejects '+JSON.stringify(options),async()=>{
    const f=fixture(options);await confirmBooking(f.tab,expected);assert.equal(f.counts().clicks,0);
  });
}
