import csv, glob, collections, datetime, json, re, os
os.makedirs('build',exist_ok=True)
from severity import severity
CITYMAP={'BIRCHWOOD':'BIRCHWOOD VILLAGE',"SAINT MARY'S POINT":'SAINT MARYS POINT','ST PAUL PARK':'SAINT PAUL PARK','CG':'COTTAGE GROVE',
         'WB':'WOODBURY','O':'OAKDALE','M':'UNKNOWN','SAINT PAUL':'SAINT PAUL'}
def pdate(s):
    s=s.strip()
    for fmt in ('%m/%d/%Y %I:%M:%S %p','%m/%d/%Y %H:%M:%S','%m/%d/%Y %I:%M %p','%m/%d/%Y'):
        try: return datetime.datetime.strptime(s,fmt)
        except ValueError: pass
    return None
import os, sys
seen={}; rows=[]; bad=0; sources=set()
files=sorted(glob.glob('history/*.csv'))+sorted(glob.glob('raw/*.csv'))
if not files: sys.exit('no input CSVs found in history/ or raw/')
for f in files:
    with open(f,encoding='utf-8-sig',newline='') as fh:
        r=csv.reader(fh); hdr=next(r)
        src_col = hdr.index('SourceFile') if 'SourceFile' in hdr else None
        for row in r:
            sources.add(row[src_col].strip() if src_col is not None and len(row)>src_col and row[src_col].strip() else os.path.basename(f))
            if len(row)<6: bad+=1; continue
            ag,city,ts,case,addr,ev=[x.strip() for x in row[:6]]
            city=CITYMAP.get(city.upper(),city.upper())
            d=pdate(ts)
            if d is None: bad+=1; continue
            # strip trailing ", CITY"
            a=addr
            m=re.match(r'^(.*?),\s*([A-Z .\']+)$',a)
            if m: a=m.group(1).strip()
            key=case or (ts+a+ev)
            if key in seen: continue
            seen[key]=1
            rows.append({'c':case,'t':d.strftime('%Y-%m-%d %H:%M'),'a':a,'e':ev,'s':severity(ev),'city':city,'ag':ag})
print('rows',len(rows),'bad',bad)
yc=collections.Counter((r['city'],r['t'][:4]) for r in rows)
cities=sorted(set(r['city'] for r in rows))
for c in cities:
    print(f'{c:28s}', ' '.join(f'{y}:{yc[(c,y)]:6d}' for y in ('2022','2023','2024','2025','2026')))
print('date range', min(r['t'] for r in rows), max(r['t'] for r in rows))
json.dump(rows, open('build/incidents_all.json','w'))
json.dump(sorted(sources), open('build/sources.json','w'))
print('source files', len(sources))
