const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor(tag) {this.tagName=tag;this.children=[];this.style={};this.listeners={};this.attributes={};this.clientWidth=900;this.clientHeight=400;this.classList={add(){},remove(){},toggle(){}};}
  appendChild(e) {this.children.push(e);e.parentElement=this;return e;}
  append(...es) {es.forEach(e=>this.appendChild(e));}
  replaceChildren(...es) {this.children=[];this.append(...es);}
  addEventListener(name,callback) {this.listeners[name]=callback;}
  setAttribute(name,value) {this.attributes[name]=value;}
  remove() {this.removed=true;}
}
function environment() {
  const elements={};
  const document={getElementById:id=>elements[id] ||= new Element('div'),createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag)};
  const window={addEventListener(){}};
  const context=vm.createContext({document,window,console,setTimeout(){},navigator:{},ResizeObserver:class {observe(){} disconnect(){}}});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8'),context);
  return {context,document,elements,window};
}
const flush = () => new Promise(resolve=>setImmediate(resolve));
function walk(element) {return [element,...element.children.flatMap(walk)];}

test('stored text is escaped for markup and toast uses textContent',()=>{
  const {context,document}=environment();
  assert.equal(vm.runInContext(`escapeHtml('</textarea><img src=x onerror="attack()">')`,context),'&lt;/textarea&gt;&lt;img src=x onerror=&quot;attack()&quot;&gt;');
  vm.runInContext(`app.showToast('<img src=x onerror=attack()>')`,context);
  const toast=document.getElementById('toastContainer').children[0];
  assert.equal(toast.textContent,'<img src=x onerror=attack()>');
  assert.equal(toast.innerHTML,undefined);
});

test('1 V does not inherit legacy 10 V uncertainty',()=>{
  const {context}=environment();
  assert.equal(vm.runInContext(`formatUncertainty({mu_relative:1e-6},'dcv_reference',1)`,context),'—');
  assert.equal(vm.runInContext(`formatUncertainty({uncertainty:24.4},'dcv_reference',1)`,context),'24.4 nV');
});

test('edit dialog handles point values and keeps failed saves open',async()=>{
  const {context,document,window}=environment();
  const payloads=[];
  window.pywebview={api:{get_calibration_for_edit:async()=>({id:7,cal_date:'2020-01-01',measured_value:1,mu_relative:2e-6,
    reviewer_comment:'</textarea><img src=x onerror=attack()>',location:'Lab A',pressure_hpa:1000,is_adjusted:false,excluded_from_regression:false,
    test_point_readings:[{tp_id:8,point_name:'1 V <test>',unit:'V',measured_value:1,uncertainty:24.4,excluded_from_regression:false}]}),
    save_calibration_edit:async payload=>{payloads.push(payload);return {ok:false,error:'Date already exists'};}}};
  vm.runInContext('openEditCalModal(7)',context);
  await flush();
  const card=document.getElementById('genericModalCard');
  const nodes=walk(card),form=nodes.find(n=>n.tagName==='form');
  assert.equal(nodes.find(n=>n.tagName==='textarea').value,'</textarea><img src=x onerror=attack()>');
  assert.equal(card.innerHTML,undefined);
  assert.ok(nodes.some(n=>n.tagName==='legend'&&n.textContent==='1 V <test>'));
  let closed=false;
  context.closeGenericModal=()=>{closed=true;};
  await form.listeners.submit({preventDefault(){}});
  assert.equal(closed,false);
  assert.equal(payloads[0].test_point_readings[0].tp_id,8);
  assert.equal(payloads[0].test_point_readings[0].uncertainty,24.4);
  assert.equal(document.getElementById('toastContainer').children.at(-1).textContent,'Date already exists');
});

test('offline chart draws zero bounds, supports null gaps and releases observer',()=>{
  const {context,document}=environment();
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/trend-chart.js'),'utf8'),context);
  const parent=new Element('div'),canvas=new Element('canvas');parent.append(canvas);context.canvas=canvas;
  vm.runInContext(`var chart = new CalibrationChart(canvas, {data:{datasets:[{label:'limits',data:[{x:0,y:0},{x:1,y:null},{x:2,y:0}],showLine:true,pointRadius:0,borderColor:'#fff'}]},options:{scales:{x:{ticks:{color:'#fff'},grid:{color:'#333'},title:{text:'Days'}},y:{title:{text:'dB'}}},plugins:{tooltip:{callbacks:{label:()=>['safe']}}}}});`,context);
  const svg=parent.children.at(-1);
  assert.equal(svg.tagName,'svg');
  const curve=svg.children.find(n=>n.tagName==='path');
  assert.ok(curve.attributes.d.includes('M'));
  assert.ok(!curve.attributes.d.includes('NaN'));
  assert.equal((curve.attributes.d.match(/M/g)||[]).length,2);
  vm.runInContext('chart.destroy()',context);
  assert.equal(canvas.hidden,false);assert.equal(svg.removed,true);
});
