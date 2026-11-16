/* ---------- review state: as the page before (same key, same shape) ---------- */
// creates: the new shots and assets the review asks for (planned).
var rv={author:'',role:'',date:'',files:{},creates:[]};
// Live: what's on its way to Blender (liveSend()).
var LIVE_OUT={busy:false,again:false,sent:{},t:0,after:null,say:'live'};
// The live page's own state, set before anything draws: the Farm tab's
// jobs open, the panel's sections folded, the Render form per file.
var JOB_STATES=[['running','In progress','wip'],['waiting','Waiting','todo'],['failed','Failed','fail'],['finished','Finished','done']],JOPEN={},chkOpen=true,lnkOpen=false,rndOpen=false,RF={},FF={s:'',mine:false,q:''},JD={},WD={},WOPEN={},LKF={},JW={},
SHARE_IP='',SHARE_TIMES=[['1','1 hour'],['eod','Until tonight'],['24','1 day'],['168','1 week']];
var KEY='mp-review:'+META.project+':'+(META.live?'live':META.snapshot);
// synced: Still done per department; req: a department required added
// (true) or removed (false); omit: {state, reason} set aside or counted again.
function entry(it){var e=rv.files[it.file]||(rv.files[it.file]={deps:{},all:false,text:'',desc:null});e.fixed=e.fixed||{};e.replies=e.replies||{};e.synced=e.synced||{};e.req=e.req||{};e.assign=e.assign||{};return e;}
function peek(it){var e=rv.files[it.file]||{deps:{},all:false,text:'',desc:null,fixed:{},replies:{}};e.synced=e.synced||{};e.req=e.req||{};e.assign=e.assign||{};return e;}
// A file's own changes in the review: still done, departments, set aside,
// who a department is assigned to.
function fileChanges(it,e){return Object.keys(e.synced||{}).length+Object.keys(e.req||{}).length+(omitChanged(it,e)?1:0)+Object.keys(e.assign||{}).length;}
// Who a department is assigned to: as the review leaves it.
function people(it,d){var e=peek(it);return d in e.assign?e.assign[d]:((it.assignees||{})[d]||[]);}
// Me: the review's name (Review asks it), lower case as the team's.
function me(){return (rv.author||'').trim().toLowerCase();}
function mineDeps(it){var m=me();return m?Object.keys(it.states).filter(function(d){return people(it,d).indexOf(m)>=0;}):[];}
function omitChanged(it,e){return !!e.omit&&(e.omit.state!==((it.omit||{}).state||'')||(e.omit.state&&e.omit.reason!==((it.omit||{}).reason||'')));}
// The open notes this review replies to with a retake (anything but
// "note:" lines): still to redo -- their departments sent back as a ✕
// would ({deps}), the whole file's when they have none (gen).
function answered(it){var e=peek(it),ids=replies(e),out={deps:{},gen:false};if(!ids.length)return out;
it.notes.forEach(function(n){if(!n.closed&&ids.indexOf(n.id)>=0&&!noteOnly(e.replies[n.id])){
if(n.deps.length)n.deps.forEach(function(d){out.deps[d]=1;});else out.gen=true;}});return out;}
// Replies written, by the note they answer.
function replies(e){var r=e.replies||{};return Object.keys(r).filter(function(id){return (r[id]||'').trim();});}
function changes(it){var e=rv.files[it.file];if(!e)return 0;
var n=Object.keys(e.deps).filter(function(d){return sent(e.deps[d]);}).length+(e.all&&!asTeam()?1:0)+(e.text.trim()?1:0)+Object.keys(e.fixed||{}).length+replies(e).length;
if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)n++;return n+fileChanges(it,e);}
// What this review says of a department: 'ok' (its own ✓, or all done), 'no',
// 'note' (only "note:" lines: a remark, its validation left as it is), or ''.
// Written as the team (Role "team", no validation role of that name): its
// retakes and notes are the team's own, it validates nothing -- a ✓ or an
// empty ✕ (a validation withdrawn) is neither shown as yours nor sent.
function asTeam(){return rv.role==='team'&&(META.roles||[]).indexOf('team')<0;}
function sent(v){return !asTeam()||(!v.ok&&!!(v.text||'').trim());}
function verdict(it,d){var e=peek(it),v=e.deps[d];if(v&&sent(v))return v.ok?'ok':noteOnly(v.text)?'note':'no';
if(answered(it).deps[d])return 'no';
return e.all&&!asTeam()&&isDone(it.states[d])?'ok':'';}
function you(it,d){var v=verdict(it,d);if(!v)return '';
return v==='ok'?'<span class="you y" title="Validated in your review">✓ YOU</span>':v==='note'?youNote():
'<span class="you n" title="Sent back in your review">✕ YOU</span>';}
function youNote(){return '<span class="you nt" title="A note in your review: a remark, nothing withdrawn">✎ YOU</span>';}
// Written, and nothing but "note:" lines.
function noteOnly(t){return !!(t&&t.trim())&&retakes(t)===0;}
function notesIn(t){return (t||'').split(NL).filter(function(l){return NOTE_RE.test(l);}).length;}
// "note:" -- or "note :", "n:", any case -- after the line's tags: a remark
// (lib/review_import.py _NOTE_PREFIX, the same).
var NOTE_RE=/^\s*(?:\[[^\]]*\]\s*)*(?:note|n)\s*:/i;
function retakes(t){return t.split(NL).filter(function(l){var w=l.trim().split(' ').filter(function(x){return x&&x.charAt(0)!=='[';});
return w.length&&!NOTE_RE.test(l);}).length;}
function summary(){var c={files:0,ok:0,rt:0,out:0,desc:0,fixed:0,replies:0,notes:0,changes:0};D.forEach(function(it){if(!changes(it))return;var e=rv.files[it.file];c.files++;c.fixed+=Object.keys(e.fixed||{}).length;c.replies+=replies(e).length;c.changes+=fileChanges(it,e);
Object.keys(e.deps).forEach(function(d){var v=e.deps[d];if(!sent(v))return;if(v.ok)c.ok++;else if(v.text.trim()){c.rt+=retakes(v.text);c.notes+=notesIn(v.text);}else c.out++;});
var an=answered(it).deps;Object.keys(an).forEach(function(d){if(!e.deps[d]&&!asTeam())c.out++;});
if(e.all&&!asTeam())Object.keys(it.states).forEach(function(d){if(isDone(it.states[d])&&!e.deps[d]&&!an[d])c.ok++;});
c.rt+=retakes(e.text);c.notes+=notesIn(e.text);if(e.desc!==null&&e.desc.trim()&&e.desc.trim()!==it.desc)c.desc++;});c.creates=(rv.creates||[]).length;return c;}
function store(){try{localStorage.setItem(KEY,JSON.stringify(rv));}catch(e){}}
// Live (served by Blender): each change sent too, a moment later (liveSend()).
function save(){store();if(META.live&&reviewing())liveSend();}

