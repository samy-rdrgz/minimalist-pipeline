/* ---------- Actions de revue (couche partagée) ----------
   Les seules fonctions qui modifient les fichiers. Desktop et mobile les appellent, puis refresh().
   Aucune ne touche au DOM. Chacune correspond à une action de lib/review_import.py (indiquée en fin de ligne). */
const canVal=(it,d)=>!!S.review&&S.review.role!=='équipe'&&['done','rework'].includes(it.states[d])&&!it.ok[d];
const rangeStr=()=>S.rangeStart!=null&&S.rangeStart!==S.frame?'f'+Math.min(S.rangeStart,S.frame)+'-'+Math.max(S.rangeStart,S.frame):'f'+S.frame;
const jobId=()=>'job_'+Math.random().toString(16).slice(2,12);
const A={
  validate(it,d){it.mine[d]='val'},                                                         // validate
  toggleVal(it,d){if(it.mine[d]==='val')delete it.mine[d];else it.mine[d]='val'},             // validate / unvalidate
  validateAll(it){let n=0;required(it).forEach(d=>{if(canVal(it,d)&&!it.rtk[d]&&!it.mine[d]){it.mine[d]='val';n++}});return n},
  undo(it,d){delete it.mine[d];it.myNotes=it.myNotes.filter(n=>n.dept!==d||n.type!=='rtk')},
  toggleRtk(it,d){if(it.mine[d]==='rtk'){A.undo(it,d);return false}it.mine[d]='rtk';return true}, // rtk
  note(it,{type,dept,text,frames}){                                                         // note (frames, departments)
    it.myNotes.unshift({type,deps:dept?[dept]:[],dept,text,frames:frames||'',author:S.review.name,date:new Date().toISOString(),replies:[],at:Date.now()});
    if(type==='rtk'&&dept)it.mine[dept]='rtk'},
  unnote(it,at){const n=it.myNotes.find(x=>String(x.at)===String(at));it.myNotes=it.myNotes.filter(x=>x!==n);
    if(n&&n.type==='rtk'&&n.dept&&!it.myNotes.some(x=>x.dept===n.dept&&x.type==='rtk'))delete it.mine[n.dept]},
  reply(it,id,text){if(!text)return;(it.myReplies[id]=it.myReplies[id]||[]).push({text,author:S.review.name,date:new Date().toISOString()})}, // reply
  unreply(it,id){it.myReplies[id]?.pop();if(!it.myReplies[id]?.length)delete it.myReplies[id]},
  fixed(it,id){if(it.fixed[id])delete it.fixed[id];else it.fixed[id]=true},                 // fixed
  still(it,d){if(it.still[d])delete it.still[d];else it.still[d]=true},                     // still_done
  assignToggle(it,d,p){let a=[...assignOf(it,d)];a=!p?[]:a.includes(p)?a.filter(x=>x!==p):[...a,p];  // assign
    it.assign=it.assign||{};it.assign[d]=a;
    if(JSON.stringify(a)===JSON.stringify(it.assignees[d]||[])){delete it.assign[d];if(!Object.keys(it.assign).length)it.assign=null}return a},
  setReq(it,d,on){if(!it.req){it.req={};DEPTS[it.kind].forEach(x=>it.req[x]=x in it.states)}it.req[d]=on}, // departments (add / remove)
  toggleReq(it,d){A.setReq(it,d,!required(it).includes(d))},
  omit(it,state,reason=''){it.setAside=state?{state,reason}:null},                          // omit (on_hold / cancelled)
  omitReason(it,r){it.setAside={...(it.setAside||it.omit||{}),reason:r}},
  desc(it,v){if(v!==it.desc)it.descEdit=v;else delete it.descEdit},                         // description
  plan(p){S.planned.push(p)},unplan(i){S.planned.splice(i,1)},                              // create (shot / asset)
  /* Ce que la revue contient : le résumé lisible et le fichier à importer dans Blender. */
  changes(){const ch=[];items.filter(touched).forEach(it=>{Object.entries(it.mine).forEach(([d,v])=>ch.push(`${it.name} · ${LBL[d]} : ${v==='val'?'validé':'retake'}`));
    it.myNotes.forEach(n=>ch.push(`${it.name} · ${n.type==='rtk'?'retake':'remarque'}${n.dept?' '+LBL[n.dept]:''}${n.frames?' '+n.frames:''}`));
    Object.values(it.myReplies).flat().forEach(()=>ch.push(`${it.name} · réponse`));
    if(it.setAside!==undefined)ch.push(`${it.name} · ${it.setAside&&it.setAside.state?(it.setAside.state==='cancelled'?'annulé':'en pause'):'actif à nouveau'}`);
    if(it.req)ch.push(`${it.name} · départements requis modifiés`);Object.keys(it.still).forEach(d=>ch.push(`${it.name} · ${LBL[d]} : toujours fini`));
    Object.keys(it.fixed).forEach(()=>ch.push(`${it.name} · note marquée corrigée`));if(it.assign)Object.entries(it.assign).forEach(([d,a])=>ch.push(`${it.name} · ${LBL[d]} → ${a.join(', ')||'personne'}`));
    if(it.descEdit!==undefined)ch.push(`${it.name} · description`)});S.planned.forEach(p=>ch.push(`${p.name} · nouveau ${p.kind==='shot'?'plan':'fichier'}`));return ch},
  exportJSON(){return JSON.stringify({format:'minimalist-pipeline-review',project:M.project,base:M.snapshot,reviewer:S.review.name,role:S.review.role,date:new Date().toISOString(),
    items:items.filter(touched).map(it=>({name:it.name,validated:Object.keys(it.mine).filter(d=>it.mine[d]==='val'),notes:it.myNotes.map(({type,deps,text,frames})=>({type,deps,text,frames})),
      replies:it.myReplies,omit:it.setAside,required:it.req,assign:it.assign||undefined,still_done:Object.keys(it.still),fixed:Object.keys(it.fixed),description:it.descEdit})),
    create:S.planned.map(({name,kind,desc,deps})=>({name,kind,description:desc,departments:deps}))},null,1)},
  /* Live seulement : envoyé à Blender par POST /farm. */
  queueJob(o){const j={id:jobId(),key:'',shot:'',state:'waiting',text:'queued',done:0,total:0,machines:0,user:M.live.user,at:new Date().toISOString(),stage:'pending',
    priority:10,preset:'',department:'',range:null,names:[],pending:true,retry:false,recompile:false,removable:true,...o};F.jobs.unshift(j);return j},
  job(k,j){if(k==='remove'||k==='archive')j.archived=true;if(k==='cancel'){j.state='failed';j.text='annulé';j.retry=true}
    if(k==='retry'){j.state='waiting';j.text='queued';j.stage='pending';j.retry=false;j.removable=true}
    return {remove:'retiré de la file',archive:'archivé',cancel:'annulé',retry:'relancé',recompile:'recompilation'}[k]+' · '+j.file},
};
