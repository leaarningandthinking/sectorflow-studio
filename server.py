from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse,parse_qs
from pathlib import Path
from datetime import datetime
import json,subprocess,sys,threading,uuid,math,re,os
os.environ.setdefault("PYTHONUTF8", "1")
from audio import audio_duration, MAX_MUSIC_BYTES, MUSIC_EXTENSIONS
from data_source import load_data, fetch_data, snapshot_path, default_date, validate_category, validate_source
ROOT=Path(__file__).resolve().parent
LOCK=threading.Lock()
class Handler(SimpleHTTPRequestHandler):
 def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'web'),**kwargs)
 def sendjson(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  u=urlparse(self.path)
  if u.path in ('/assets/caixin-brand.mp4','/assets/custom-outro.mp4'):self.send_brand_video('custom-outro.mp4' if u.path.endswith('custom-outro.mp4') else 'caixin-brand.mp4')
  elif u.path=='/api/data':
   try:
    query=parse_qs(u.query);category=validate_category(query.get('category',['industry'])[0]);source=validate_source(query.get('source',['top'])[0]);self.sendjson(load_data(query.get('date',[default_date(category,source)])[0],query.get('mode',['api'])[0],query.get('version',[None])[0],category,source))
   except FileNotFoundError as e:self.sendjson({'error':str(e)},404)
   except Exception as e:self.sendjson({'error':str(e)},400)
  elif u.path=='/api/info':
   try:
    query=parse_qs(u.query);category=validate_category(query.get('category',['industry'])[0]);source=validate_source(query.get('source',['top'])[0]);self.sendjson({'defaultDate':default_date(category,source),'category':category,'source':source,'defaultSource':'top'})
   except ValueError as e:self.sendjson({'error':str(e)},400)
  elif u.path.startswith('/output/'):
   name=Path(u.path).name;f=ROOT/'output'/name
   if not f.exists():self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type','video/mp4' if name.endswith('.mp4') else 'image/png');self.send_header('Content-Length',str(f.stat().st_size));self.send_header('Content-Disposition',f'attachment; filename="{name}"');self.end_headers()
   with f.open('rb') as src:
    while b:=src.read(1024*1024):self.wfile.write(b)
  elif u.path=='/static/app.js':self.path='/app.js';super().do_GET()
  else:super().do_GET()
 def send_brand_video(self,name='caixin-brand.mp4'):
  path=ROOT/'web'/'assets'/name
  if not path.is_file():self.send_error(404);return
  size=path.stat().st_size;start=0;end=size-1;status=200
  requested=self.headers.get('Range')
  if requested:
   match=re.fullmatch(r'bytes=(\d*)-(\d*)',requested)
   if match and (match[1] or match[2]):
    if match[1]:start=int(match[1]);end=min(size-1,int(match[2])) if match[2] else size-1
    else:start=max(0,size-int(match[2]))
   else:start=size
   if start>=size or start>end:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
   status=206
  self.send_response(status);self.send_header('Content-Type','video/mp4');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  with path.open('rb') as source:
   source.seek(start);remaining=end-start+1
   while remaining:
    chunk=source.read(min(1024*1024,remaining))
    if not chunk:break
    self.wfile.write(chunk);remaining-=len(chunk)
 def upload_music(self):
  dest=None
  try:
   extension=parse_qs(urlparse(self.path).query).get('ext',[''])[0].lower()
   length=int(self.headers.get('Content-Length','0'))
   if extension not in MUSIC_EXTENSIONS:raise ValueError('请选择 MP3、M4A 或 WAV 文件')
   if not 0<length<=MAX_MUSIC_BYTES:raise ValueError('音乐文件不能为空，且不能超过50MB')
   folder=ROOT/'music';folder.mkdir(exist_ok=True)
   music_id=uuid.uuid4().hex+extension;dest=folder/music_id
   remaining=length
   with dest.open('wb') as target:
    while remaining:
     chunk=self.rfile.read(min(remaining,1024*1024))
     if not chunk:raise ValueError('音乐上传未完成，请重新选择')
     target.write(chunk);remaining-=len(chunk)
   duration=audio_duration(dest)
   self.sendjson({'id':music_id,'duration':duration})
  except Exception as e:
   if dest:dest.unlink(missing_ok=True)
   self.sendjson({'error':str(e)},400)
 def do_POST(self):
  if urlparse(self.path).path=='/api/music':self.upload_music();return
  if urlparse(self.path).path=='/api/fetch':
   try:
    a=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),4096)));category=validate_category(a.get('category','industry'));source=validate_source(a.get('source','top'));self.sendjson(fetch_data(a.get('date',default_date(category,source)),category,source))
   except ValueError as e:self.sendjson({'error':str(e)},400)
   except Exception as e:self.sendjson({'error':str(e)},502)
   return
  if self.path!='/api/export':self.send_error(404);return
  try:
   a=json.loads(self.rfile.read(min(int(self.headers.get('Content-Length','0')),4096)));category=validate_category(a.get('category','industry'));source=validate_source(a.get('source','top'));date=a.get('date',default_date(category,source));datetime.strptime(date,'%Y-%m-%d');duration=float(a.get('duration',60));typ=a.get('type','cover')
   if typ not in ('cover','video') or not 3<=duration<=180:raise ValueError('type 或 duration 参数无效')
   mode=a.get('mode','api');version=a.get('dataset_version')
   if not version:raise ValueError('请先加载数据，再导出当前数据快照')
   snapshot=load_data(date,mode,version,category,source)
   music=a.get('music') if typ=='video' else None
   if music:
    music_id=music.get('id','')
    if not re.fullmatch(r'[0-9a-f]{32}\.(mp3|m4a|wav)',music_id):raise ValueError('音乐文件标识无效，请重新选择')
    music_path=ROOT/'music'/music_id
    volume=float(music.get('volume',.2));start=float(music.get('start',0))
    if not music_path.is_file():raise ValueError('音乐文件已丢失，请重新选择')
    if not math.isfinite(volume) or not 0<=volume<=1 or not math.isfinite(start) or not 0<=start<audio_duration(music_path):raise ValueError('音乐音量或起播时间无效')
   if not LOCK.acquire(blocking=False):self.sendjson({'error':'已有导出任务，请稍后重试'},409);return
   try:
    args=[sys.executable,str(ROOT/'export.py'),'--date',date,'--duration',str(duration),'--type',typ,'--category',category,'--source',source,'--snapshot',str(snapshot_path(snapshot['dataset_version']))]
    if music:args+=['--music',str(music_path),'--volume',str(volume),'--music-start',str(start)]
    result=subprocess.run(args,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=1200)
    if result.returncode:raise RuntimeError(result.stderr[-1200:] or result.stdout[-1200:])
   finally:LOCK.release()
   name=f'{date}_'+('top_' if source=='top' else '')+('concept_' if category=='concept' else '')+('cover.png' if typ=='cover' else 'fund_flow.mp4');self.sendjson({'filename':name,'url':'/output/'+name,'dataset_version':snapshot['dataset_version']})
  except Exception as e:self.sendjson({'error':str(e)},500)
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);a=p.parse_args();print(f'Open http://127.0.0.1:{a.port}',flush=True);ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()
