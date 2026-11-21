// The live page and the snapshot, screenshotted for the docs (tools/doc_screenshots/README.md).
// Run from the folder holding page.html and live.html (build_pages.py); writes shots/*.png.
const { chromium, devices } = require('playwright');
const fs = require('fs');
const html = fs.readFileSync('live.html', 'utf8');
const snap = fs.readFileSync('page.html', 'utf8');
async function ctxFor(b, opts) {
  const ctx = await b.newContext(opts);
  await ctx.route('http://127.0.0.1:8765/**', async r => {
    const u = r.request().url();
    if (u.includes('/data')) { await new Promise(res => setTimeout(res, 60000)).catch(() => {}); return r.fulfill({ json: { busy: false, version: 1 } }).catch(() => {}); }
    if (u.includes('/snap')) return r.fulfill({ body: snap, contentType: 'text/html' });
    if (/\/(\?.*)?$/.test(new URL(u).pathname + '')) return r.fulfill({ body: html, contentType: 'text/html' });
    return r.fulfill({ status: 404, body: '' });
  });
  return ctx;
}
const W = { viewport: { width: 1440, height: 860 }, deviceScaleFactor: 2, locale: 'en-US' };
(async () => {
  const b = await chromium.launch();
  const ctx = await ctxFor(b, W);
  const p = await ctx.newPage();
  p.on('pageerror', e => console.log('ERR', e.message));
  const tab = async ws => { await p.click(`[data-ws="${ws}"]`); await p.waitForTimeout(700); };
  const shot = n => p.screenshot({ path: `shots/${n}.png` });
  // snapshot (offline) views
  await p.goto('http://127.0.0.1:8765/snap'); await p.waitForTimeout(1200);
  await shot('tracking-snapshot-details');
  await tab('synth'); await shot('tracking-snapshot-progress');
  // live
  await p.goto('http://127.0.0.1:8765/?t=demo'); await p.waitForTimeout(1200);
  await shot('live-shots');
  await tab('todo'); await shot('live-todo');
  await tab('synth'); await shot('live-breakdown');
  await p.evaluate(() => { const h = [...document.querySelectorAll('.ot-h b')].find(x => x.textContent === 'Activity'); h && h.closest('.ot, section, div').scrollIntoView({ block: 'start' }); });
  await p.waitForTimeout(500); await shot('live-breakdown-activity');
  await p.evaluate(() => { const h = [...document.querySelectorAll('.ot-h b')].find(x => x.textContent === 'Projection'); h && h.closest('.ot, section, div').scrollIntoView({ block: 'start' }); });
  await p.waitForTimeout(500); await shot('live-breakdown-projection');
  await tab('farm'); await shot('live-farm');
  const row = await p.$('[data-job]'); if (row) { await row.click(); await p.waitForTimeout(600); await shot('live-farm-job'); }
  await p.evaluate(() => { const h = [...document.querySelectorAll('.grp-h b')].find(x => x.textContent === 'Machines'); h && h.scrollIntoView({ block: 'start' }); });
  await p.waitForTimeout(500); await shot('live-farm-machines');
  await tab('shot');
  await p.keyboard.press('Control+k'); await p.waitForTimeout(500);
  await p.keyboard.type('bounc'); await p.waitForTimeout(700); await shot('live-search');
  await ctx.close();
  // phone
  const ph = await ctxFor(b, { ...devices['iPhone 13'], locale: 'en-US' });
  const m = await ph.newPage();
  m.on('pageerror', e => console.log('ERR m', e.message));
  await m.goto('http://127.0.0.1:8765/?t=demo'); await m.waitForTimeout(1500);
  await m.screenshot({ path: 'shots/live-phone-list.png' });
  for (const t of ['todo', 'farm']) {
    const el = await m.$(`[data-mtab="${t}"]`); if (el) { await el.click(); await m.waitForTimeout(700); await m.screenshot({ path: `shots/live-phone-${t}.png` }); } else console.log('no mtab', t);
  }
  console.log(await m.$$eval('[data-mtab]', e => e.map(x => x.dataset.mtab).join(',')));
  await b.close();
})();
