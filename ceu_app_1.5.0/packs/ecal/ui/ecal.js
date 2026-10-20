/* ECal screen (pack UI contract 1). Registered with the shell, which calls the hooks at the bottom. */
CEU.register("ecal",function(shell){
var $=shell.$,esc=shell.esc,api=shell.api,poll=shell.poll,openModal=shell.openModal,closeModal=shell.closeModal,dueHtml=shell.dueHtml,card=shell.card;
var S=null,jobResult="",CAT=null,dlKey="",ecInit=false;
async function loadCat(){CAT=await shell.call("catalog")}
function ecModel(id){return CAT&&CAT.models.filter(function(m){return m.id===id})[0]}
function sendSel(){return sendSelWith(S.sel.conn||[],S.torque)}
function sendSelWith(conn,torque){return shell.call("select",$("emodel").value.trim(),$("emod").value.trim(),conn,torque).then(poll)}
function sendJobE(){return api().set_job($("eso").value,$("eserial").value,jobResult).then(poll)}
function renderJobE(){
 var j=S.job,sel=S.sel,er=j.errors;
 if(!CAT){loadCat().then(function(){shell.rerender()});return}
 if(!ecInit){ecInit=true;wireE()}
 var dm=$("dlModels"),k1=CAT.models.length;if(dm.dataset.k!=k1){dm.dataset.k=k1;dm.innerHTML=CAT.models.map(function(m){return'<option value="'+esc(m.id)+'">'+esc(m.desc)+'</option>'}).join("")}
 var key=sel.model_ok?sel.model:"*";
 if(dlKey!==key){dlKey=key;var mods=[];
  CAT.models.forEach(function(m){if(key!=="*"&&m.id!==key)return;m.modules.forEach(function(x){if(!mods.some(function(y){return y.id===x.id}))mods.push(x)})});
  $("dlMods").innerHTML=mods.map(function(x){return'<option value="'+esc(x.id)+'">'+esc(x.text)+'</option>'}).join("")}
 if(document.activeElement!==$("emodel"))$("emodel").value=sel.model;
 if(document.activeElement!==$("emod"))$("emod").value=sel.module;
 if(document.activeElement!==$("eso"))$("eso").value=j.so;
 if(document.activeElement!==$("eserial"))$("eserial").value=j.serial;
 $("emodel").classList.toggle("bad",!!sel.model&&!sel.model_ok);$("emod").classList.toggle("bad",!!sel.module&&!sel.module_ok);
 $("emh").textContent=sel.model&&!sel.model_ok?"Unknown Model ID":(sel.model_ok?((ecModel(sel.model)||{}).desc||""):"");
 $("emodel").readOnly=!!sel.model_locked;$("emodel").style.opacity=sel.model_locked?.8:"";
 var ow=$("eown"),oh=(sel.module_ok&&!sel.model_ok&&sel.owners&&sel.owners.length>1)?'<span class="jh" style="margin:0 4px 0 0">This module is used by:</span>'+sel.owners.map(function(x){return'<button type="button" class="cchip" data-o="'+esc(x)+'">'+esc(x)+'</button>'}).join(""):"";
 if(ow.dataset.k!==oh){ow.dataset.k=oh;ow.innerHTML=oh;Array.prototype.forEach.call(ow.querySelectorAll(".cchip"),function(b){b.onclick=function(){$("emodel").value=b.dataset.o;sendSel()}})}
 $("emoh").textContent=sel.module&&!sel.module_ok?(sel.model_ok?"Not a module of "+sel.model:"Unknown module ID"):"";
 $("eserl").textContent="Unit "+(sel.model_ok?sel.model+" ":"")+"Serial # *";
 $("eso").classList.toggle("bad",!!j.so&&!!er.so);$("eserial").classList.toggle("bad",!!j.serial&&!!er.serial);
 $("esoh").textContent=j.so&&er.so?er.so:"";$("eserh").textContent=j.serial&&er.serial?er.serial:"";
 Array.prototype.forEach.call($("ert").children,function(b){b.classList.toggle("on",b.dataset.v===j.result)});
 /* connector area */
 var c=$("econn"),h="";
 if(!sel.module_ok){$("econnl").textContent="Connector type(s)";h='<div class="cinfo">Choose the Model ID and Module ID first (the cal kits follow from them).</div>'}
 else if(sel.type==="Fixed"){$("econnl").textContent="Connector type (fixed)";h='<div class="cinfo">'+esc(sel.text)+'</div>'}
 else{$("econnl").textContent="Connector types installed on this DUT (up to "+sel.max+")";
  h='<div class="cchips">'+sel.allowed.map(function(x){var on=sel.conn.indexOf(x)>=0;return'<button type="button" class="cchip'+(on?" on":"")+'" data-c="'+esc(x)+'"'+(!on&&sel.conn.length>=sel.max?" disabled":"")+'>'+esc(x)+(CAT.connectors[x]?' <span style="opacity:.7;font-weight:500">'+esc(CAT.connectors[x])+'</span>':"")+'</button>'}).join("")+'</div><div class="jh">'+(er.conn?esc(er.conn):"")+'</div>'}
 if(c.dataset.k!==h){c.dataset.k=h;c.innerHTML=h;Array.prototype.forEach.call(c.querySelectorAll(".cchip"),function(b){b.onclick=function(){
   var cur=(S.sel.conn||[]).slice(),i=cur.indexOf(b.dataset.c);if(i>=0)cur.splice(i,1);else if(cur.length<S.sel.max)cur.push(b.dataset.c);sendSelWith(cur,S.torque)}})}
 /* torque: Yes/No here, the tester itself is chosen in Setup */
 var t=$("etq"),th='<button type="button" class="cchip'+(S.torque?"":" on")+'" data-t="no">No</button><button type="button" class="cchip'+(S.torque?" on":"")+'" data-t="yes">Yes</button>';
 if(t.dataset.k!==th){t.dataset.k=th;t.innerHTML=th;Array.prototype.forEach.call(t.querySelectorAll(".cchip"),function(b){b.onclick=function(){sendSelWith(S.sel.conn||[],b.dataset.t==="yes")}})}
 var ta=S.torque_active||{};
 $("etqh").textContent=S.torque?(er.tt?er.tt:"Active tester: "+(ta.model?ta.model+" ":"")+ta.id+" (change in Setup). Listed on the report, not scanned."):"";
}
function wireE(){
 ["emodel","emod"].forEach(function(id){$(id).addEventListener("input",function(){this.value=this.value.toUpperCase().replace(/\s+/g,"");sendSel()});$(id).addEventListener("change",function(){sendSel()})});
 ["eso","eserial"].forEach(function(id){$(id).addEventListener("input",function(){this.value=this.value.toUpperCase().replace(/\s+/g,"");sendJobE()})});
 $("emodel").addEventListener("keydown",function(e){if(e.key==="Enter")$("emod").focus()});
 $("emod").addEventListener("keydown",function(e){if(e.key==="Enter")$("eso").focus()});
 $("eso").addEventListener("keydown",function(e){if(e.key==="Enter")$("eserial").focus()});
 $("eserial").addEventListener("keydown",function(e){if(e.key==="Enter")(S.job.ok?$("scan"):$("ert").children[0]).focus()});
 Array.prototype.forEach.call($("ert").children,function(b){b.onclick=async function(){jobResult=b.dataset.v;await sendJobE();if(S.job.ok)$("scan").focus()}});
}

/* ---------------- ECal setup ---------------- */
async function showSetupEcal(){
 var cfg=await api().get_setup(),master=cfg.master,slots=cfg.slots,mm={},nk=function(s){return String(s||"").toUpperCase().replace(/[^A-Z0-9&.\-]/g,"")};
 master.forEach(function(m){mm[m.equipment_id]=m});
 var d=openModal('<h2 class="n">Setup - ECal</h2><div class="b" id="sb"></div><div class="f"><span class="err" id="se" style="margin-right:auto;text-align:left"></span><button class="ghost" id="sx">Cancel</button><button class="primary" id="ss">Save</button></div>',true);
 var sb=d.querySelector("#sb");
 slots.forEach(function(x){if(x.models.length>1){var m=mm[x.equipment_id],hit=m&&m.model?x.models.filter(function(y){return nk(y)===nk(m.model)})[0]:"";x.model=hit||x.models[0]}});
 function draw(){
  var h='<div class="muted">Each slot holds the <b>active</b> ETE of that model. A scan can only confirm the active ETE, so change it here when a different unit becomes the one in use.</div>',last="";
  slots.forEach(function(x,i){
   if(x.group!==last){h+='<div class="sec" style="margin-top:12px">'+esc(x.group)+(x.group==="Torque tester"?" - one at a time, listed on the report, never scanned":"")+'</div>';last=x.group}
   var opts=master.filter(function(m){return nk(m.model)===nk(x.model)}),o=x.equipment_id?"":'<option value="" hidden selected></option>';
   opts.forEach(function(m){o+='<option value="'+esc(m.equipment_id)+'"'+(m.equipment_id===x.equipment_id?" selected":"")+'>'+esc(m.equipment_id+(m.serial?"  ("+m.serial+")":""))+'</option>'});
   var m=mm[x.equipment_id],dsc=m?esc(m.description||m.model||"")+dueHtml(m)+(m.status&&m.status!=="Valid"&&m.status!=="Expiring Soon"?' <span class="chip bad">'+esc(m.status)+'</span>':""):'<span class="muted">Choose an ETE</span>';
   h+='<div class="srow"><span class="slot">'+esc(x.label)+'</span><select '+(x.models.length>1?'data-m="'+i+'"':"disabled")+' aria-label="Model number">'+x.models.map(function(y){return'<option'+(y===x.model?" selected":"")+'>'+esc(y)+'</option>'}).join("")+'</select><select data-i="'+i+'" aria-label="Equipment ID">'+o+'</select><span class="mdesc">'+dsc+'</span></div>'});
  sb.innerHTML=h;
 }
 draw();
 sb.onchange=function(e){var t=e.target;
  if(t.dataset.m!=null){var x=slots[+t.dataset.m];x.model=t.value;var c=master.filter(function(m){return nk(m.model)===nk(x.model)});
   if(!c.some(function(m){return m.equipment_id===x.equipment_id}))x.equipment_id=c.length===1?c[0].equipment_id:"";draw();return}
  if(t.dataset.i==null)return;slots[+t.dataset.i].equipment_id=t.value;draw()};
 d.querySelector("#sx").onclick=closeModal;
 d.querySelector("#ss").onclick=async function(){
  var a={};slots.forEach(function(x){a[x.key]=x.equipment_id});
  var r=await api().save_setup({active:a});
  if(!r.ok){d.querySelector("#se").textContent=r.errors.join("  |  ");return}
  closeModal();$("msg").className="verified";$("msg").textContent="Setup saved. Fetching the latest data from MARS...";poll();
 };
}

function ecModelDesc(id){var m=ecModel(id);return m?m.desc:""}
return {
 init:function(){},
 render:function(s){S=s;jobResult=s.job.result;renderJobE()},
 started:function(s){return s.scanned>0},
 progress:function(s){return {done:s.scanned,total:s.need_scan,word:"scanned"}},
 hasWork:function(s){return !!(s.scanned>0||s.job.so||s.job.serial)},
 notReady:function(){return "Complete the Model ID, Module ID and job fields above first"},
 pcard:function(s,d){if(s.sel.model_ok)d=ecModelDesc(s.sel.model)||d;if(s.sel.module_ok)d+=" | "+s.sel.module+" - "+s.sel.text;return {label:"Product - ECal",detail:d}},
 summary:function(S){return '<span class="k">Module</span><b>'+esc(S.sel.model)+' / '+esc(S.sel.module)+'</b>'+(S.sel.conn&&S.sel.conn.length?'<span class="k">Connectors</span><b>'+esc(S.sel.conn.join(", "))+'</b>':'')+'<span class="k">Torque</span><b>'+(S.torque?"Yes":"No")+'</b>'},
 kpis:function(s){var k=s.kpi;return {n:5,html:
  card("Required ETEs",k.req_ready+"/"+k.req_total,k.req_ready>=k.req_total?"ok":"bad",k.req_ready>=k.req_total?"All valid":"Some not valid",k.req_ready,"/"+k.req_total)+
  card("Active ETEs",k.act_ready+"/"+k.act_total,k.act_ready>=k.act_total?"ok":"warn","valid in Setup",k.act_ready,"/"+k.act_total)+
  card("Expiring soon",k.expiring,k.expiring?"warn":"","due within 30 days",k.expiring)+
  card("Expired",k.expired,k.expired?"bad":"","past cal due date",k.expired)+
  card("Sent for cal",k.sent,k.sent?"bad":"","whereabout RCV",k.sent)}},
 sessionLabel:function(s){return "ECal, "+s.sel.model+" "+s.sel.module},
 focusJob:function(){$("eso").focus()},
 setup:function(){return showSetupEcal()}
};
});
