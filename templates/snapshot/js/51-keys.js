/* ---------- keys, as the page before ---------- */
document.addEventListener('keydown',function(e){var t=e.target;
if(t.matches&&t.matches('input,textarea,select')){if(e.key==='Escape'){t.blur();e.preventDefault();}
else if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)){t.blur();e.preventDefault();}return;}
if(e.altKey||e.ctrlKey||e.metaKey)return;
if(!$('lb').hidden){if(e.key==='Escape'){closeLb();e.preventDefault();}
else if(e.key==='ArrowLeft'||e.key==='ArrowRight'){var nb=$('lb').querySelector('[data-lb="'+(e.key==='ArrowLeft'?-1:1)+'"]');if(nb&&!nb.disabled){nb.click();e.preventDefault();}}
return;}
// Watch large: Esc back to the panel; Space, , . and ← → the videos.
if(!$('wl').hidden){var kk=e.key;if(kk==='Escape')closeWatch();else if(kk===' '&&PL){if(PL.el.paused)PL.el.play();else PL.el.pause();}
else if(kk===','||kk==='.')stepFrame(kk===','?-1:1);else if(kk==='m'&&PL)setMuted(!PL.el.muted);else if(kk==='ArrowLeft'||kk==='ArrowRight')nextVideo(kk==='ArrowLeft'?-1:1);else return;e.preventDefault();return;}
if(!$('dlg').hidden){if(e.key==='Escape'){$('dlg').hidden=true;e.preventDefault();}return;}
// "/": go to a file.
if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();$('q').focus();return;}
if(e.key==='Escape'&&MENUS.some(function(m){return !$(m[1]).hidden;})){closeMenus();return;}
if(cur==null)return;var k=e.key.toLowerCase();
if(PL&&PL.mode==='panel'&&PL.it===D[cur]&&(k===' '||k===','||k==='.'||k==='m')){if(k===' '){if(PL.el.paused)PL.el.play();else PL.el.pause();}else if(k==='m')setMuted(!PL.el.muted);else stepFrame(k===','?-1:1);}
else if(k==='arrowleft')step(-1);else if(k==='arrowright')step(1);else if(k==='escape')closePanel();
else if(reviewing()&&k==='v')validateAll();else if(reviewing()&&k==='x')generalRetake();
else if(reviewing()&&k==='r'&&document.activeElement&&document.activeElement.closest&&document.activeElement.closest('#p-body details.th'))startReply(document.activeElement.closest('details.th').dataset.th);
else return;e.preventDefault();});

