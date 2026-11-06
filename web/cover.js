(() => {
 'use strict';
 const el=id=>document.getElementById(id);
 const dateInput=el('cover-date'),formatInput=el('cover-format'),canvas=el('cover-canvas'),context=canvas.getContext('2d');
 const exportButton=el('cover-export'),errorBox=el('cover-error');
 const font='"SectorFlow Sans", sans-serif';
 const formats={portrait34:{width:1200,height:1600,label:'1200 × 1600 · 3:4'},portrait916:{width:1080,height:1920,label:'1080 × 1920 · 9:16'}};
 let automatic=true,renderSequence=0,rendered=false,exporting=false,activeTab='video';
 const image=new Image();
 const imageReady=new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=()=>reject(Error('封面底图加载失败，请刷新后重试。'));});
 // Keep the rejection handled even if a user stays in the video workspace.
 imageReady.catch(()=>{});image.src='assets/cover-background.png';
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
  el('cover-safe-note').textContent=formatInput.value==='portrait916'?'竖版文字已避开顶部、底部各220px安全区。':'参考图同款3:4比例，日期、标题与内容来源独立排版。';
  for(const id of ['cover-date','cover-format','cover-sync-date','cover-today'])el(id).disabled=exporting;
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
 async function render(){
  const sequence=++renderSequence;rendered=false;updateState();
  if(!validDate(dateInput.value)){showError('请选择有效的封面日期。');el('cover-status').textContent='等待选择日期';return false;}
  showError('');el('cover-status').textContent='正在生成封面预览…';
  try{
   await imageReady;await document.fonts.load('800 60px "SectorFlow Sans"');await document.fonts.ready;if(sequence!==renderSequence)return false;
   const {width,height}=formats[formatInput.value];canvas.width=width;canvas.height=height;
   const scale=Math.max(width/image.naturalWidth,height/image.naturalHeight),dw=image.naturalWidth*scale,dh=image.naturalHeight*scale;
   context.drawImage(image,(width-dw)/2,(height-dh)/2,dw,dh);
   const [,month,day]=dateInput.value.split('-'),dateText=`${Number(month)}月${day}日`,vertical=height===1920;
   const margin=vertical?88:105,maxWidth=width-margin*2;
   text(dateText,width/2,vertical?775:640,vertical?190:210,800,'#ffc400',maxWidth,'center',true);
   text('主力资金流向',width/2,vertical?1000:875,vertical?138:152,750,'#ffffff',maxWidth,'center',true);
   const lineY=vertical?1520:1338;
   context.save();context.strokeStyle='#e8edf4';context.lineWidth=3;context.beginPath();context.moveTo(margin,lineY);context.lineTo(width-margin,lineY);context.stroke();context.restore();
   text('内容来源：',margin,lineY+76,vertical?32:36,400,'#ffffff',maxWidth);
   text('数据来源于财信证券APP，部分素材取自千库网',margin,lineY+132,vertical?32:36,400,'#ffffff',maxWidth);
   canvas.setAttribute('aria-label',`${dateText}主力资金流向视频封面，${formats[formatInput.value].label}`);
   rendered=true;updateState();fit();el('cover-status').textContent=`封面已就绪 · ${dateInput.value}`;return true;
  }catch(error){if(sequence===renderSequence){showError(error.message);el('cover-status').textContent='封面生成失败';updateState();}return false;}
 }
 function refreshToday(){if(!exporting&&automatic&&dateInput.value!==today()){dateInput.value=today();render();}}
 function selectTab(name){
  activeTab=name==='cover'?'cover':'video';
  ['video','cover'].forEach(kind=>{const selected=kind===activeTab;el(`${kind}-tab`).setAttribute('aria-selected',String(selected));el(`${kind}-tab`).tabIndex=selected?0:-1;el(`${kind}-workspace`).hidden=!selected;});
  if(activeTab==='cover'){window.sectorFlow?.pause?.();refreshToday();fit();}
  else window.dispatchEvent(new Event('resize'));
 }
 ['video','cover'].forEach(name=>{
  const tab=el(`${name}-tab`);tab.addEventListener('click',()=>selectTab(name));
  tab.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();const next=event.key==='Home'?'video':event.key==='End'?'cover':name==='video'?'cover':'video';selectTab(next);el(`${next}-tab`).focus();});
 });
 dateInput.addEventListener('input',()=>{automatic=false;render();});
 formatInput.addEventListener('change',render);
 el('cover-today').addEventListener('click',()=>{automatic=true;dateInput.value=today();render();});
 el('cover-sync-date').addEventListener('click',()=>{const value=el('date').value;if(!validDate(value)){showError('请先在行情视频中选择有效日期。');return;}automatic=false;dateInput.value=value;render();});
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
  finally{exporting=false;updateState();}
 });
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshToday();});window.addEventListener('focus',refreshToday);window.addEventListener('resize',fit);setInterval(refreshToday,30000);
 if(window.ResizeObserver)new ResizeObserver(fit).observe(el('cover-preview-surface'));
 dateInput.value=today();render();
 window.sectorCover={today,render,selectTab,ready:()=>rendered,state:()=>({date:dateInput.value,automatic,format:formatInput.value,width:canvas.width,height:canvas.height,canExport:!exportButton.disabled,tab:activeTab})};
})();
