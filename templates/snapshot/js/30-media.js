/* ---------- pictures and videos ---------- */
var hov=$('hover'),fine=matchMedia('(hover:hover) and (pointer:fine)');
// With a mouse only: a tap is not a hover, the picture would stay open.
document.addEventListener('mouseover',function(e){var t=e.target.closest('.row .thumb[data-zoom]');if(!t||!fine.matches)return;
hov.onload=function(){var r=t.getBoundingClientRect(),w=hov.offsetWidth,h=hov.offsetHeight;
hov.style.left=Math.max(8,Math.min(r.left,innerWidth-w-8))+'px';hov.style.top=(r.bottom+8+h<innerHeight?r.bottom+8:Math.max(8,r.top-8-h))+'px';};
hov.src=img(D[t.dataset.zoom].thumb);hov.style.display='block';});
document.addEventListener('mouseout',function(e){if(e.target.closest('.thumb'))hov.style.display='none';});
// The page under it holds still, and is back where it was once closed:
// on an iPad, starting a video scrolled it to the top.
function lightbox(html,cap){lockPage('lb',true);
$('lb-in').innerHTML=html;$('lb-cap').innerHTML=cap||'';$('lb').hidden=false;hov.style.display='none';}
function closeLb(){var v=$('lb-in').querySelector('video');if(v)v.pause();$('lb').hidden=true;$('lb-in').innerHTML='';
lockPage('lb',false);}
$('lb').addEventListener('click',function(e){if(e.target===this||e.target.closest('#lb-x')||e.target.tagName==='IMG')closeLb();});
document.addEventListener('click',function(e){var t=e.target.closest('[data-zoom]');if(!t)return;e.stopPropagation();var it=D[t.dataset.zoom];
lightbox('<img alt="" src="'+img(it.thumb)+'">',esc(it.name));},true);
// A render's video in the zip made with the snapshot (same name), unzipped
// beside this page: <zip>/sq060/sq060_sh070_v012-stable_001.mp4,
// <zip>/assets/env/env_sol-lac_v002-stable_001.mp4 (lib/preview.py).
// A render's videos, as zipped with the snapshot (its name) and unzipped
// beside this page (lib/preview.py zip_latest_videos()): one per shot
// for shots rendered apart -- <zip>/sq060/sq060_sh070_v012-stable_001.mp4
// --, one for a block rendered whole or anything else --
// <zip>/sq060/sq060_sh070-090-100_..., <zip>/assets/env/env_sol-lac_....
// The videos the page can play, by their paths under renders/ (each
// render line's video, lib/snapshot.py snapshot_videos()): in the
// snapshot's videos folder or zip, or in a folder chosen here -- the
// project's renders/ too.
var VNAMES={},PICKED=null;((META.videos||{}).files||[]).forEach(function(n){VNAMES[n]=1;});
function videoSrc(name){var f=null,parts=name.split('/');
// The longest tail found: a folder above, or below, renders/ alike. Its
// file name alone only from a phone's pick (the same in every version).
if(PICKED)for(var k=0;k<parts.length&&!f;k++)if(k<parts.length-1||PICKED[' flat'])f=PICKED[parts.slice(k).join('/')];
if(f)return {src:f.url||(f.url=URL.createObjectURL(f)),from:'picked'};
// Then the copy that came with the page (videos/, or the zip unzipped),
// then the render itself, in the project, relative to the page.
var V=META.videos||{},path=encodeURI(name);
if(VNAMES[name])return {src:V.base+'/'+path,from:V.mode};
return V.local?{src:V.local+'/'+path,from:'local'}:null;}
// A render line's video, one or none.
// Live: another version picked to watch (PICKV, by file and line).
var PICKV={};
function videosOf(it,r){var o=(PICKV[it.file]||{})[r.shots||''];if(o)r=Object.assign({},r,{video:o.video,folder:o.folder,first:o.first});var s=r.video&&videoSrc(r.video);
return s?[{file:it.name,shot:r.shots,shots:r.shot_list,first:r.shot_list[0],start:r.first,folder:r.folder,src:s.src,from:s.from,name:r.video}]:[];}
// Choose the videos' folder: each video known by its path's every tail, so
// the folder's own name, or one above it, doesn't matter. A phone with no
// folder picker gives the videos themselves, known by their names.
function pickVideos(files){var n=0;PICKED={};
[].forEach.call(files,function(f){if(!/\.mp4$/i.test(f.name))return;n++;
var parts=(f.webkitRelativePath||f.name).split('/');
if(parts.length<2)PICKED[' flat']=1;
for(var k=0;k<parts.length;k++){var key=parts.slice(k).join('/');if(!PICKED[key])PICKED[key]=f;}});
if(!n){PICKED=null;toast('No .mp4 in that folder.');return;}
var found=D.reduce(function(c,it){return c+allVideos(it).filter(function(v){return v.src.slice(0,5)==='blob:';}).length;},0);
toast(plural(n,'video')+' in that folder, '+found+' for this snapshot.');
if(cur!=null)refresh();else render();}
// Chrome, Edge: the folder opened, not read -- only the videos this page
// needs are looked for, by their paths, so even the project's renders/
// (hundreds of thousands of frames) is quick. Each path tried as is,
// under renders/, then without its first folders (a folder inside).
function pickFolder(){window.showDirectoryPicker({id:'mp-videos'}).then(function(dir){
var names={};D.forEach(function(it){it.renders.forEach(function(r){if(r.video)names[r.video]=1;});});
names=Object.keys(names);var found={},n=0,next=0,left=names.length;
if(!left){toast('No render of this snapshot has a video.');return;}
toast('Looking for '+plural(left,'video')+'…');
function open(parts){var h=Promise.resolve(dir);parts.slice(0,-1).forEach(function(p){h=h.then(function(d){return d.getDirectoryHandle(p);});});
return h.then(function(d){return d.getFileHandle(parts[parts.length-1]);}).then(function(f){return f.getFile();});}
function look(name){var parts=name.split('/'),tries=[parts,['renders'].concat(parts)];
for(var k=1;k<parts.length-1;k++)tries.push(parts.slice(k));
var at=0;function one(){if(at>=tries.length)return null;return open(tries[at++]).catch(one);}return Promise.resolve().then(one);}
function work(){if(next>=names.length)return Promise.resolve();var name=names[next++];
return look(name).then(function(f){if(f){found[name]=f;n++;}}).then(work);}
var pool=[];for(var w=0;w<8;w++)pool.push(work());
Promise.all(pool).then(function(){if(!n){toast('None of this snapshot\'s videos in '+dir.name+'.');return;}
PICKED=found;toast(n+' of '+plural(names.length,'video')+' found in '+dir.name+'.');if(cur!=null)refresh();else render();});
}).catch(function(e){if(e&&e.name!=='AbortError')toast('That folder could not be read.');});}
// The pickers are file inputs, for the browsers without it.
document.addEventListener('click',function(e){var l=e.target.closest('label');
if(!l||!window.showDirectoryPicker||!l.querySelector('.vid-pick'))return;e.preventDefault();e.stopPropagation();closeMenus();pickFolder();},true);
function pickLink(text){return '<label class="vpick">'+esc(text)+'<input type="file" class="vid-pick" webkitdirectory multiple accept="video/mp4,.mp4"></label>';}
document.addEventListener('change',function(e){var t=e.target;if(!t.classList||!t.classList.contains('vid-pick'))return;
var files=t.files;closeMenus();if(files&&files.length)pickVideos(files);t.value='';});
// Every video of the file, in its shots' order.
function allVideos(it){var out=[];it.renders.forEach(function(r){out=out.concat(videosOf(it,r));});
var rank=function(v){var k=it.shots.indexOf(v.first);return k<0?0:k;};return out.sort(function(a,b){return rank(a)-rank(b);});}
