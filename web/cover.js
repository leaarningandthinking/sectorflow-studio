(() => {
 'use strict';
 const el=id=>document.getElementById(id);
 const dateInput=el('cover-date'),formatInput=el('cover-format'),canvas=el('cover-canvas'),context=canvas.getContext('2d');
 const exportButton=el('cover-export'),errorBox=el('cover-error'),colorInput=el('cover-color-mode');
 const font='"SectorFlow Sans", sans-serif';
 const formats={portrait34:{width:1200,height:1600,label:'1200 × 1600 · 3:4'},portrait916:{width:1080,height:1920,label:'1080 × 1920 · 9:16'}};
 let automatic=true,renderSequence=0,rendered=false,exporting=false,activeTab='video';
 let color='blue',judged=false,marketDate=null,marketSequence=0,deferred=false;
 let colorReason='尚未获取该日大盘数据，未自动判定。';
 const backgrounds=new Map();
 function backgroundFor(selectedColor){
  const file=`cover-${selectedColor}-finance.png`;
  if(!backgrounds.has(file)){
   const image=new Image(),promise=new Promise((resolve,reject)=>{image.onload=()=>resolve(image);image.onerror=()=>{backgrounds.delete(file);reject(Error('封面底图加载失败，请刷新后重试。'));}});
   backgrounds.set(file,promise);image.src='assets/'+file+'?rev=20261126';
  }
  return backgrounds.get(file);
 }
 function today(){
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(new Date());
  const value=type=>parts.find(part=>part.type===type).value;
  return `${value('year')}-${value('month')}-${value('day')}`;
 }
 function validDate(value){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
  const [year,month,day]=value.split('-').map(Number),d=new Date(0);d.setUTCFullYear(year,month-1,day);d.setUTCHours(0,0,0,0);
  return year>=1&&d.getUTCFullYear()===year&&d.getUTCMonth()===month-1&&d.getUTCDate()===day;
 }
 function showError(message){errorBox.textContent=message;errorBox.hidden=!message;}
 function filename(){return `${dateInput.value}_主力资金流向_封面.jpg`;}
 function updateState(){
  el('cover-date-state').textContent=automatic?'自动 · 北京时间今天':'自选日期';
  el('cover-today').hidden=automatic;
  el('cover-file-name').textContent=validDate(dateInput.value)?filename():'请选择封面日期';
  el('cover-format-badge').textContent=formats[formatInput.value].label;
  el('cover-safe-note').textContent=formatInput.value==='portrait916'?'9:16封面 · 标题完整显示，内容来源避开底部220px安全区。':'3:4封面 · 日期、标题与内容来源独立排版。';
  el('cover-color-badge').textContent=(color==='red'?'红色':'蓝色')+(colorInput.value==='auto'&&!judged?' · 未判定':'');
  el('cover-color-badge').dataset.color=color;
  el('cover-color-reason').textContent=colorReason;
  for(const id of ['cover-date','cover-format','cover-sync-date','cover-today','cover-color-mode','cover-color-refresh'])el(id).disabled=exporting;
  exportButton.disabled=exporting||!rendered||!validDate(dateInput.value);
  exportButton.textContent=exporting?'正在导出…':'↓ 导出封面';
 }
 function fit(){
  const surface=el('cover-preview-surface');if(surface.clientWidth===0||surface.clientHeight===0)return;
  const s=getComputedStyle(surface),w=surface.clientWidth-parseFloat(s.paddingLeft)-parseFloat(s.paddingRight),h=surface.clientHeight-parseFloat(s.paddingTop)-parseFloat(s.paddingBottom);
  const ratio=Math.min(w/canvas.width,h/canvas.height,1);canvas.style.width=`${Math.max(1,Math.floor(canvas.width*ratio))}px`;canvas.style.height=`${Math.max(1,Math.floor(canvas.height*ratio))}px`;
 }
 function setFont(size,weight){context.font=`${weight} ${size}px ${font}`;}
 function text(value,x,y,size,weight,color,maxWidth,align='left',shadow=false){
  context.save();let actual=size;setFont(actual,weight);
  if(context.measureText(value).width>maxWidth){actual*=maxWidth/context.measureText(value).width;setFont(actual,weight);}
  context.textAlign=align;context.textBaseline='alphabetic';context.fillStyle=color;
  if(shadow){context.shadowColor='rgba(0,0,0,.4)';context.shadowBlur=6;context.shadowOffsetX=8;context.shadowOffsetY=10;}
  context.fillText(value,x,y);context.restore();
 }
 const MAX_COVER_BYTES=500000;
 function encodeJpeg(source,quality){
  return new Promise((resolve,reject)=>source.toBlob(blob=>blob&&blob.type==='image/jpeg'?resolve(blob):reject(Error('封面压缩失败，请重试。')),'image/jpeg',quality));
 }
 async function compressedCover(){
  let source=canvas;
  for(let attempt=0;attempt<12;attempt++){
   let best=await encodeJpeg(source,.96);
   if(best.size<=MAX_COVER_BYTES)return best;
   best=await encodeJpeg(source,.5);
   if(best.size<=MAX_COVER_BYTES){
    let low=.5,high=.96;
    for(let i=0;i<7;i++){
     const quality=(low+high)/2,blob=await encodeJpeg(source,quality);
     if(blob.size<=MAX_COVER_BYTES){best=blob;low=quality;}else high=quality;
    }
    return best;
   }
   const smaller=document.createElement('canvas');
   smaller.width=Math.max(1,Math.round(source.width*.85));smaller.height=Math.max(1,Math.round(source.height*.85));
   const ctx=smaller.getContext('2d');ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';ctx.drawImage(source,0,0,smaller.width,smaller.height);source=smaller;
  }
  throw Error('封面无法压缩至500KB以内，请重试。');
 }
 function roundRect(x,y,width,height,radius,fill,topOnly=false){
  context.beginPath();context.moveTo(x+radius,y);context.lineTo(x+width-radius,y);context.quadraticCurveTo(x+width,y,x+width,y+radius);
  context.lineTo(x+width,y+height-(topOnly?0:radius));
  if(!topOnly)context.quadraticCurveTo(x+width,y+height,x+width-radius,y+height);
  context.lineTo(x+(topOnly?0:radius),y+height);if(!topOnly)context.quadraticCurveTo(x,y+height,x,y+height-radius);
  context.lineTo(x,y+radius);context.quadraticCurveTo(x,y,x+radius,y);context.closePath();context.fillStyle=fill;context.fill();
 }
 async function render(){
  if(exporting){deferred=true;return false;}
  const sequence=++renderSequence,selectedColor=color,selectedDate=dateInput.value,selectedFormat=formatInput.value;
  rendered=false;updateState();
  if(!validDate(selectedDate)){showError('请选择有效的封面日期。');el('cover-status').textContent='等待选择日期';return false;}
  showError('');el('cover-status').textContent='正在生成封面预览…';
  try{
   const image=await backgroundFor(selectedColor);
   await document.fonts.load('900 60px "SectorFlow Sans"');await document.fonts.ready;
   if(sequence!==renderSequence||exporting)return false;
   const {width,height}=formats[selectedFormat],vertical=selectedFormat==='portrait916';canvas.width=width;canvas.height=height;
   const scale=Math.max(width/image.naturalWidth,height/image.naturalHeight),dw=image.naturalWidth*scale,dh=image.naturalHeight*scale;
   context.drawImage(image,(width-dw)/2,(height-dh)/2,dw,dh);
   const [,month,day]=selectedDate.split('-'),dateText=`${Number(month)}月${Number(day)}日`;
   const cardX=width*.10,cardY=height*(vertical?.335:.363),cardW=width*.817,cardH=height*(vertical?.365:.423);
   const tabY=height*(vertical?.248:.261),tabH=cardY-tabY+2,tabW=width*.409;
   roundRect(cardX,tabY,tabW,tabH,width*.035,selectedColor==='red'?'#ff1010':'#1559ff',true);
   roundRect(cardX,cardY,cardW,cardH,width*.035,'#ffffff');
   text(dateText,cardX+width*.028,tabY+tabH*.73,width*.094,900,'#ffffff',tabW-width*.056);
   const titleX=cardX+width*.035,titleSize=width*.174;
   text('主力资金',titleX,cardY+cardH*.39,titleSize,900,'#403535',cardW-width*.07);
   text('流向',titleX,cardY+cardH*.87,titleSize,900,'#403535',cardW-width*.07);
   const footerY=vertical?height-240:height*.973;
   text('内容来源：数据来源于财信证券　部分素材取自千库网',width*.5,footerY,width*.021,500,'#ffffff',width*.88,'center');
   canvas.setAttribute('aria-label',`${dateText}主力资金流向视频封面，${selectedColor==='red'?'红色':'蓝色'}，${formats[selectedFormat].label}`);
   rendered=true;updateState();fit();el('cover-status').textContent=`封面已就绪 · ${selectedDate}`;return true;
  }catch(error){if(sequence===renderSequence){showError(error.message);el('cover-status').textContent='封面生成失败';updateState();}return false;}
 }
 function sourceKey(){return el('source-select')?.value||'top';}
 function invalidateMarket(){marketSequence++;judged=false;marketDate=null;if(colorInput.value==='auto')colorReason='正在检查所选日期的已获取大盘数据…';}
 async function refreshMarket(){
  if(exporting){deferred=true;return;}
  if(colorInput.value!=='auto')return;
  const sequence=++marketSequence,date=dateInput.value,source=sourceKey();judged=false;marketDate=null;
  if(!validDate(date)){colorReason='请选择有效日期后自动判断。';updateState();return;}
  colorReason='正在检查所选日期的已获取大盘数据…';updateState();
  try{
   const response=await fetch(`/api/cover-market?${new URLSearchParams({date,source})}`,{cache:'no-store'});
   if(!response.ok)throw Error('暂时无法读取已获取的数据');
   const result=await response.json();
   if(sequence!==marketSequence||date!==dateInput.value||source!==sourceKey()||colorInput.value!=='auto')return;
   if(exporting){deferred=true;return;}
   if(result.date!==date||result.source!==source)throw Error('返回数据与所选日期或数据源不一致');
   if(result.available&&['red','blue'].includes(result.color)){
    color=result.color;judged=true;marketDate=date;
    const exact=String(result.total_exact??result.total_decimal??result.total),total=Number(exact),negative=exact.trim().startsWith('-'),nonzero=/[1-9]/.test(exact.split(/[eE]/)[0]);
    const magnitude=Number.isFinite(total)&&(!nonzero||Math.abs(total)>=.005)?Math.abs(total).toFixed(2):exact.replace(/^[+-]/,'');
    const amount=`${negative?'−':'+'}${magnitude}`;
    colorReason=`自动选中${color==='red'?'红色':'蓝色'} · ${date} · 两市合计 ${amount}亿元${result.as_of?' · '+result.as_of:''}（已获取真实数据）`;
   }else colorReason='尚未获取该日大盘数据，未自动判定；保留当前配色，可直接导出或手动选择。';
   updateState();await render();
  }catch(error){
   if(sequence!==marketSequence||date!==dateInput.value||source!==sourceKey()||colorInput.value!=='auto')return;
   if(exporting){deferred=true;return;}
   colorReason=`未自动判定：${error.message}。保留当前配色，可手动选择并导出。`;updateState();
  }
 }
 function dateChanged(){invalidateMarket();render();refreshMarket();}
 function refreshToday(){if(!exporting&&automatic&&dateInput.value!==today()){dateInput.value=today();dateChanged();}}
 function selectTab(name){
  activeTab=name==='cover'?'cover':'video';
  ['video','cover'].forEach(kind=>{const selected=kind===activeTab;el(`${kind}-tab`).setAttribute('aria-selected',String(selected));el(`${kind}-tab`).tabIndex=selected?0:-1;el(`${kind}-workspace`).hidden=!selected;});
  if(activeTab==='cover'){window.sectorFlow?.pause?.();refreshToday();refreshMarket();fit();}
  else window.dispatchEvent(new Event('resize'));
 }
 ['video','cover'].forEach(name=>{
  const tab=el(`${name}-tab`);tab.addEventListener('click',()=>selectTab(name));
  tab.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'video':event.key==='End'?'cover':name==='video'?'cover':'video';selectTab(next);el(`${next}-tab`).focus();});
 });
 dateInput.addEventListener('input',()=>{automatic=false;dateChanged();});
 formatInput.addEventListener('change',render);
 colorInput.addEventListener('change',()=>{invalidateMarket();if(colorInput.value==='auto'){refreshMarket();}else{color=colorInput.value;colorReason=`手动选择${color==='red'?'红色':'蓝色'}封面 · 数据更新不会覆盖你的选择。`;render();}});
 el('cover-color-refresh').addEventListener('click',refreshMarket);
 el('source-select')?.addEventListener('change',()=>{if(colorInput.value==='auto'){invalidateMarket();refreshMarket();}});
 window.addEventListener('sectorflow-data-updated',refreshMarket);
 el('cover-today').addEventListener('click',()=>{automatic=true;dateInput.value=today();dateChanged();});
 el('cover-sync-date').addEventListener('click',()=>{const value=el('date').value;if(!validDate(value)){showError('请先在行情视频中选择有效日期。');return;}automatic=false;dateInput.value=value;dateChanged();});
 exportButton.addEventListener('click',async()=>{
  if(exporting)return;
  refreshToday();if(!rendered||!validDate(dateInput.value)){await render();if(!rendered)return;}
  exporting=true;updateState();showError('');
  const exportName=filename();
  try{
   const blob=await compressedCover();
   if(blob.size>MAX_COVER_BYTES)throw Error('封面超过500KB，已停止导出。');
   const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=exportName;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);
   el('cover-status').textContent=`已导出：${exportName} · ${Math.ceil(blob.size/1000)}KB`;
  }catch(error){showError(error.message);el('cover-status').textContent='封面导出失败';}
  finally{exporting=false;updateState();if(deferred){deferred=false;render();refreshMarket();}}
 });
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshToday();});window.addEventListener('focus',refreshToday);window.addEventListener('resize',fit);setInterval(refreshToday,30000);
 if(window.ResizeObserver)new ResizeObserver(fit).observe(el('cover-preview-surface'));
 dateInput.value=today();render();refreshMarket();
 window.sectorCover={today,render,selectTab,ready:()=>rendered,state:()=>({date:dateInput.value,automatic,format:formatInput.value,width:canvas.width,height:canvas.height,canExport:!exportButton.disabled,tab:activeTab,color,selection:colorInput.value,marketDate,judged})};
})();
