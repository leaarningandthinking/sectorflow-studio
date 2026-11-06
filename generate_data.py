import json, math, random
from datetime import datetime,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parent
NAMES=['消费电子','自动化设备','医疗服务','汽车零部件','小家电','光伏设备','工业金属','证券Ⅱ','半导体','电池']
ENDS=[28.8,14.3,9.9,5.1,4.0,-28.7,-21.9,-21.3,-19.3,-17.8]
COLORS=['#ff5479','#ffc054','#4fa9ff','#2bd9cc','#b28cff','#32d9a4','#f5bd48','#e38bcf','#8ea9ff','#4dd5f2']
def make(date):
 datetime.strptime(date,'%Y-%m-%d'); r=random.Random(int(date.replace('-',''))); n=241
 times=[(datetime(2026,1,1,9,30)+timedelta(minutes=i)).strftime('%H:%M') if i<=120 else (datetime(2026,1,1,13,0)+timedelta(minutes=i-120)).strftime('%H:%M') for i in range(n)]
 def curve(end,k):
  raw=[0.0]
  for i in range(1,n):raw.append(raw[-1]+r.gauss(0,.45))
  return [round(end*t+(.85*(raw[i]-t*raw[-1]))+min(5,abs(end)*.24)*math.sin(math.pi*t)*math.sin((k%4+1)*math.pi*t+k*.5),3) for i in range(n) for t in [i/(n-1)]]
 series=[{'code':f'MOCK{i+1:03d}','name':name,'color':COLORS[i],'values':curve(ENDS[i],i)} for i,name in enumerate(NAMES)]
 sh=curve(-2.36,11);sz=curve(-2.96,12)
 return {'date':date,'mock':True,'unit':'亿元','times':times,'industries':series,'market':{'sh':sh,'sz':sz,'total':[round(a+b,3) for a,b in zip(sh,sz)]},'meta':{'classification':'申万二级（演示行业名，模拟数据）','rank_mode':'close_top5_positive_negative'}}
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--date',default='2026-10-20');a=p.parse_args();d=make(a.date);out=ROOT/'data'/f'{a.date}.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(d,ensure_ascii=False),encoding='utf8');print(out)
