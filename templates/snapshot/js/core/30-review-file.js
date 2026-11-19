/* ---------- The review as a file: what lib/monitoring/review_import.py reads ----------
   The changes a review left on the files (A.*) written as its actions
   (REVIEW_JSON_FORMAT: validate, unvalidate, rtk, note, reply, fixed, edit, delete, done, still_done,
   departments, assign, omit, description, create), read back from one, and kept
   in this browser until sent. No DOM here. */
const TEAM='team';
/* Written as the team (no validation role of that name): retakes and remarks, no validation. */
const asTeam=()=>!!S.review&&S.review.role===TEAM&&!(M.roles||[]).includes(TEAM);
const digits=s=>String(s||'').replace(/\D/g,'');
/* "f12" / "f12-23" → [12, null] / [12, 23]. */
function framesOf(t){const m=/^f?(\d+)(?:-(\d+))?$/.exec(String(t||'').trim());return m?[+m[1],m[2]!=null?+m[2]:null]:null}
function framesStr(f){return f?'f'+f[0]+(f[1]!=null?'-'+f[1]:''):''}
/* A planned file as create wants it: a shot's sequence and shot numbers, an asset's prefix and name. */
function createOf(p){const nm=M.naming||{},sp=(nm.shot||{}).prefix||'sh',o={type:'create',file:p.name,kind:p.kind==='shot'?'shot':'asset',description:p.desc||'',departments:p.deps||[],assignees:p.assignees||{}};
  if(o.kind==='shot'){const part=p.name.split('_')[1]||'';o.sequence=digits(p.g||p.name.split('_')[0]);o.shot=part.startsWith(sp)?part.slice(sp.length):digits(part);
    if(p.frame_start!=null)o.frame_start=p.frame_start;if(p.frame_end!=null)o.frame_end=p.frame_end}
  else{const i=p.name.indexOf('_');o.prefix=i>0?p.name.slice(0,i):(p.g||'');o.name=i>0?p.name.slice(i+1):p.name}
  return o}
function reviewActions(){const out=[],team=asTeam();
  items.forEach(it=>{const f=it.file,seen=it.stableFile||'',ref=it.render||'',said={};
    const shot=it.shots&&it.shots.length>1&&S.shot[it.name]?digits(S.shot[it.name]):'';
    Object.entries(it.mine).forEach(([d,v])=>{said[d]=1;
      if(v==='val'){if(!team)out.push({type:'validate',file:f,department:d,seen});return}
      if(!team)out.push({type:'unvalidate',file:f,department:d,seen})});
    it.myNotes.slice().reverse().forEach(n=>{const deps=n.deps&&n.deps.length?n.deps:(n.dept?[n.dept]:[]);
      // A retake withdraws the validation of its department; a remark leaves it.
      if(n.type==='rtk'&&!team)deps.forEach(d=>{if(!said[d]){said[d]=1;out.push({type:'unvalidate',file:f,department:d,seen})}});
      out.push({type:n.type==='rtk'?'rtk':'note',file:f,departments:deps,text:n.text,shot:n.shot||shot,frames:framesOf(n.frames),render:ref})});
    if(it.descEdit!==undefined&&String(it.descEdit).trim()&&it.descEdit.trim()!==(it.desc||''))out.push({type:'description',file:f,old:it.desc||'',new:it.descEdit.trim()});
    Object.keys(it.fixed).forEach(id=>out.push({type:'fixed',file:f,id}));
    Object.entries(it.myReplies).forEach(([id,rs])=>{const t=rs.map(r=>r.text).join('\n').trim();if(t)out.push({type:'reply',file:f,to:id,text:t})});
    Object.entries(it.edits||{}).forEach(([id,t])=>out.push(t===null?{type:'delete',file:f,id}:{type:'edit',file:f,id,text:t}));
    Object.keys(it.marked).forEach(d=>out.push({type:'done',file:f,department:d,done:it.marked[d]}));
    Object.keys(it.still).forEach(d=>out.push({type:'still_done',file:f,department:d,text:''}));
    if(it.req){const now=Object.keys(it.states),add=Object.keys(it.req).filter(d=>it.req[d]&&!now.includes(d)),rem=Object.keys(it.req).filter(d=>!it.req[d]&&now.includes(d));
      if(add.length||rem.length)out.push({type:'departments',file:f,add,remove:rem})}
    if(it.setAside!==undefined){const was=it.omit||{},s=it.setAside||{state:'',reason:''};
      if((s.state||'')!==(was.state||'')||(s.state&&(s.reason||'')!==(was.reason||'')))out.push({type:'omit',file:f,state:s.state||'',reason:s.state?s.reason||'':''})}
    if(it.assign)Object.entries(it.assign).forEach(([d,p])=>out.push({type:'assign',file:f,department:d,people:p}))});
  S.planned.forEach(p=>out.push(createOf(p)));return out}
