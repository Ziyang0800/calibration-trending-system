/* 3458A OGC screen (pack UI contract 1). Station B-1 / B-2, job card, Setup editor. */
CEU.register("ogc",function(shell){
var $=shell.$,esc=shell.esc,api=shell.api,poll=shell.poll,openModal=shell.openModal,closeModal=shell.closeModal,dueHtml=shell.dueHtml,card=shell.card;
var S=null,jobResult="",wired=false,segBuilt=false;
function sendJob(){return api().set_job($("so").value,$("serial").value,jobResult).then(poll)}
function wire(){
 if(wired)return;wired=true;
 ["so","serial"].forEach(function(id){$(id).addEventListener("input",function(){this.value=this.value.toUpperCase().replace(/\s+/g,"");sendJob()})});
 $("so").addEventListener("keydown",function(e){if(e.key==="Enter")$("serial").focus()});
 $("serial").addEventListener("keydown",function(e){if(e.key==="Enter")(S.job.ok?$("scan"):$("rt").children[0]).focus()});
 Array.prototype.forEach.call($("rt").children,function(b){b.onclick=async function(){jobResult=b.dataset.v;await sendJob();if(S.job.ok)$("scan").focus()}});
}
function header(s,el){
 if(!el.firstChild){el.innerHTML='<div class="seg" id="seg"><button data-st="B-1">Station B-1</button><button data-st="B-2">Station B-2</button></div>';
  Array.prototype.forEach.call(el.querySelectorAll("button"),function(b){b.onclick=function(){switchTo(b.dataset.st)}})}
 Array.prototype.forEach.call(el.querySelectorAll("button"),function(b){b.classList.toggle("on",b.dataset.st===s.station)});
}
async function switchTo(st){
 if(shell.busy())return;
 if(st==="B-1"){if(S.station!=="B-1"){await shell.call("go_b1");await poll()}return}
 if(await shell.call("need_warning"))await showWarning();
 await showPicker();
}
function showWarning(){return new Promise(function(res){
 var d=openModal('<h2 class="warnh">STATION B-2 - PARAMETRIC TESTING ONLY</h2><div class="b"><div>Station B-2 should only be used when the DUT requires <b>PARAMETRIC testing</b> involving <b>TWO sets</b> of Fluke Calibrator &amp; Amplifier.</div><div>For all other testing, please use <b>Station B-1</b> at all times.</div><label style="display:flex;gap:10px;align-items:center;cursor:pointer"><input type="checkbox" id="ack" style="width:18px;height:18px;accent-color:#e90029"> I acknowledge, do not show again until next launch</label></div><div class="f"><button class="primary" id="go" disabled>Continue</button></div>');
 var ack=d.querySelector("#ack"),go=d.querySelector("#go");
 ack.onchange=function(){go.disabled=!ack.checked};
 go.onclick=async function(){await shell.call("ack_b2");res()};
})}
async function showPicker(){
 var sets=await shell.call("sets"),pick=null;
 var any=sets.some(function(s){return s.available});
 var html='<h2 style="background:var(--b2)">Station B-2: choose the Calibrator &amp; Amplifier Set</h2><div class="b">';
 sets.forEach(function(s){
  html+='<div class="set'+(s.available?"":" off")+'" data-n="'+s.num+'"><div style="flex:1"><b>Set '+s.num+'</b><small>'+esc(s.calibrator.equipment_id)+" "+esc(s.calibrator.model)+" + "+esc(s.amplifier.equipment_id)+" "+esc(s.amplifier.model)+'</small>'+(s.available?"":'<div class="why">'+esc(s.reason)+"</div>")+(s.last_used&&s.available?'<div class="muted" style="font-size:12px">Last used</div>':"")+'</div></div>';
 });
 if(!any)html+='<div class="err">No Set is available right now.</div>';
 html+='</div><div class="f">'+(any?'':'<button class="ghost" id="stay">Stay on Station B-1</button>')+'<button class="primary" id="ok" disabled>OK</button></div>';
 var d=openModal(html),ok=d.querySelector("#ok");
 var cards=d.querySelectorAll(".set");
 function select(n){pick=n;Array.prototype.forEach.call(cards,function(c){c.classList.toggle("sel",+c.dataset.n===n)});ok.disabled=false}
 Array.prototype.forEach.call(cards,function(c){if(!c.classList.contains("off"))c.onclick=function(){select(+c.dataset.n)}});
 var last=sets.filter(function(s){return s.last_used&&s.available})[0];if(last)select(last.num);
 if(d.querySelector("#stay"))d.querySelector("#stay").onclick=function(){closeModal()};
 ok.onclick=async function(){
  try{await shell.call("choose_set",pick);closeModal();await poll()}
  catch(e){d.querySelector(".b").insertAdjacentHTML("beforeend",'<div class="err">'+esc(e.message||e)+"</div>")}
 };
}


async function showSetupOgc(){
 var cfg=await api().get_setup(),master=cfg.master,rules=cfg.rules,glab=cfg.group_labels,mm={};
 var nk=function(s){return String(s||"").toUpperCase().replace(/[^A-Z0-9&.\-]/g,"")};
 master.forEach(function(m){mm[m.equipment_id]=m});
 /* one flat list of fixed slots: B-1 slots, then the Calibrator and Amplifier of each B-2 Set */
 var items=[];
 cfg.b1.forEach(function(x,i){var r=rules[i]||{models:[],group:null};
  items.push({sec:"Station B-1",label:x.slot,no:i+1,models:r.models,group:r.group,gkey:r.group,id:x.equipment_id})});
 function allowed(it){var all=[];master.forEach(function(m){if(m.model&&all.indexOf(m.model)<0)all.push(m.model)});
  if(!it.models.length)return all.sort();
  return it.models.filter(function(x){return all.some(function(y){return nk(y)===nk(x)})}).map(function(x){return all.filter(function(y){return nk(y)===nk(x)})[0]})}
 function modelOf(it){var m=mm[it.id];return m&&m.model?m.model:""}
 items.forEach(function(it){it.opts=allowed(it);it.model=modelOf(it);if(!it.model)it.model=it.opts[0]||""});
 function idsFor(it){return master.filter(function(m){return it.model?nk(m.model)===nk(it.model):true})}
 function members(it){return items.filter(function(o){return o.gkey&&o.gkey===it.gkey})}
 function setOf(list){var s={};list.forEach(function(o){var m=mm[o.id];if(m&&m.set)s[m.set]=1});return Object.keys(s)}
 var pending=null,blocked=null;

 var d=openModal('<h2 class="n">Setup</h2><div class="b" id="sb"></div><div class="f"><span class="err" id="se" style="margin-right:auto;text-align:left"></span><button class="ghost" id="sx">Cancel</button><button class="primary" id="ss">Save</button></div>',true);
 var sb=d.querySelector("#sb");
 function opt(v,t,sel,dis){return '<option value="'+esc(v)+'"'+(sel?" selected":"")+(dis?" disabled":"")+'>'+esc(t)+'</option>'}
 function row(it,k){
  var mo=it.model?"":'<option value="" hidden selected></option>',io=it.id?"":'<option value="" hidden selected></option>';
  it.opts.forEach(function(x){mo+=opt(x,x,x===it.model)});
  idsFor(it).forEach(function(m){io+=opt(m.equipment_id,m.equipment_id+(m.serial?"  ("+m.serial+")":"")+(m.set?"  Set "+m.set:""),m.equipment_id===it.id)});
  var m=mm[it.id],dsc=m?esc(m.description||m.model||"")+(m.serial?' <span class="muted">&middot; S/N '+esc(m.serial)+'</span>':"")+dueHtml(m)+(m.status&&m.status!=="Valid"&&m.status!=="Expiring Soon"?' <span class="chip bad">'+esc(m.status)+'</span>':""):'<span class="muted">Choose an ETE</span>';
  var dis=pending||blocked?" disabled":"";
  return '<div class="srow"><span class="slot">'+esc(it.label)+'</span><select data-k="m" data-n="'+k+'"'+dis+' aria-label="Model number">'+mo+'</select><select data-k="i" data-n="'+k+'"'+dis+' aria-label="Equipment ID">'+io+'</select><span class="mdesc">'+dsc+'</span></div>';
 }
 function draw(){
  var h="",lastSec="",lastG="";
  if(blocked)h+='<div class="gwarn bad"><b>Cannot change this group</b><div style="margin-top:6px">'+blocked.msg+'</div><div class="btns"><button class="ghost" data-a="ok">OK</button></div></div>';
  if(pending){
   var all=[{it:pending.it,from:pending.from,to:pending.to,me:true}].concat(pending.changes.map(function(c){return {it:c.it,from:c.it.id,to:c.to}}));
   var li=all.map(function(c){return '<li>'+esc(c.it.label)+': '+esc(c.from||"-")+' &rarr; <b>'+esc(c.to)+'</b>'+(c.me?' <span class="muted">(your change)</span>':'')+'</li>'}).join("");
   h+='<div class="gwarn"><b>Switch all '+esc(glab[pending.it.group]||"group ETEs")+' to Set '+esc(pending.set)+'?</b><div style="margin-top:6px">These ETEs are calibrated together, so they must be used as a whole. Changing <b>'+esc(pending.it.label)+'</b> to <b>'+esc(pending.to)+'</b> (Set '+esc(pending.set)+') also changes '+pending.changes.length+' other ETE'+(pending.changes.length>1?"s":"")+'. All changes:</div><ul>'+li+'</ul><div class="btns"><button class="ghost" data-a="no">Keep current</button><button class="primary" data-a="yes">Switch whole group</button></div></div>';
  }
  items.forEach(function(it,k){
   if(it.sec!==lastSec){h+='<div class="sec" style="margin-top:6px">'+it.sec+' - choose the Model Number, then the Equipment ID</div>';lastSec=it.sec;lastG=""}
   var gk=it.gkey||("solo"+k);
   if(it.gkey&&gk!==lastG){var ms=members(it),ss=setOf(ms);
    h+='<div class="shead">'+esc(it.setNo?"Set "+it.setNo:(glab[it.group]||""))+(ss.length===1?'<i>Set '+esc(ss[0])+'</i>':ss.length>1?'<i class="bad">Mixed sets '+esc(ss.join(", "))+'</i>':'')+'</div>'}
   lastG=gk;
   h+=row(it,k);
  });
  h+='<div class="sec" style="margin-top:20px">Station B-2 - Calibrator &amp; Amplifier Sets (display only)</div>';
  cfg.sets.forEach(function(s){
   function one(id){var m=mm[id];return '<span><b class="id">'+esc(id)+'</b> <span class="muted">'+esc(m?m.model:"")+(m&&m.serial?" &middot; S/N "+esc(m.serial):"")+'</span></span>'}
   h+='<div class="setview"><b>Set '+s.num+'</b>'+one(s.calibrator)+one(s.amplifier)+'</div>';
  });
  sb.innerHTML=h;
  d.querySelector("#ss").disabled=!!(pending||blocked);
 }
 draw();
 function plan(it,newId){
  var st=(mm[newId]||{}).set;
  if(!it.group||!st)return {changes:[],set:st||""};
  var changes=[],missing=[];
  members(it).forEach(function(o){
   if(o===it)return;
   var want=o.models.map(nk);
   var c=master.filter(function(m){return m.set===st&&(want.length?want.indexOf(nk(m.model))>=0:true)});
   if(!c.length){missing.push(o.label);return}
   var pick=c.filter(function(m){return nk(m.model)===nk(o.model)})[0]||c[0];
   if(pick.equipment_id!==o.id)changes.push({it:o,to:pick.equipment_id,model:pick.model});
  });
  return {changes:changes,missing:missing,set:st};
 }
 function pickId(it,newId){
  var p=plan(it,newId);
  if(p.missing&&p.missing.length){blocked={msg:'Set '+esc(p.set)+' is incomplete: the masterlist has no '+p.missing.map(esc).join(", ")+' in it. Choose an ETE from a complete Set.'};draw();return}
  it.id=newId;if(newId)it.model=modelOf(it)||it.model;
  if(p.changes.length){it.id=pending_prev;pending={it:it,from:pending_prev,to:newId,set:p.set,changes:p.changes};}
  draw();
 }
 var pending_prev="";
 sb.onchange=function(e){
  var t=e.target,k=+t.dataset.n,it=items[k];if(t.dataset.k==null)return;
  if(t.dataset.k==="m"){
   it.model=t.value;var c=idsFor(it);
   if(it.id&&(mm[it.id]||{}).model&&nk(mm[it.id].model)!==nk(it.model)){pending_prev=it.id;it.id=""}
   if(c.length===1&&it.model){pending_prev=it.id;pickId(it,c[0].equipment_id)}else draw();
   return;
  }
  pending_prev=it.id;pickId(it,t.value);
 };
 sb.onclick=function(e){
  var b=e.target.closest("button");if(!b)return;
  if(b.dataset.a==="ok"){blocked=null;draw()}
  if(b.dataset.a==="no"){pending=null;draw()}
  if(b.dataset.a==="yes"){
   pending.it.id=pending.to;pending.it.model=modelOf(pending.it)||pending.it.model;
   pending.changes.forEach(function(c){c.it.id=c.to;c.it.model=c.model||c.it.model});
   pending=null;draw();
  }
 };
 d.querySelector("#sx").onclick=closeModal;
 d.querySelector("#ss").onclick=async function(){
  var b1=items.map(function(it){return {slot:it.label,equipment_id:it.id}});
  var r=await api().save_setup({b1:b1});
  if(!r.ok){d.querySelector("#se").textContent=r.errors.join("  |  ");return}
  closeModal();
  $("msg").className="verified";
  $("msg").textContent="Setup saved. Fetching the latest data from MARS...";
  poll();
 };
}
return {
 init:function(){wire()},
 header:header,
 render:function(s){S=s;jobResult=s.job.result;var j=s.job;
  if(document.activeElement!==$("so"))$("so").value=j.so;
  if(document.activeElement!==$("serial"))$("serial").value=j.serial;
  $("so").classList.toggle("bad",!!j.so&&!!j.errors.so);$("serial").classList.toggle("bad",!!j.serial&&!!j.errors.serial);
  $("soh").textContent=j.so&&j.errors.so?j.errors.so:"";$("serh").textContent=j.serial&&j.errors.serial?j.errors.serial:"";
  Array.prototype.forEach.call($("rt").children,function(b){b.classList.toggle("on",b.dataset.v===j.result)})},
 started:function(s){return s.verified>0},
 progress:function(s){return {done:s.verified,total:s.total,word:"verified"}},
 hasWork:function(s){return !!(s.verified>0||s.job.so||s.job.serial)},
 notReady:function(){return "Fill in the Service Order, Serial # and Result Type first"},
 pcard:function(s,d){return {label:"Product - Station "+s.station+(s.b2_set?" (Set "+s.b2_set+")":""),detail:d}},
 summary:function(){return ""},
 sessionLabel:function(s){return "Station "+s.station+(s.b2_set?", Set "+s.b2_set:"")},
 focusJob:function(){$("so").focus()},
 kpis:function(s){var k=s.kpi,b1c=k.b1_ready>=k.b1_total?"ok":(k.b1_ready>=10?"warn":"bad");return {n:s.b2_set?5:4,html:
  card("B-1 ready",k.b1_ready+"/"+k.b1_total,b1c,k.b1_ready>=k.b1_total?"Station ready":"Station not ready",k.b1_ready,"/"+k.b1_total)+
  (s.b2_set?card("B-2 Cal/Amp",k.b2_ready==null?"-":k.b2_ready+"/2",k.b2_ready==null?"":(k.b2_ready>=2?"ok":"bad"),"Set "+s.b2_set):"")+
  card("Expiring soon",k.expiring,k.expiring?"warn":"","due within 30 days",k.expiring)+
  card("Expired",k.expired,k.expired?"bad":"","past cal due date",k.expired)+
  card("Sent for cal",k.sent,k.sent?"bad":"","whereabout RCV",k.sent)}},
 setup:function(){return showSetupOgc()}
};
});
