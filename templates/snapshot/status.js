// The state engine's twin (lib/status.py): a department's score, a file's
// Done -- the same rules, so the page can work out the figures a review
// would give (page.js "with your review"). The cases both run:
// tests/status_cases.json (tests/test_status.py).
var MPStatus=(function(){
'use strict';
// One department's share done, 0..1: validated 1 (its "rtk" weight with an
// open RTK), not started 0, else its state's weight.
function departmentScore(state,openRtk,w){if(state==='done')return openRtk?w.rtk/100:1;return (w[state]||0)/100;}
// A file's Done: its departments' mean, a general retake counting as an
// RTK on one of them -- a done one with none of its own. null without any.
function fileProgress(item,w){var ds=Object.keys(item.departments||{});if(!ds.length)return null;
var rtk=item.rtk_departments||[],total=0;
ds.forEach(function(d){total+=departmentScore(item.departments[d],rtk.indexOf(d)>=0,w);});
if(item.general_rtk&&ds.some(function(d){return item.departments[d]==='done'&&rtk.indexOf(d)<0;}))total-=1-w.rtk/100;
return total/ds.length;}
// Each item the same weight, those without a value left out.
function average(values){var v=values.filter(function(x){return x!=null;});return v.length?v.reduce(function(s,x){return s+x;},0)/v.length:null;}
return {departmentScore:departmentScore,fileProgress:fileProgress,average:average};})();