const isoNow=()=>{const d=new Date(),z=-d.getTimezoneOffset(),p=n=>String(Math.floor(Math.abs(n))).padStart(2,'0');
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate())+'T'+p(d.getHours())+':'+p(d.getMinutes())+':'+p(d.getSeconds())+(z>=0?'+':'-')+p(z/60)+':'+p(z%60)};
function reviewFile(){return {format:M.format,schema_version:M.schema_version,project:M.project,snapshot:M.snapshot,
  author:S.review?S.review.name:'',role:S.review?S.review.role:'',review_date:isoNow().slice(0,10),written_at:isoNow(),actions:reviewActions()}}
/* <project>_review_<YYYY-MM-DD_HH-MM>_<role>_<author>.json: two reviewers' files side by side, never one over the other. */
const slug=t=>String(t||'').normalize('NFD').replace(/[̀-ͯ]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'');
function reviewName(){const n=isoNow(),stamp=n.slice(0,10)+'_'+n.slice(11,13)+'-'+n.slice(14,16);
  return [(M.review_base||slug(M.project))+'_review_'+stamp,slug(S.review&&S.review.role),slug(S.review&&S.review.name)].filter(Boolean).join('_')+'.json'}
/* A review file read back: its actions as the changes they came from. Returns the files it names that aren't here. */
function fromActions(actions){const by={},unknown=new Set();items.forEach(it=>{by[it.file]=it;by[it.name]=it});
  (actions||[]).forEach((a,i)=>{if(a.type==='create'){S.planned.push({name:a.file,g:a.kind==='shot'?(((M.naming||{}).sequence||{}).prefix||'sq')+a.sequence:a.prefix,kind:a.kind==='shot'?'shot':'asset',desc:a.description||'',deps:a.departments||[],assignees:a.assignees||{}});return}
    const it=by[a.file];if(!it){unknown.add(a.file);return}
    if(a.type==='validate')it.mine[a.department]='val';
    else if(a.type==='unvalidate'){if(!it.mine[a.department])it.mine[a.department]='rtk'}
    else if(a.type==='rtk'||a.type==='note'){const d=(a.departments||[])[0]||null;
      it.myNotes.unshift({type:a.type,deps:a.departments||[],dept:d,text:a.text,frames:framesStr(a.frames),shot:a.shot||'',author:S.review?S.review.name:'',date:isoNow(),replies:[],at:Date.now()+i});
      if(a.type==='rtk'&&d)it.mine[d]='rtk'}
    else if(a.type==='reply')it.myReplies[a.to]=[{text:String(a.text||''),author:S.review?S.review.name:'',date:isoNow()}];
    else if(a.type==='fixed')it.fixed[a.id]=true;
    else if(a.type==='description')it.descEdit=a.new;
    else if(a.type==='edit')it.edits[a.id]=String(a.text||'');
    else if(a.type==='delete')it.edits[a.id]=null;
    else if(a.type==='done')it.marked[a.department]=a.done!==false;
    else if(a.type==='still_done')it.still[a.department]=true;
    else if(a.type==='departments'){(a.add||[]).forEach(d=>A.setReq(it,d,true));(a.remove||[]).forEach(d=>A.setReq(it,d,false))}
    else if(a.type==='omit')it.setAside={state:a.state||'',reason:a.reason||''};
    else if(a.type==='assign'){it.assign=it.assign||{};it.assign[a.department]=a.people||[]}});
  return [...unknown]}
/* Kept in this browser until sent: who reviews, and each file's changes. */
const RV_KEY='mp-review:'+M.project+':'+(LIVE?'live':M.snapshot);
const RV_FIELDS=['edits','marked','mine','myNotes','myReplies','setAside','req','assign','still','fixed','descEdit'];
function storeReview(){try{const files={};items.forEach(it=>{if(touched(it)){const o={};RV_FIELDS.forEach(k=>{if(it[k]!==undefined)o[k]=it[k]});files[it.name]=o}});
  if(!S.review&&!Object.keys(files).length&&!S.planned.length)localStorage.removeItem(RV_KEY);
  else localStorage.setItem(RV_KEY,JSON.stringify({review:S.review,planned:S.planned,files}))}catch(_){}
  if(typeof liveQueue==='function')liveQueue()}
function restoreReview(){try{const r=JSON.parse(localStorage.getItem(RV_KEY)||'null');if(!r)return;S.review=r.review||null;S.planned=r.planned||[];
  items.forEach(it=>{const o=(r.files||{})[it.name];if(o)Object.assign(it,o)})}catch(_){}}
function clearReview(){items.forEach(it=>Object.assign(it,fresh(),{descEdit:undefined}));S.planned=[];storeReview()}
