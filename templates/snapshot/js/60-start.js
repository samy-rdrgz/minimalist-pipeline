/* ---------- start ---------- */
try{var kept=JSON.parse(localStorage.getItem(KEY)||'null');if(kept&&kept.files){rv=kept;rv.date=rv.date||'';rv.creates=rv.creates||[];
$('author').value=rv.author||'';$('role').value=rv.role||'';sync('role');
if(summary().files){document.body.classList.add('reviewing');try{if(localStorage.getItem(FOLD)==='1'&&rv.author)document.body.classList.add('rb-folded');}catch(e){}setTimeout(function(){toast('Your review in progress is back (kept in this browser).');},300);}}}catch(e){}
// The opening's motions (page.css "small motions"), once: not at each redraw.
document.body.classList.add('intro');setTimeout(function(){document.body.classList.remove('intro');},1400);
summaryCards();drawTabs();render();barHeight();
