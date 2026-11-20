/* ---------- Live: share with a phone (lib/monitoring/live.py /share, lib/monitoring/qr.py) ----------
   An access for someone on the studio's network, or on the same VPN: their name, role, how
   long (a week at most) -- a link and its QR code, Copy link beside; the accesses running,
   each revoked in a click. A guest reviews as themselves: the farm read only, nothing opened
   on this machine (.host-only hidden). */
const guest = () => !!(M.live && M.live.guest);
let SHARE_IP = '',
  SHARE_FARM = false;
const SHARE_TIMES = () => [
  ['1', T('1 hour')],
  ['eod', T('Until tonight')],
  ['24', T('1 day')],
  ['168', T('1 week')]
];
/* An end: its time today, else its day and time. */
function fmtUntil(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return esc(iso || '');
  return d.toDateString() === new Date().toDateString() ? d.toLocaleTimeString(DTL(), HM) : fmtD(iso);
}
function shareDialog() {
  const dl = $('#dlg');
  dl.hidden = false;
  dl.innerHTML = `<div class="dlg-in sh-dlg" role="dialog" aria-modal="true" aria-labelledby="sh-t"><h3 id="sh-t">${T('Share with a phone')}</h3><div id="sh-body"><p class="faint">${T('Reading…')}</p></div>
    <div class="acts"><span style="flex:1"></span><button class="btn" data-dclose>${T('Done')}</button></div></div>`;
  dl.onclick = e => {
    const b = e.target.closest('[data-shrev]');
    if (b) return shareSend({ revoke: b.dataset.shrev });
    if (e.target.closest('#sh-make')) {
      const n = $('#sh-name').value.trim();
      if (!n) {
        $('#sh-name').focus();
        return;
      }
      const ip = $('#sh-ip');
      if (ip) SHARE_IP = ip.value;
      return shareSend({
        name: n,
        role: $('#sh-role').value,
        hours: $('#sh-time').value,
        ip: SHARE_IP,
        farm: SHARE_FARM
      });
    }
    const sf = e.target.closest('[data-shfarm]');
    if (sf) {
      SHARE_FARM = sf.dataset.shfarm === '1';
      dl.querySelectorAll('[data-shfarm]').forEach(b => b.setAttribute('aria-pressed', b === sf));
      return;
    }
    if (e.target.closest('#sh-copy')) copyShareLink($('#sh-link').value);
  };
  shareSend({});
}
function shareSend(body) {
  const late = setTimeout(() => {
    const b = $('#sh-body');
    if (b && !b.querySelector('.sh-form'))
      b.innerHTML = `<p class="faint">${T("Blender doesn't answer -- busy, or this page is open in many tabs (each holds a connection): close the others.")}</p>`;
  }, 10000);
  livePost('share', body)
    .then(res => {
      clearTimeout(late);
      if (!res.ok) {
        toast(T('Not shared: {error}', { error: res.error || '?' }));
        if (!$('#sh-body').querySelector('.sh-form')) shareDraw(res);
        return;
      }
      shareDraw(res);
    })
    .catch(() => {
      clearTimeout(late);
      noAnswer();
    });
}
function shareDraw(res) {
  const roles = [TEAM, ...(M.roles || []).filter(r => r !== TEAM)],
    ad = res.addresses || [];
  let h = '';
  if (ad.length) SHARE_IP = SHARE_IP && ad.some(a => a.ip === SHARE_IP) ? SHARE_IP : ad[0].ip;
  if (res.link)
    h += `<div class="sh-made"><div class="sh-qr">${res.qr}</div><div class="sh-info"><span><b>${esc(res.name)}</b> · ${esc(res.role)}${res.farm ? ' · ' + T('drives the farm') : ''}</span><small class="faint">${T('until {when}', { when: fmtUntil(res.until) })}</small>
    <p class="faint">${res.via === 'VPN' ? T('Scan it on a device on the same VPN, wherever it is -- or send the link:') : T("Scan it on the same network (the studio's Wi-Fi) -- or send the link:")}</p>
    <label class="field"><input id="sh-link" readonly value="${esc(res.link)}" aria-label="${T('Link')}"></label><button class="btn" id="sh-copy">${ic('b-linked')}${T('Copy link')}</button></div></div>`;
  h += `<div class="sh-form">
    <div class="prop"><span class="k">${T('Name')}</span><span class="v"><label class="field" style="flex:1"><input id="sh-name" maxlength="40" placeholder="${T('Who it is for')}" autocomplete="off"></label></span></div>
    <div class="prop"><span class="k">${T('Role')}</span><span class="v"><label class="field" style="flex:1"><select id="sh-role">${roles.map(r => `<option${r === TEAM ? ' selected' : ''}>${esc(r)}</option>`).join('')}</select></label></span></div>
    ${ad.length > 1 ? `<div class="prop"><span class="k">${T('Reached through')}</span><span class="v"><label class="field" style="flex:1"><select id="sh-ip">${ad.map(a => `<option value="${esc(a.ip)}"${a.ip === SHARE_IP ? ' selected' : ''}>${esc(a.kind)} · ${esc(a.ip)}</option>`).join('')}</select></label></span></div>` : ''}
    <div class="prop"><span class="k">${T('For')}</span><span class="v"><label class="field" style="flex:1"><select id="sh-time">${SHARE_TIMES()
      .map(([v, l]) => `<option value="${v}"${v === 'eod' ? ' selected' : ''}>${l}</option>`)
      .join('')}</select></label></span></div>
    <div class="prop"><span class="k">${T('Farm')}</span><span class="v"><span class="join full" style="flex:1"><button class="btn" data-shfarm="0" aria-pressed="${!SHARE_FARM}">${T('Read only')}</button><button class="btn" data-shfarm="1" aria-pressed="${SHARE_FARM}" title="${T('Launch and stop it, send renders, change priorities: for yourself, away from the studio')}">${T('Can drive it')}</button></span></span></div>
    <div class="acts"><span style="flex:1"></span><button class="btn primary" id="sh-make">${T('Make the access')}</button></div></div>
    <p class="hint">${T('They review as that name and role -- notes, validations, assignees; the farm read only unless they may drive it; nothing opened on this machine. Blender stays open here for it to work.')}</p>`;
  const g = res.guests || [];
  if (g.length)
    h +=
      `<div class="sec-h">${T('Running')}</div>` +
      g
        .map(
          x =>
            `<div class="sh-g"><span><b>${esc(x.name)}</b> · ${esc(x.role)}${x.farm ? ' · ' + T('drives the farm') : ''} · ${T('until {when}', { when: fmtUntil(x.until) })}${x.ip ? ` <small class="faint">${esc(x.ip)}</small>` : ''}</span><button class="btn sm alert" data-shrev="${esc(x.token)}">${T('Revoke')}</button></div>`
        )
        .join('');
  $('#sh-body').innerHTML = h;
}
function copyShareLink(t) {
  const sel = () => {
    $('#sh-link').select();
    toast(T('Selected: copy it with Ctrl+C.'));
  };
  if (navigator.clipboard && navigator.clipboard.writeText)
    navigator.clipboard.writeText(t).then(() => toast(T('Link copied')), sel);
  else sel();
}
/* Update links (lib/relink.py): a new -relink version, written without opening the file, its links on their latest stables. */
function relinkSend(files) {
  livePost('relink', { files })
    .then(res => {
      const sk = (res.skipped || []).map(x => x[0] + ' (' + x[1] + ')').join(', ');
      toast(
        res.ok
          ? T('Updating {n} file in the background|Updating {n} files in the background', {
              n: (res.started || []).length
            }) + (sk ? ' -- ' + T('left: {what}', { what: sk }) : '')
          : T('Not updated: {error}', { error: res.error || sk || '?' })
      );
    })
    .catch(noAnswer);
}
