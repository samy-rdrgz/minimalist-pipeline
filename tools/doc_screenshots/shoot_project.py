"""The docs' live-page screenshots, from a Blender serving the demo project (U) and an exported snapshot (SNAP)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
U, SNAP, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3]); OUT.mkdir(exist_ok=True)
W = dict(viewport={'width': 1440, 'height': 860}, device_scale_factor=2, locale='en-US', color_scheme='dark')
def scroll_to(p, sel, text):
    p.evaluate("""([s, t]) => { const h = [...document.querySelectorAll(s)].find(x => x.textContent.trim() === t); if (h) h.scrollIntoView({block: 'start'}); return !!h; }""", [sel, text])
    p.wait_for_timeout(600)
with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(**W); p = ctx.new_page()
    p.on('pageerror', lambda e: print('ERR', e))
    shot = lambda n: p.screenshot(path=str(OUT / f'{n}.png'))
    tab = lambda ws: (p.click(f'[data-ws="{ws}"]'), p.wait_for_timeout(1200))
    p.goto('file://' + SNAP); p.wait_for_timeout(2500)
    shot('tracking-snapshot-details')
    tab('synth'); shot('tracking-snapshot-progress')
    p.goto(U); p.wait_for_timeout(5000)
    shot('live-shots')
    tab('todo'); shot('live-todo')
    tab('synth'); shot('live-breakdown')
    for t, n in (('Activity', 'live-breakdown-activity'), ('Projection', 'live-breakdown-projection')):
        el = p.evaluate_handle("t => [...document.querySelectorAll('.ot-h b')].find(x => x.textContent.trim() === t).closest('.ot')", t).as_element()
        el.scroll_into_view_if_needed(); p.wait_for_timeout(600); el.screenshot(path=str(OUT / f'{n}.png'))
    tab('farm'); shot('live-farm')
    row = p.query_selector('[data-job]')
    if row: row.click(); p.wait_for_timeout(1500); shot('live-farm-job')
    scroll_to(p, '.grp-h b', 'Machines'); shot('live-farm-machines')
    tab('shot')
    p.keyboard.press('Control+k'); p.wait_for_timeout(600)
    p.keyboard.type(sys.argv[4] if len(sys.argv) > 4 else 'parcel'); p.wait_for_timeout(1200); shot('live-search')
    ctx.close()
    ph = b.new_context(**pw.devices['iPhone 13'], locale='en-US', color_scheme='dark'); m = ph.new_page()
    m.on('pageerror', lambda e: print('ERR m', e))
    m.goto(U); m.wait_for_timeout(5000)
    m.screenshot(path=str(OUT / 'live-phone-list.png'))
    for t in ('todo', 'farm'):
        el = m.query_selector(f'[data-mtab="{t}"]')
        if el: el.click(); m.wait_for_timeout(1200); m.screenshot(path=str(OUT / f'live-phone-{t}.png'))
        else: print('no mtab', t)
    b.close()
