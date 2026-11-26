"""Check compact geometry, final expansion, and the actual export API."""
from pathlib import Path
import sys,subprocess,tempfile,shutil,time,socket,json
from urllib.request import urlopen,Request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='sectorflow compact ') as directory:
 root=Path(directory)
 for path in ROOT.glob('*.py'):shutil.copy2(path,root/path.name)
 shutil.copytree(ROOT/'web',root/'web')
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 url=f'http://127.0.0.1:{port}/'
 with (root/'server.log').open('w') as log:
  server=subprocess.Popen([sys.executable,str(root/'server.py'),'--port',str(port)],stdout=log,stderr=log)
  try:
   for _ in range(100):
    try:
     if urlopen(url,timeout=1).status==200:break
    except OSError:time.sleep(.1)
   with sync_playwright() as p:
    b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000})
    page.goto(url);page.wait_for_function('window.sectorFlow && !loading')
    page.select_option('#data-mode-select','demo');page.wait_for_function('window.sectorFlow.ready()')
    assert page.locator('#video-template').input_value()=='standard'
    def geometry(t):return page.evaluate('t=>{setTimeline(t,15);return {expansion:labelExpansion,positions:endpointLabels().filter(x=>x.type==="text").map(x=>({id:x.id,x:x.x,y:x.y,text:x.style.text})),curves:chartIndustries().length}}',t)
    assert page.evaluate('idx === lastFrame()')
    page.select_option('#video-template','compact')
    assert page.evaluate('idx < lastFrame() && labelExpansion === 0')
    page.click('#play');page.wait_for_timeout(200)
    assert page.evaluate('playing && labelExpansion === 0 && idx < lastFrame()*.1')
    page.evaluate('stop()')
    page.select_option('#video-template','standard')
    standard=geometry(0)
    page.select_option('#video-template','compact');compact=geometry(0)
    assert compact['curves']==standard['curves']==15
    assert compact['expansion']==0 and standard['expansion']==1
    assert abs(compact['positions'][-1]['y']-compact['positions'][0]['y'])<abs(standard['positions'][-1]['y']-standard['positions'][0]['y'])
    assert all(a['text']==z['text'] and a['x']==z['x'] for a,z in zip(standard['positions'],compact['positions']))
    for t in [14,14.7,14.9,15,15.2]:
     result=geometry(t)
     assert result['expansion']==(0 if t<14.8 else 1) if t!=14.9 else 0<result['expansion']<1
     if t>=15:
      page.select_option('#video-template','standard');reference=geometry(t);page.select_option('#video-template','compact')
      assert result['positions']==reference['positions'],(t,result,reference)
    for t in [15,15.3,16.299]:
     page.evaluate('t=>setTimeline(t,15)',t)
     assert page.evaluate('labelExpansion === 1 && document.querySelector("#custom-ending").hidden')
    page.evaluate('setTimeline(16.301,15)')
    assert page.evaluate('!document.querySelector("#custom-ending").hidden')
    page.evaluate('setTimeline(0,15)');(ROOT/'output/test-artifacts').mkdir(parents=True,exist_ok=True)
    page.locator('#stage').screenshot(path=str(ROOT/'output/test-artifacts/compact-labels.png'))
    page.evaluate('setTimeline(15,15)');page.locator('#stage').screenshot(path=str(ROOT/'output/test-artifacts/compact-close.png'))
    b.close()
   snapshot=json.load(urlopen(url+'api/data?date=2026-11-26&mode=demo&category=industry&source=top'))
   payload={'date':snapshot['date'],'mode':'demo','category':'industry','source':'top','dataset_version':snapshot['dataset_version'],'duration':3,'type':'video','template':'compact'}
   with urlopen(Request(url+'api/export',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=300) as response:result=json.load(response)
   assert result['filename']=='2026-11-26_top_compact_fund_flow.mp4',result
   video=root/'output'/result['filename']
   info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','json',str(video)]))
   assert abs(float(info['format']['duration'])-11.3)<.1
   print('PASS compact/standard geometry, all labels retained, deterministic 1.3-second close hold, actual API/CLI export and distinct filename')
  finally:server.terminate();server.wait(timeout=10)
