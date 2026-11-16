/* ---------- badges: only what the row shows nowhere else ---------- */
// The small icons of the tags (stand-ins for Blender's, see NOTES.md).
var IC={eye:'<path d="M1.5 8s2.4-4.5 6.5-4.5S14.5 8 14.5 8 12.1 12.5 8 12.5 1.5 8 1.5 8z" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="8" cy="8" r="2" fill="currentColor"/>',
time:'<circle cx="8" cy="8" r="6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 4.6V8l2.4 1.6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>',
render:'<rect x="1.5" y="3" width="13" height="10" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.8v4.4L10.2 8z" fill="currentColor"/>',
cancel:'<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
warn:'<path d="M8 2l6.5 11.5h-13z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M8 6.5v3.2M8 11.6v.1" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
// The player's, after Blender's PLAY, PAUSE, FRAME_PREV / NEXT, REW / FF,
// FULLSCREEN_ENTER / EXIT.
play:'<path d="M4.5 2.8v10.4c0 .6.6 1 1.1.7l8-5.2c.5-.3.5-1 0-1.3l-8-5.2c-.5-.4-1.1 0-1.1.6z" fill="currentColor"/>',
pause:'<rect x="3.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/><rect x="9.5" y="2.5" width="3" height="11" rx="1" fill="currentColor"/>',
fprev:'<rect x="3" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M12.5 3.6v8.8c0 .5-.5.8-.9.5L6 8.5c-.4-.3-.4-.8 0-1.1l5.6-4.3c.4-.3.9 0 .9.5z" fill="currentColor"/>',
fnext:'<rect x="11" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M3.5 3.6v8.8c0 .5.5.8.9.5L10 8.5c.4-.3.4-.8 0-1.1L4.4 3.1c-.4-.3-.9 0-.9.5z" fill="currentColor"/>',
rew:'<rect x="1.5" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M9 3.8v8.4L4.5 8zM14.5 3.8v8.4L10 8z" fill="currentColor" stroke="currentColor" stroke-width=".8" stroke-linejoin="round"/>',
ff:'<rect x="12.5" y="3" width="2" height="10" rx=".8" fill="currentColor"/><path d="M7 3.8v8.4L11.5 8zM1.5 3.8v8.4L6 8z" fill="currentColor" stroke="currentColor" stroke-width=".8" stroke-linejoin="round"/>',
fsin:'<path d="M2.5 6V2.5H6M10 2.5h3.5V6M13.5 10v3.5H10M6 13.5H2.5V10" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
fsout:'<path d="M6 2.5V6H2.5M13.5 6H10V2.5M10 13.5V10h3.5M2.5 10H6v3.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>',
trash:'<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/>',
export:'<path d="M8 10.5V2.5M5 5.5l3-3 3 3M3 10v3.5h10V10" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
review:'<path d="M10.5 2.5l3 3L6 13H3v-3z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>',
check:'<path d="M3 8.5l3.2 3L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
reply:'<path d="M6 4L2.5 7.5 6 11M2.5 7.5H10a3.5 3.5 0 0 1 3.5 3.5V12" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>',
sound:'<path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill="currentColor"/><path d="M10.5 5.5a3.5 3.5 0 0 1 0 5M12 3.5a6 6 0 0 1 0 9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>',
text:'<path d="M3.5 2.5h9v11h-9z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>',
range:'<path d="M4.5 3H3v10h1.5M11.5 3H13v10h-1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><circle cx="8" cy="8" r="2.6" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M8 6.6V8l.9.7" fill="none" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
mute:'<path d="M2.5 6h2.5l3.5-3v10l-3.5-3H2.5z" fill="currentColor"/><path d="M10.5 6l4 4M14.5 6l-4 4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'};
// Blender's own where the page has it (icon_sprite(): "b-<name>", its
// file in templates/snapshot/icons), else the stand-in above.
var BI={play:'b-play',pause:'b-pause',fprev:'b-frame_prev',fnext:'b-frame_next',rew:'b-rew',ff:'b-ff',eye:'b-hide_off',
trash:'b-trash',import:'b-import',export:'b-export',user:'b-user',movie:'b-file_movie',prevk:'b-prev_keyframe',nextk:'b-next_keyframe',link:'b-decorate_linked',
time:'b-time',render:'b-render_still',cancel:'b-cancel',warn:'b-status_warning',fsin:'b-fullscreen_enter',fsout:'b-fullscreen_exit',
review:'b-greasepencil',help:'b-question',filter:'b-filter',search:'b-viewzoom',folder:'b-file_folder',check:'b-checkmark',team:'b-community',reply:'b-file_parent',text:'b-text',box:'b-checkbox_dehlt',settings:'b-preferences',range:'b-preview_range'};
function ico(n){return BI[n]&&document.getElementById(BI[n])?'<svg class="ico bi-'+n+'" aria-hidden="true"><use href="#'+BI[n]+'"/></svg>':
'<svg class="ico" viewBox="0 0 16 16" aria-hidden="true">'+IC[n]+'</svg>';}
function tag(cls,icon,text,tip){return '<span class="tg tg-'+cls+'"'+(tip?' title="'+esc(tip)+'"':'')+'>'+(icon?ico(icon):'')+esc(text)+'</span>';}
// Under a file's name: a retake on no department, then its renders' tags
// -- to check, outdated, in the farm (queued, rendering, failed).
function flags(it){var h='',e=peek(it);
if(it.genRtks.length){var tm=it.genRtks.every(function(n){return n.team;});
h+='<span class="inl" title="An open retake on no department: it holds back every department"><span class="pi pi-gen pi-'+(tm?'team':'role')+'">'+(it.genRtks.length>1?it.genRtks.length+' general RTK':'General RTK')+'</span></span>';}
// A retake on no department in your review: the departments' own ✕ you.
var gen=answered(it).gen;
if(e.text.trim()||gen)h+='<span class="inl">'+(noteOnly(e.text)&&!gen?youNote():'<span class="you n" title="A retake on no department, in your review">✕ YOU</span>')+'</span>';
// Set aside, or changed in your review: as it'll be, ✎ you.
var om=omitChanged(it,e)?e.omit:it.omit;
if(om&&om.state)h+=tag('check','',(om.state==='cancelled'?'Cancelled':'On hold')+(om.reason?': '+om.reason:''),'Set aside: out of the figures');
else if(om)h+=tag('check','','Active again','Counted again in your review');
if(omitChanged(it,e))h+='<span class="inl"><span class="you nt" title="Set aside or back in your review">✎ YOU</span></span>';
if(it.to_check)h+=tag('check','eye','render to check','Rendered, not checked by the team yet');
if(it.outdated)h+=tag('old','warn','render outdated','Rendered from an older version than the last stable');
if(it.farm){var k=it.farm.state==='failed'?'fail':it.farm.state==='waiting'?'wait':'run';
h+=tag(k,k==='fail'?'cancel':k==='wait'?'time':'render','farm '+it.farm.text,'In the farm: '+it.farm.tip);}
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)h+=tag('check','','✎ description','Your review changes its description');
// Who a department is assigned to, changed in your review.
var ac=Object.keys(e.assign||{}),to=function(d){return cap(d)+' → '+(e.assign[d].join(', ')||'nobody');};
if(ac.length)h+=tag('check','user',ac.length===1?to(ac[0]):ac.length+' departments reassigned','Assigned in your review: '+ac.map(to).join(' · '));
return h;}
function subline(it){var p=['<span class="vers">'+esc(it.versions||'not saved yet')+'</span>'];
if(it.shots.length>1)p.push('<span>'+plural(it.shots.length,'shot')+'</span>');
if(it.openNotes.length){var t=it.openNotes.some(function(n){return n.type==='todo';});
p.push('<span class="nn'+(t?' todo':'')+'">'+plural(it.openNotes.length,'open note')+'</span>');}
return p.join('<i class="sep"> · </i>');}
