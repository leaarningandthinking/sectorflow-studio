let data=null,idx=0,playing=false,timer=null,chart=null,loading=false,loadSequence=0;
const $=id=>document.getElementById(id);
const lastFrame=()=>Math.max(1,(data?.times.length||241)-1);
const fmt=v=>Number.isFinite(v)?`${v>0?'+':''}${Number(v).toFixed(2)}亿`:'—';
function money(id,v){const e=$(id);e.textContent=fmt(v);e.style.color=!Number.isFinite(v)?'#9eb7d0':v<0?'#14dfad':'#ff597a';if(id==='total')e.style.fontSize='64px'}
const outroVideo=$('outro-video');
const CLOSE_HOLD_SECONDS=1,CUSTOM_OUTRO_SECONDS=5;
let outroActive=false;
function brandDuration(){return CUSTOM_OUTRO_SECONDS}
function endingDuration(){return CLOSE_HOLD_SECONDS+CUSTOM_OUTRO_SECONDS}
async function prepareOutro(){
 if(outroVideo.readyState>=2)return;
 await new Promise((resolve,reject)=>{const clear=()=>{clearTimeout(timeout);outroVideo.removeEventListener('loadeddata',done);outroVideo.removeEventListener('error',fail)};const done=()=>{clear();resolve()},fail=()=>{clear();reject(Error('片尾视频加载失败'))};const timeout=setTimeout(()=>{clear();reject(Error('片尾视频加载超时'))},15000);outroVideo.addEventListener('loadeddata',done,{once:true});outroVideo.addEventListener('error',fail,{once:true});outroVideo.load()});
}
const CHART_GRID={left:88,right:300,top:24,bottom:72};
const LINE_COLORS=['#FF567C','#FFB547','#40B9FF','#20E0C5','#BA92FF','#FF7FD1','#C8E95B','#FF895E','#62E0F3','#8FAEFF','#61E59A','#F6D85B','#D799F0','#73C9AE','#F5A8A8'];
function chartIndustries(){
 const seen=new Set();
 return (data?.industries||[]).filter(series=>{const key=series.code||series.name;if(seen.has(key))return false;seen.add(key);return true});
}
const lineColor=(s,i=chartIndustries().indexOf(s))=>LINE_COLORS[Math.max(0,i)%LINE_COLORS.length];
const LABEL_FONT='"SectorFlow Sans", sans-serif';
const labelMeasure=document.createElement('canvas').getContext('2d');
function chartInit(){
 if(!window.echarts){$('status').textContent='ECharts CDN 加载失败：请检查网络后刷新页面';return false}
 if(!chart){chart=echarts.init($('chart'),null,{renderer:'canvas',devicePixelRatio:2});window.addEventListener('resize',()=>{chart.resize();if(data){chart.setOption(chartOption(),{notMerge:true,lazyUpdate:false});chart.setOption({graphic:endpointLabels()},{lazyUpdate:false})}})}
 return true;
}
function chartOption(){
 CHART_GRID.right=labelGutter();
 const a=chartIndustries();const {min,max}=axisRange();
 const series=a.map((s,i)=>({name:s.name,type:'line',data:s.values.slice(0,idx+1).map((v,k)=>[k,v]),connectNulls:false,showSymbol:false,symbol:'circle',symbolSize:7,smooth:false,animation:false,clip:true,lineStyle:{width:3.6,color:lineColor(s,i),type:'solid',opacity:1,shadowColor:'#031023',shadowBlur:2},itemStyle:{color:lineColor(s,i)},emphasis:{disabled:true},endLabel:{show:false}}));
 return {textStyle:{fontFamily:LABEL_FONT},backgroundColor:'transparent',animation:false,grid:{...CHART_GRID,containLabel:false},
 xAxis:{type:'category',data:data.times,boundaryGap:false,min:0,max:lastFrame(),axisLine:{lineStyle:{color:'#87a9c5',width:1.5}},axisTick:{show:false},
 axisLabel:{color:'#a4bbd3',fontSize:22,margin:20,hideOverlap:true,interval:(i,value)=>i===0||i===lastFrame()||['09:30','10:30','11:30','14:00','15:00'].includes(value),formatter:value=>value},
 splitLine:{show:true,interval:(i,value)=>i===0||i===lastFrame()||['09:30','10:30','11:30','14:00','15:00'].includes(value),lineStyle:{color:'#17314a'}}},
 yAxis:{type:'value',min,max,splitNumber:8,axisLine:{show:false},axisLabel:{color:'#a4bbd3',fontSize:22,margin:16,hideOverlap:true,showMinLabel:false,showMaxLabel:false,formatter:v=>v>0?'+'+v:v},splitLine:{lineStyle:{color:'#28435b',opacity:.65}}},
 series};
}
// A fixed all-day range preserves proportions and avoids frame-to-frame axis jumps.
function axisRange(){
 const values=chartIndustries().flatMap(s=>s.values.filter(Number.isFinite));
 let lo=Math.min(0,...values),hi=Math.max(0,...values);
 if(lo===hi){lo=-1;hi=1}
 const span=hi-lo,raw=span/8,power=10**Math.floor(Math.log10(raw));
 const step=[1,2,5,10].map(n=>n*power).find(n=>n>=raw);
 // Use only the final deduplicated plotted series, never removed candidates.
 // Tick labels are computed independently; they must not enlarge these bounds.
 const padding=span*.025;
 const min=Number((lo-padding).toPrecision(12));
 const max=Number((hi+padding).toPrecision(12));
 return {min,max,step};
}
// Least-squares packing keeps each column as close as possible to its true endpoints.
function packLabels(items,top,bottom,gap){
 const blocks=[];
 items.forEach((item,i)=>{
  blocks.push({start:i,end:i,sum:item.y-i*gap,count:1});
  while(blocks.length>1){const b=blocks.at(-1),a=blocks.at(-2);if(a.sum/a.count<=b.sum/b.count)break;blocks.splice(-2,2,{start:a.start,end:b.end,sum:a.sum+b.sum,count:a.count+b.count})}
 });
 blocks.forEach(b=>{const y=Math.max(top,Math.min(bottom-(items.length-1)*gap,b.sum/b.count));for(let i=b.start;i<=b.end;i++)items[i].labelY=y+i*gap});
}
const LABEL_NAME_SIZE=24,LABEL_AMOUNT_SIZE=24,LABEL_OFFSET=14;
function labelDisplayName(series){
 if((data.meta?.category||'industry')!=='industry')return series.name;
 const simplify=name=>name.replace(/\s*(?:II|Ⅱ)$/u,'').trimEnd();
 const name=simplify(series.name);
 // Keep the original label when removing a classification suffix would create ambiguity.
 return name && chartIndustries().filter(s=>simplify(s.name)===name).length===1?name:series.name;
}
function endpointLabelStyle(series,value){
 const color=lineColor(series);
 return {
  text:`{name|${labelDisplayName(series)}} {amount|${fmt(value)}}`,verticalAlign:'middle',align:'left',fontFamily:LABEL_FONT,fontSize:20,
  rich:{name:{fontFamily:LABEL_FONT,fontSize:LABEL_NAME_SIZE,fontWeight:500,fill:color,lineHeight:28},amount:{fontFamily:LABEL_FONT,fontSize:LABEL_AMOUNT_SIZE,fontWeight:400,fill:color,lineHeight:28}},
  backgroundColor:'rgba(4,22,42,0.92)',padding:[3,3],borderRadius:3
 };
}
let gutterDataset=null,gutterWidth=0;
function labelGutter(){
 if(gutterDataset===data)return gutterWidth;
 let rightExtent=0;
 for(const series of chartIndustries()){
  labelMeasure.font=`400 ${LABEL_AMOUNT_SIZE}px ${LABEL_FONT}`;
  let widest=0,maxWidth=-1;
  for(const value of series.values){if(!Number.isFinite(value))continue;const width=labelMeasure.measureText(fmt(value)).width;if(width>maxWidth){maxWidth=width;widest=value}}
  // Measure exactly the same rich text and padding that ECharts will draw.
  const text=new echarts.graphic.Text({style:endpointLabelStyle(series,widest)}),r=text.getBoundingRect();
  rightExtent=Math.max(rightExtent,LABEL_OFFSET+r.x+r.width);
 }
 gutterDataset=data;gutterWidth=Math.ceil(rightExtent+8);return gutterWidth;
}
function endpointLabels(){
 const top=CHART_GRID.top+20,bottom=chart.getHeight()-CHART_GRID.bottom-20,gap=36;
 const items=chartIndustries().map((s,i)=>{
  if(!Number.isFinite(s.values[idx]))return null;
  const [x,y]=chart.convertToPixel({xAxisIndex:0,yAxisIndex:0},[idx,s.values[idx]]);
  return {s,i,x,y,labelY:y};
 }).filter(Boolean).sort((a,b)=>a.y-b.y||a.i-b.i);
 packLabels(items,top,bottom,gap);
 return items.flatMap(({s,i,x,y,labelY})=>[
  {id:'link-'+i,type:'polyline',silent:true,z:8,shape:{points:[[x,y],[x+6,y],[x+10,labelY]]},style:{stroke:lineColor(s,i),lineWidth:1.25,opacity:.9,fill:null}},
  {id:'dot-'+i,type:'circle',silent:true,z:12,shape:{cx:x,cy:y,r:3.5},style:{fill:lineColor(s,i)}},
  {id:'label-'+i,type:'text',silent:true,z:10,x:x+LABEL_OFFSET,y:labelY,style:endpointLabelStyle(s,s.values[idx])}
 ]);
}
function render(i,reset=true){
 if(!data)return;
 idx=Math.max(0,Math.min(lastFrame(),Math.round(i)));if(reset)resetEnding();
 $('scrub').value=idx;$('time').textContent=data.times[idx];$('progress').style.width=(idx/lastFrame()*100)+'%';
 let marketIndex=idx;
 const marketTime=data.meta?.market_asof?.[idx];
 if(marketTime)marketIndex=data.times.indexOf(marketTime);
 const validMarket=marketIndex>=0 && Number.isFinite(data.market.sh[marketIndex]) && Number.isFinite(data.market.sz[marketIndex]);
 const a=validMarket?data.market.sh[marketIndex]:null,b=validMarket?data.market.sz[marketIndex]:null,t=validMarket?a+b:null;
 money('total',t);money('sh',a);money('sz',b);
 $('arrow').textContent=t===null?'—':t<0?'↓':'↑';$('arrow').style.color=t===null?'#9eb7d0':t<0?'#14dfad':'#ff597a';
 const observed=validMarket?data.times[marketIndex]:null;
 $('market-asof').textContent=observed?`大盘截至 ${observed}${marketIndex!==idx?' · 当前分钟未更新':''}`:'当前分钟暂无大盘数据';
 if(chartInit()){chart.setOption(chartOption(),{notMerge:true,lazyUpdate:false});chart.setOption({graphic:endpointLabels()},{lazyUpdate:false})}
}
function updateEnabled(){
 const busy=loading||exporting;
 for(const id of ['date','data-mode-select','source-select','category-select','fetch-data','duration','music-enabled','music-file','music-clear','music-start','music-volume'])$(id).disabled=busy;
 for(const id of ['play','cover','video','preview-ending','scrub'])$(id).disabled=busy||!data;
 $('music-controls').disabled=busy||!$('music-enabled').checked;
 $('music-start').disabled=busy||!selectedMusic||!$('music-enabled').checked;$('music-volume').disabled=busy||!selectedMusic||!$('music-enabled').checked;
}
function stop(){musicPlayer.pause();playing=false;clearInterval(timer);timer=null;outroVideo.pause();$('play').textContent='▶ 播放预览'}
function resetEnding(){
 outroVideo.pause();outroActive=false;$('custom-ending').hidden=true;
 if(outroVideo.readyState>=1&&outroVideo.currentTime>.02)outroVideo.currentTime=0;
}
async function load(refresh=false){
 if(loading||exporting)return;
 const seq=++loadSequence;stop();resetEnding();loading=true;data=null;
 if(chart)chart.clear();['total','sh','sz'].forEach(id=>money(id,null));$('arrow').textContent='—';$('market-asof').textContent='等待获取数据';$('coverage-note').textContent='';
 updateEnabled();const date=$('date').value,mode=$('data-mode-select').value,category=$('category-select').value,source=$('source-select').value;
 $('industry-title').textContent=category==='concept'?'热门概念主力资金流向':'行业主力资金流向';
 $('fetch-data').textContent=mode==='demo'?'生成模拟演示':'获取／重新获取接口数据';
 $('status').textContent=refresh?`正在查询大盘与${category==='concept'?'概念':'行业'}接口…`:'正在读取数据…';$('data-health').textContent='正在检查数据状态…';
 try{
  await document.fonts.load('500 24px "SectorFlow Sans"');await document.fonts.ready;
  const r=refresh&&mode==='api'?await fetch('/api/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({date,category,source})}):await fetch('/api/data?date='+encodeURIComponent(date)+'&mode='+mode+'&category='+category+'&source='+source);
  const result=await r.json();if(!r.ok)throw Error(result.error||'取数失败');
  if(seq!==loadSequence)return;
  data=result;const [,m,day]=date.split('-');$('headline').innerHTML=`<span class="headline-date">${+m}月${+day}日</span><span class="headline-subject">主力资金流向</span>`;
  $('scrub').max=lastFrame();render(lastFrame());applyDataPresentation();
  $('status').textContent=`已加载 ${date} · ${data.mock?'模拟演示':'接口数据'}`;
 }catch(e){data=null;$('status').textContent='加载失败：'+e.message;$('data-health').textContent='未加载有效数据。可点击“获取／重新获取接口数据”重试。';}
 finally{loading=false;updateEnabled()}
}
function totalDuration(){return Math.min(186,Math.max(9,Math.round(Number($('duration').value)||21)))}
function replayDuration(){return totalDuration()-endingDuration()}
function clockText(seconds){const s=Math.max(0,Math.round(seconds));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}
function updatePreviewPhase(t=0,duration=replayDuration()){
 const phase=t<duration?'行情回放':t<duration+CLOSE_HOLD_SECONDS?'收盘停留':'视频片尾';
 if($('preview-phase'))$('preview-phase').textContent=phase;
 if($('preview-elapsed'))$('preview-elapsed').textContent=clockText(t);
 if($('preview-total'))$('preview-total').textContent=clockText(duration+endingDuration());
}
function updateDurationNote(){
 const d=replayDuration();$('export-duration-note').textContent=`行情 ${d} 秒 · 收盘停留 ${CLOSE_HOLD_SECONDS} 秒 · 视频片尾 ${CUSTOM_OUTRO_SECONDS} 秒`;
 if($('preview-total'))$('preview-total').textContent=clockText(totalDuration());
}
function fitPreview(){
 if(window.__sectorFlowExport)return;
 const canvas=document.querySelector('.preview-canvas'),wrap=document.querySelector('.stage-wrap');
 if(!canvas||!wrap)return;
 const scale=Math.max(.12,Math.min((canvas.clientWidth-40)/1080,(canvas.clientHeight-32)/1920,.6));
 wrap.style.setProperty('--preview-scale',String(scale));wrap.style.width=(1080*scale)+'px';wrap.style.height=(1920*scale)+'px';
}
function setTimeline(seconds,duration=replayDuration()){
 const t=Math.max(0,seconds);updatePreviewPhase(t,duration);syncPreviewMusic(t,duration+endingDuration());
 if(t<duration){const frame=Math.min(lastFrame(),Math.round(t/duration*lastFrame()));render(frame);return 'data:'+frame}
 // Draw the exact close without hiding and re-showing the ending layers every frame.
 if(idx!==lastFrame())render(lastFrame(),false);
 if(t<duration+CLOSE_HOLD_SECONDS){resetEnding();return 'data:'+lastFrame()}
 $('custom-ending').hidden=false;
 const elapsed=t-duration-CLOSE_HOLD_SECONDS,target=Math.max(0,Math.min(CUSTOM_OUTRO_SECONDS-1/30,elapsed));
 if(!outroActive||!playing||Math.abs(outroVideo.currentTime-target)>.25)outroVideo.currentTime=target;
 outroActive=true;
 if(playing&&elapsed<CUSTOM_OUTRO_SECONDS-1/30&&outroVideo.paused)outroVideo.play().catch(()=>{$('status').textContent='片尾自动播放受限，请重新点击播放预览'});
 if(!playing)outroVideo.pause();
 return 'outro:'+target.toFixed(5);
}
function syncPreviewMusic(t,total){
 if(!playing||!$('music-enabled').checked||!selectedMusic||!Number.isFinite(musicPlayer.duration))return;
 const start=Number($('music-start').value)||0,segment=Math.min(total,musicPlayer.duration-start);
 if(segment<=0)return;
 const target=start+(t%segment),fadeIn=Math.min(1,total/3),fadeOut=Math.min(2,total/3);
 musicPlayer.volume=Number($('music-volume').value)/100*Math.max(0,Math.min(1,t/fadeIn,(total-t)/fadeOut));
 if(Math.abs(musicPlayer.currentTime-target)>.25)musicPlayer.currentTime=target;
 if(musicPlayer.paused&&t<total)musicPlayer.play().catch(()=>{$('status').textContent='背景音乐播放受限，请重新点击播放预览'});
}
async function setExportFrame(t,duration){
 await prepareOutro();const key=setTimeline(t,duration);
 if(outroVideo.seeking)await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>{outroVideo.removeEventListener('seeked',done);reject(Error('片尾视频定位超时'))},10000);const done=()=>{clearTimeout(timeout);resolve()};outroVideo.addEventListener('seeked',done,{once:true})});
 await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
 return key;
}
function runPlayback(from,duration){
 playing=true;$('play').textContent='❚❚ 暂停';const started=performance.now();
 timer=setInterval(()=>{const t=from+(performance.now()-started)/1000;setTimeline(Math.min(t,duration+endingDuration()),duration);if(t>=duration+endingDuration()){stop();setTimeline(duration+endingDuration(),duration);updatePreviewPhase(duration+endingDuration(),duration);if($('preview-phase'))$('preview-phase').textContent='预览结束'}},50);
}
async function play(){if(playing){stop();return}try{await prepareOutro();const duration=replayDuration(),from=idx>=lastFrame()?0:idx/lastFrame()*duration;runPlayback(from,duration)}catch(e){$('status').textContent='片尾视频加载失败，请刷新后重试'}}
async function previewEnding(){stop();try{await prepareOutro();const duration=replayDuration();setTimeline(duration,duration);runPlayback(duration,duration)}catch(e){$('status').textContent='片尾视频加载失败，请刷新后重试'}}
let exporting=false;
async function exportFile(type){
 if(exporting||!data)return;
 if(type==='video' && $('music-enabled').checked && !selectedMusic){showMusicError();return}
 stop();exporting=true;updateEnabled();
 $('status').textContent='正在生成'+(type==='video'?'视频':'封面')+'…';
 try{
  const music=type==='video'?await prepareMusic():null;
  const r=await fetch('/api/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({music,date:data.date,category:data.meta?.category||'industry',source:data.meta?.source_key||'legacy',mode:data.mock?'demo':'api',dataset_version:data.meta?.dataset_version,duration:replayDuration(),type})});
  const result=await r.json();if(!r.ok)throw Error(result.error||'导出失败');
  $('status').textContent='导出完成：'+result.filename;
  const a=document.createElement('a');a.href=result.url;a.download=result.filename;document.body.appendChild(a);a.click();a.remove();
 }catch(e){$('status').textContent='导出失败：'+e.message}
 finally{exporting=false;updateEnabled()}
}
function applyDataPresentation(){
 const mock=data.mock!==false,meta=data.meta||{},market=meta.market_range||[data.times[0],data.times.at(-1)],industry=meta.sector_range||meta.industry_range||[data.times[0],data.times.at(-1)],rank=meta.rank_as_of||industry[1],scope=meta.rank_universe_count||10;
 $('stage').classList.toggle('is-demo',mock);
 const concept=meta.category==='concept',kind=concept?'概念':'行业',rule=concept?'净流入前10':`净流入前${meta.rank_positive_count??(data.industries.length===15?8:5)}＋净流出前${meta.rank_negative_count??(data.industries.length===15?7:5)}`,isTop=meta.source_key==='top',sourceName=isTop?'恒生资金流 · TOP榜单':'原资金流接口';
 const filtered=!concept&&!!meta.industry_filter_version;
 const filterSummary=filtered&&!mock?`接口返回${meta.raw_rank_universe_count}个，剔除一级行业${meta.excluded_level1_count}个，剩余${scope}个；本次展示${data.industries.length}个（${rule}，最多8＋7）`:'';
 $('industry-title').textContent=concept?'热门概念主力资金流向':'行业主力资金流向';
 $('replay-mode').textContent=rank==='15:00'?'收盘回放':'盘中回放';
 $('intro').textContent=mock?'模拟演示 · 不代表真实行情':'财信证券APP · 资金流视频';
 $('coverage-note').textContent=mock?'模拟数据':filterSummary||`${rank} 返回 ${scope} 个${kind}，${rule}`;
 $('data-description').textContent=mock?'模拟数据仅供功能演示。':`${filtered?'先剔除31个一级行业，再按实际正负金额排名；数量不足时按实际展示。':''}按${rank}净流入金额选${rule}后固定回放。${kind}排名限接口返回范围，缺失点不补零、不插值。大盘仅更新到${market[1]}，后续保留最后已获取金额。`;
 $('data-health').textContent=`数据源：${sourceName}
大盘：${market[0]}—${market[1]}
${kind}：${industry[0]}—${industry[1]}
排名：${rank} · ${filterSummary||`返回${scope}个${kind} · ${rule}`} 
缺失${kind}分钟：${meta.missing_selected_points??0}个
${mock?'模拟演示':meta.dataset_version?'版本：'+meta.dataset_version.slice(0,12):'接口快照'}`;
 for(const id of ['data-mode','ending-data-mode','brand-data-mode']){if($(id)){$(id).hidden=true;$(id).textContent=''}}
 updateDurationNote();fitPreview();if($('preview-phase'))$('preview-phase').textContent='收盘画面';if($('preview-elapsed'))$('preview-elapsed').textContent=clockText(replayDuration());
}
// The browser previews the local file; only exports copy it to the local server.
let selectedMusic=null,musicObjectURL=null,uploadedMusic=null;
const musicPlayer=$('music-player');
function showMusicError(){
 const message='背景音乐已开启，请先选择本地音乐；如需无背景音乐的视频，请关闭开关。';
 $('music-error').textContent=message;$('music-error').hidden=false;$('status').textContent=message;
 $('music-enabled').closest('.settings-card').scrollIntoView({behavior:'smooth',block:'center'});
 $('music-enabled').focus({preventScroll:true});
}
$('music-enabled').addEventListener('change',()=>{
 const enabled=$('music-enabled').checked;
 $('music-state').textContent=enabled?'开启':'关闭';$('music-controls').hidden=!enabled;
 $('music-error').hidden=true;if(!enabled)musicPlayer.pause();updateEnabled();
});
function clearMusic(){
 musicPlayer.pause();musicPlayer.removeAttribute('src');musicPlayer.load();
 if(musicObjectURL)URL.revokeObjectURL(musicObjectURL);
 selectedMusic=null;musicObjectURL=null;uploadedMusic=null;
 $('music-file').value='';$('music-info').textContent='未选择音乐 · 导出前请选择本地音乐';
 musicPlayer.hidden=true;$('music-clear').hidden=true;
 $('music-start').value=0;$('music-start').disabled=true;$('music-volume').disabled=true;
}
$('music-file').addEventListener('change',()=>{
 const file=$('music-file').files[0];if(!file)return;
 if(!/\.(mp3|m4a|wav)$/i.test(file.name)||file.size>50*1024*1024||file.size===0){
  $('status').textContent='请选择不超过50MB的 MP3、M4A 或 WAV 音乐';$('music-file').value='';return;
 }
 clearMusic();$('music-error').hidden=true;selectedMusic=file;musicObjectURL=URL.createObjectURL(file);
 musicPlayer.src=musicObjectURL;musicPlayer.volume=Number($('music-volume').value)/100;
 musicPlayer.hidden=false;$('music-clear').hidden=false;
 $('music-start').disabled=false;$('music-volume').disabled=false;
 $('music-info').textContent=file.name+' · 正在读取…';
});
musicPlayer.addEventListener('loadedmetadata',()=>{
 if(!selectedMusic)return;
 const seconds=musicPlayer.duration;
 $('music-info').textContent=selectedMusic.name+' · '+(Number.isFinite(seconds)?Math.floor(seconds/60)+':'+String(Math.floor(seconds%60)).padStart(2,'0'):'时长未知');
 if(Number.isFinite(seconds))$('music-start').max=Math.max(0,seconds-.1);
});
musicPlayer.addEventListener('error',()=>{if(selectedMusic)$('music-info').textContent=selectedMusic.name+' · 无法试听，请检查文件或更换格式'});
$('music-volume').addEventListener('input',()=>{const v=Number($('music-volume').value);musicPlayer.volume=v/100;$('music-volume-label').textContent=v+'%'});
$('music-start').addEventListener('change',()=>{
 const start=Number($('music-start').value);
 if(Number.isFinite(start)&&start>=0&&start<musicPlayer.duration)musicPlayer.currentTime=start;
});
$('music-clear').onclick=clearMusic;
async function prepareMusic(){
 if(!$('music-enabled').checked)return null;
 if(!selectedMusic){showMusicError();throw Error('背景音乐已开启，请先选择本地音乐')}
 const file=selectedMusic,start=Number($('music-start').value),volume=Number($('music-volume').value)/100;
 if(!Number.isFinite(start)||start<0||(Number.isFinite(musicPlayer.duration)&&start>=musicPlayer.duration))throw Error('起播时间必须在音乐时长范围内');
 if(!uploadedMusic){
  const r=await fetch('/api/music?ext='+encodeURIComponent('.'+file.name.split('.').pop().toLowerCase()),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
  if(r.status===404||r.status===501)throw Error('请先重启本地服务以启用音乐功能');
  const response=await r.json();if(!r.ok)throw Error(response.error||'音乐上传失败');
  if(selectedMusic!==file)throw Error('音乐选择已变化，请重新导出');
  uploadedMusic=response;
 }
 if(start>=uploadedMusic.duration)throw Error('起播时间必须小于音乐总时长');
 return {id:uploadedMusic.id,volume,start};
}

$('date').addEventListener('change',()=>load(false));$('data-mode-select').addEventListener('change',()=>load(false));$('category-select').addEventListener('change',()=>load(false));$('source-select').addEventListener('change',()=>load(false));$('fetch-data').onclick=()=>load(true);
$('scrub').addEventListener('input',e=>{stop();render(+e.target.value);updatePreviewPhase(Math.min(replayDuration()-.001,idx/lastFrame()*replayDuration()),replayDuration())});$('play').onclick=play;$('cover').onclick=()=>exportFile('cover');$('video').onclick=()=>exportFile('video');
$('duration').addEventListener('input',updateDurationNote);$('duration').addEventListener('change',()=>{$('duration').value=totalDuration();updateDurationNote()});outroVideo.addEventListener('loadedmetadata',updateDurationNote);$('preview-ending').onclick=previewEnding;
window.sectorFlow={pause:stop,setFrame:render,lastFrame,setTimeline,setExportFrame,get endingDuration(){return endingDuration()},ready:()=>!!data&&!!chart,load,brandDuration,replayDuration,totalDuration};
updateDurationNote();
window.addEventListener('resize',fitPreview);
if(document.querySelector('.preview-canvas'))new ResizeObserver(fitPreview).observe(document.querySelector('.preview-canvas'));
requestAnimationFrame(fitPreview);
if(window.__sectorFlowSnapshot){
 const snapshot=window.__sectorFlowSnapshot;$('date').value=snapshot.date;$('data-mode-select').value=snapshot.mock?'demo':'api';$('category-select').value=snapshot.meta?.category||'industry';$('source-select').value=snapshot.meta?.source_key||'legacy';load(false);
}else{
 fetch('/api/info').then(r=>r.ok?r.json():null).then(info=>{if(info?.defaultDate)$('date').value=info.defaultDate;load(false)}).catch(()=>load(false));
}
