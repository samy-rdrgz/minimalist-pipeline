/* ---------- menus ---------- */
var MENUS=[['more','morepop'],['helpb','helppop'],['rv-more','rv-morepop']];
// A select drawn by the page: the system's own list takes no style. The
// select stays, hidden, holding the value -- its change event, its
// options, untouched; sync() after setting it from code.
function pick(sel){if(sel._pick)return sel._pick;
var w=document.createElement('span'),b=document.createElement('button'),m=document.createElement('div');
w.className='pick-w';b.type='button';b.className=sel.className+' pick';b.setAttribute('aria-haspopup','listbox');b.setAttribute('aria-expanded','false');
if(sel.getAttribute('aria-label'))b.setAttribute('aria-label',sel.getAttribute('aria-label'));
m.className='pick-pop';m.hidden=true;m.setAttribute('role','listbox');
sel.parentNode.insertBefore(w,sel);w.appendChild(sel);w.appendChild(b);sel.hidden=true;sel.tabIndex=-1;
// Its list in the body: a bar moved by a transform would carry it off.
m._button=b;document.body.appendChild(m);
function sync(){var o=sel.options[sel.selectedIndex];b.textContent=o?(o.dataset.short||o.textContent):'';
['on','need'].forEach(function(c){b.classList.toggle(c,sel.classList.contains(c));});}
b.onclick=function(e){e.stopPropagation();var open=!m.hidden;closeMenus();closePicks();if(open)return;
m.innerHTML=[].map.call(sel.options,function(o,i){return '<button type="button" role="option" data-i="'+i+'" aria-selected="'+(i===sel.selectedIndex)+'">'+esc(o.textContent)+'</button>';}).join('');
// Fixed, from the button: a scrolling bar or a panel would clip it.
var r=b.getBoundingClientRect(),up=r.top>innerHeight/2;m.style.left=Math.max(8,Math.min(r.left,innerWidth-Math.max(r.width,200)-8))+'px';m.style.minWidth=r.width+'px';
m.style.top=up?'':(r.bottom+6)+'px';m.style.bottom=up?(innerHeight-r.top+6)+'px':'';
// Focused for the keys -- never on a touch screen, where a focus in a
// fixed layer scrolls the page on an iPad (and that scroll closed it).
m.hidden=false;b.setAttribute('aria-expanded','true');pickOpenedAt=Date.now();touchHold();
if(!touchPin.matches)(m.querySelector('[aria-selected="true"]')||m.firstChild).focus({preventScroll:true});};
m.onclick=function(e){var o=e.target.closest('[data-i]');if(!o)return;e.stopPropagation();sel.selectedIndex=+o.dataset.i;closePicks();
sel.dispatchEvent(new Event('change'));sync();if(!touchPin.matches)b.focus({preventScroll:true});};
m.onkeydown=function(e){var f=[].slice.call(m.children),k=f.indexOf(document.activeElement);
if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();var n=f[Math.max(0,Math.min(f.length-1,k+(e.key==='ArrowDown'?1:-1)))];if(n)n.focus({preventScroll:true});}
else if(e.key==='Escape'||e.key==='Tab'){if(e.key==='Escape'){e.preventDefault();e.stopPropagation();}closePicks();b.focus({preventScroll:true});}};
sel._pick={sync:sync,button:b};sync();return sel._pick;}
function closePicks(){document.querySelectorAll('.pick-pop').forEach(function(m){if(!m.hidden){m.hidden=true;m._button.setAttribute('aria-expanded','false');}});touchHold();}
// A touch screen: the page under an open list or menu is held still
// (lockPage, 'pop') -- not put back after an iPad scrolled it, each
// putting back a jump of its own. The list or menu closes on a tap
// elsewhere, not on a scroll.
var touchPin=matchMedia('(pointer:coarse)');
function touchHold(){var on=touchPin.matches&&([].some.call(document.querySelectorAll('.pick-pop'),function(m){return !m.hidden;})||
MENUS.some(function(m){return !$(m[1]).hidden;}));lockPage('pop',on);}
function sync(id){var s=$(id);if(s&&s._pick)s._pick.sync();}
// Turned, a list closes (its place is gone); a touch screen's height
// moving (the keyboard, the browser's bars) leaves it open.
var pickW=innerWidth;
document.addEventListener('click',closePicks);addEventListener('resize',function(){if(touchPin.matches&&innerWidth===pickW)return;pickW=innerWidth;closePicks();});
// A scroll closes an open list -- not one the browser makes as it opens
// (iOS scrolls on a focus all the same, sometimes).
var pickOpenedAt=0;
document.addEventListener('scroll',function(e){if(touchPin.matches||Date.now()-pickOpenedAt<400)return;if(!(e.target.closest&&e.target.closest('.pick-pop')))closePicks();},true);
function closeMenus(){MENUS.forEach(function(m){$(m[1]).hidden=true;$(m[0]).setAttribute('aria-expanded','false');});touchHold();}
MENUS.forEach(function(m){$(m[0]).addEventListener('click',function(e){e.stopPropagation();var open=$(m[1]).hidden;closeMenus();
$(m[1]).hidden=!open;this.setAttribute('aria-expanded',open);touchHold();});});
document.addEventListener('click',function(e){if(!e.target.closest('.menu-pop'))closeMenus();});

