// The page's words in the reader's language: T('Validate all done'), the
// English sentence its own key (the reference), a dictionary a language
// (MPI18n.add('fr', {...})). A key a dictionary lacks: the English. With
// values: T('{n} files', {n: 3}); a plural, the key's "|" forms --
// T('{n} file|{n} files', {n}). The language: the page's (meta.lang, the
// export writes Blender's), else the browser's, else English; a choice
// kept in this browser (mp-snapshot:lang) before them all. Never
// translated: files, departments, roles, prefixes, people -- the project's.
var MPI18n=(function(){
'use strict';
var DICTS={en:{}},lang='en',KEY='mp-snapshot:lang';
function base(l){return String(l||'').toLowerCase().split(/[-_]/)[0];}
// The address's ?lang= first: a browser storing nothing for a file opened from disk still keeps it over the reload.
function pick(meta){var want=[];try{want.push(new URLSearchParams(location.search).get('lang'));}catch(e){}try{want.push(localStorage.getItem(KEY));}catch(e){}
want.push(meta&&meta.lang);(navigator.languages||[navigator.language]).forEach(function(l){want.push(l);});
for(var i=0;i<want.length;i++){var b=base(want[i]);if(b&&DICTS[b])return b;}return 'en';}
function add(l,dict){l=base(l);DICTS[l]=DICTS[l]||{};Object.keys(dict).forEach(function(k){DICTS[l][k]=dict[k];});}
function use(l){lang=DICTS[base(l)]?base(l):'en';return lang;}
function choose(l){try{if(l)localStorage.setItem(KEY,base(l));else localStorage.removeItem(KEY);}catch(e){}return use(l||pick(null));}
// The singular: as the language counts (French: 0 and 1, English: 1).
function one(n){try{return new Intl.PluralRules(lang).select(n)==='one';}catch(e){return n===1;}}
function T(key,vars){var s=(DICTS[lang]||{})[key];if(s==null)s=key;
var forms=s.split('|');if(forms.length>1)s=forms[one(vars&&vars.n)?0:1];
return vars?s.replace(/\{(\w+)\}/g,function(m,k){return k in vars?String(vars[k]):m;}):s;}
return {T:T,add:add,use:use,choose:choose,pick:pick,get lang(){return lang;},langs:function(){return Object.keys(DICTS);}};})();
var T=MPI18n.T;
