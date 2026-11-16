// The production snapshot page (lib/snapshot_page.py): everything below is
// drawn from the data the export embeds (#data). One file, offline, any
// browser; the review written here is kept in this browser and downloaded
// as the .json Import review reads (REVIEW_JSON_FORMAT).
(function(){
'use strict';
var $=function(id){return document.getElementById(id);};
var DATA=JSON.parse($('data').textContent),META=DATA.meta,D=DATA.items;
var TABS=[['shot','Shots'],['asset','Assets'],['library','Libraries']];
var LABEL={done:'Done',rework:'Done, reworked since',wip:'In progress',todo:'Not started'};
var NL=String.fromCharCode(10);
var esc=function(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){
return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});};
var cap=function(s){return s.charAt(0).toUpperCase()+s.slice(1);};
var pct=function(v){return v==null?'–':Math.round(v*100)+' %';};
function isDone(s){return s==='done'||s==='rework';}
function plural(n,w){return n+' '+w+(n===1?'':'s');}
// A note's author, nothing when not known (no "unknown").
function author(n){var a=(n.author||'').trim();return a&&a.toLowerCase()!=='unknown'?esc(a):'';}

/* ---------- images: each stored once (#data images), turned into blob URLs
once — short src strings, however often the list is redrawn ---------- */
var urls={};
function img(id){if(!id)return '';if(urls[id])return urls[id];
try{var b=atob(DATA.images[id]),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);
urls[id]=URL.createObjectURL(new Blob([a],{type:'image/jpeg'}));}
catch(e){urls[id]='data:image/jpeg;base64,'+DATA.images[id];}return urls[id];}

/* ---------- items ---------- */
// Made again from new data on the live page (applyData()).
var byFile={},byName={},byKey={},tabs=[];
function prepare(){byFile={};byName={};byKey={};
D.forEach(function(it,i){it.i=i;byFile[it.file]=it;byName[it.name]=it;if(it.live&&it.live.key)byKey[it.live.key]=it;
it.tab=it.root==='library'?'library':it.kind;
it.tracked=Object.keys(it.states).length>0;
var open=it.notes.filter(function(n){return !n.closed;});
// Open threads, by where the page shows them: an open RTK under its
// department (none: the general retakes), the rest as notes.
it.rtkNotes={};it.genRtks=[];it.otherNotes=[];
open.forEach(function(n){if(n.type==='rtk'&&n.done===false){
if(n.deps.length)n.deps.forEach(function(d){(it.rtkNotes[d]=it.rtkNotes[d]||[]).push(n);});else it.genRtks.push(n);}});
it.todos={};it.dnotes={};open.forEach(function(n){if(n.type==='todo'&&n.done===false)n.deps.forEach(function(d){it.todos[d]=(it.todos[d]||0)+1;});
// An open note on a department (a remark, the prod's "n:" one): its grey ◆ too.
else if(n.type==='note'&&!n.approval)n.deps.forEach(function(d){it.dnotes[d]=(it.dnotes[d]||0)+1;});});
it.openNotes=open.filter(function(n){return !(n.type==='rtk'&&n.done===false)&&!n.approval;});});
// The sections present, then Breakdown: the progress by group and department.
tabs=TABS.filter(function(t){return D.some(function(it){return it.tab===t[0];});}).concat([['breakdown','Breakdown']]);
// Live: the farm too, as Farm monitoring shows it.
if(DATA.farm)tabs.push(['farm','Farm']);}
prepare();
function depsOf(tab){return META.departments[tab==='shot'?'shot':'asset'];}
function validNow(it,d){return it.ok[d]&&!it.ok[d].old;}

