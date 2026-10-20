/* Screen of a pack (pack UI contract 1). The shell gives you: shell.$ shell.esc shell.api shell.poll shell.call(name,...) shell.card
   shell.openModal shell.closeModal shell.fmtDate shell.dueHtml shell.rerender. Element ids must be unique across the app: use a prefix. */
CEU.register("example",function(shell){
var $=shell.$,esc=shell.esc,S=null,result="";
function send(){return shell.api().set_job($("xso").value,$("xserial").value,result).then(shell.poll)}
["xso","xserial"].forEach(function(id){$(id).addEventListener("input",function(){this.value=this.value.toUpperCase().replace(/\s+/g,"");send()})});
Array.prototype.forEach.call($("xrt").children,function(b){b.onclick=async function(){result=b.dataset.v;await send();if(S&&S.job.ok)$("scan").focus()}});
return {
 render:function(s){S=s;var j=s.job;result=j.result;
  if(document.activeElement!==$("xso"))$("xso").value=j.so;
  if(document.activeElement!==$("xserial"))$("xserial").value=j.serial;
  $("xsoh").textContent=j.so&&j.errors.so?j.errors.so:"";$("xserh").textContent=j.serial&&j.errors.serial?j.errors.serial:"";
  Array.prototype.forEach.call($("xrt").children,function(b){b.classList.toggle("on",b.dataset.v===j.result)})},
 started:function(s){return s.scanned>0},
 progress:function(s){return {done:s.scanned,total:s.need_scan,word:"verified"}},
 hasWork:function(s){return !!(s.scanned>0||s.job.so||s.job.serial)},
 notReady:function(){return "Fill in the Service Order, Serial # and Result Type first"},
 pcard:function(s,d){return {label:"Product - Example",detail:d}},
 summary:function(){return ""},
 kpis:function(s){var k=s.kpi;return {n:4,html:
  shell.card("Ready",k.ready+"/"+k.total,k.ready>=k.total?"ok":"bad","valid ETEs",k.ready,"/"+k.total)+
  shell.card("Expiring soon",k.expiring,k.expiring?"warn":"","due within 30 days",k.expiring)+
  shell.card("Expired",k.expired,k.expired?"bad":"","past cal due date",k.expired)+
  shell.card("Sent for cal",k.sent,k.sent?"bad":"","whereabout RCV",k.sent)}}
 /* setup:function(){...}  optional: opens this product's Setup page (the Setup button calls it) */
};
});
