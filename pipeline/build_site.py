#!/usr/bin/env python3
"""Build the multi-city site: site/index.html + site/data/*.json"""
import json, math, os, re, collections, sys, datetime, glob
OUT=sys.argv[1] if len(sys.argv)>1 else '../'
sys.argv=[sys.argv[0],'osm_county.txt']
import geocode_county as G
from mask import mask_address

os.makedirs(OUT+'/data/city',exist_ok=True); os.makedirs(OUT+'/data/inc',exist_ok=True)
rows=json.load(open('build/incidents_geocoded.json'))
YEARS=['2022','2023','2024','2025','2026']
PCODES=['block','block~','intersection','intersection~','grid','street','area']
SKIP={'SAINT PAUL','UNKNOWN'}

def title(n):
    small={'ON','OF'}
    return ' '.join(w.lower() if w in small else w.capitalize() for w in n.split())
def slug(n): return re.sub(r'[^a-z0-9]+','-',n.lower()).strip('-')
def area_km2(ring):
    a=0
    for i in range(len(ring)):
        y1,x1=ring[i]; y2,x2=ring[(i+1)%len(ring)]
        a+=(x1*G.M_PER_DEG_LON)*(y2*G.M_PER_DEG_LAT)-(x2*G.M_PER_DEG_LON)*(y1*G.M_PER_DEG_LAT)
    return abs(a)/2/1e6
def centroid(ring):
    a=0;cx=0;cy=0
    for i in range(len(ring)):
        y1,x1=ring[i]; y2,x2=ring[(i+1)%len(ring)]
        f=x1*y2-x2*y1; a+=f; cx+=(x1+x2)*f; cy+=(y1+y2)*f
    if abs(a)<1e-12: return ring[0]
    return (cy/(3*a), cx/(3*a))
def dp(pts,eps):
    if len(pts)<3: return pts
    def d(p,a,b):
        if a==b: return math.hypot(p[0]-a[0],p[1]-a[1])
        t=max(0,min(1,((p[0]-a[0])*(b[0]-a[0])+(p[1]-a[1])*(b[1]-a[1]))/((b[0]-a[0])**2+(b[1]-a[1])**2)))
        return math.hypot(p[0]-(a[0]+t*(b[0]-a[0])),p[1]-(a[1]+t*(b[1]-a[1])))
    mi=0;md=0
    for i in range(1,len(pts)-1):
        dd=d(pts[i],pts[0],pts[-1])
        if dd>md: md=dd;mi=i
    if md>eps: return dp(pts[:mi+1],eps)[:-1]+dp(pts[mi:],eps)
    return [pts[0],pts[-1]]
def rnd(pts): return [[round(p[0],5),round(p[1],5)] for p in pts]
SHORT={'North':'N','South':'S','East':'E','West':'W','Street':'St','Avenue':'Ave','Boulevard':'Blvd','Road':'Rd','Drive':'Dr','Trail':'Trl','Lane':'Ln','Parkway':'Pkwy','Court':'Ct','Circle':'Cir','Highway':'Hwy','Place':'Pl','Northeast':'NE','Northwest':'NW','Southeast':'SE','Southwest':'SW'}
def short(n): return ' '.join(SHORT.get(w,w) for w in n.split())
def rank(sub):
    cls=sub.split(';')[0]; return {'motorway':5,'trunk':5,'motorway_link':4,'trunk_link':4,'primary':4,'primary_link':3,'secondary':3,'secondary_link':3,'tertiary':2,'tertiary_link':2}.get(cls,1)

def auto_labels(ci, rings):
    inside=lambda p: any(G.pip(p,r) for r in rings)
    byname=collections.defaultdict(list)
    for r in ci.by_canon.values():
        for w in r:
            if not w['name'] or rank(w['sub'])<2: continue
            byname[w['name']].append(w)
    scored=[]
    for name,ways in byname.items():
        L=0; best=None; bl=0
        for w in ways:
            p=w['pts']; wl=0
            for i in range(len(p)-1):
                if inside(p[i]) or inside(p[i+1]): wl+=G.dist(p[i],p[i+1])
            L+=wl
            if wl>bl: bl=wl; best=w
        if L>800 and best: scored.append((L,name,best))
    scored.sort(reverse=True)
    labels=[]; used=[]
    for L,name,w in scored[:16]:
        p=w['pts']; ins=[q for q in p if inside(q)] or p
        mid=ins[len(ins)//2]; i=p.index(mid); a=p[max(0,i-1)]; b=p[min(len(p)-1,i+1)]
        ang=math.degrees(math.atan2(-(b[0]-a[0])*G.M_PER_DEG_LAT,(b[1]-a[1])*G.M_PER_DEG_LON))
        if ang>90: ang-=180
        if ang<-90: ang+=180
        if any(G.dist(mid,u)<600 for u in used): continue
        used.append(mid); labels.append({'t':short(name),'lat':round(mid[0],5),'lon':round(mid[1],5),'a':round(ang,1),'k':'road'})
    for w in ci.water:
        if not w['name'] or 'Lake' not in w['name'] and 'River' not in w['name'] and 'Pond' not in w['name']: continue
        A=area_km2(w['pts'])
        if A<0.12: continue
        c=centroid(w['pts'])
        if not inside(c) and not ci._near((c[0],c[0],c[1],c[1])): continue
        if any(G.dist(c,u)<400 for u in used): continue
        used.append(c); labels.append({'t':w['name'],'lat':round(c[0],5),'lon':round(c[1],5),'a':0,'k':'water'})
    return labels

def basemap_for(ci, rings, eps_road=0.00004):
    bb=ci.bb
    near=lambda pts: ci._near(G.bbox(pts))
    bm={'roads':[],'water':[],'streams':[],'rail':[],'boundary':[rnd(r) for r in rings]}
    for r in G.roads:
        if near(r['pts']): bm['roads'].append({'n':r['name'],'s':r['sub'],'p':rnd(dp(r['pts'],eps_road))})
    for w in G.water:
        if near(w['pts']): bm['water'].append({'n':w['name'],'p':rnd(dp(w['pts'],0.00006))})
    for s in G.streams:
        if near(s['pts']): bm['streams'].append({'p':rnd(dp(s['pts'],0.00008))})
    for l in G.rail:
        if near(l['pts']): bm['rail'].append({'p':rnd(dp(l['pts'],0.00008))})
    bm['labels']=auto_labels(ci, rings)
    return bm

bycity=collections.defaultdict(list)
for r in rows:
    if r['city'] in SKIP: continue
    bycity[r['city']].append(r)
cities=[]; shapes={}
for name in sorted(bycity):
    ci=G.CityIndex(name)
    rings=ci.polys
    if not rings: print('NO POLYGON', name); continue
    rings=sorted(rings,key=lambda r:-area_km2(r))
    km2=sum(area_km2(r) for r in rings)
    main=rings[0]; c=centroid(main)
    if not G.pip(c,main): c=main[len(main)//2]
    inc=bycity[name]
    by={y:{} for y in YEARS}
    for r in inc: by[r['t'][:4]][str(r['s'])]=by[r['t'][:4]].get(str(r['s']),0)+1
    top=[k for k,v in collections.Counter(r['e'] for r in inc).most_common(3)]
    la=[p[0] for r in rings for p in r]; lo=[p[1] for r in rings for p in r]
    s=slug(name)
    cities.append({'slug':s,'name':title(name),'kind':'township' if 'TOWNSHIP' in name else 'city','n':len(inc),'by':by,'top':top,
                   'km2':round(km2,2),'center':[round(c[0],5),round(c[1],5)],'bbox':[round(min(la),4),round(min(lo),4),round(max(la),4),round(max(lo),4)],
                   'located':sum(1 for r in inc if 'lat' in r)})
    shapes[s]=[rnd(dp(r,0.00015)) for r in rings]
    bm=basemap_for(ci, rings)
    json.dump(bm,open(f'{OUT}/data/city/{s}.json','w'),separators=(',',':'))
    ev=[];evi={};ad=[];adi={};ag=[];agi={}
    def idx(lst,d,v):
        if v not in d: d[v]=len(lst); lst.append(v)
        return d[v]
    out=[]
    for r in sorted(inc,key=lambda r:r['t']):
        out.append([r['c'],int(r['t'][2:4]+r['t'][5:7]+r['t'][8:10]+r['t'][11:13]+r['t'][14:16]),idx(ad,adi,mask_address(r['a'])),idx(ev,evi,r['e']),r['s'],PCODES.index(r['p']) if 'p' in r else None,
                    round(r['lat']*1e5) if 'lat' in r else None, round(r['lon']*1e5) if 'lon' in r else None, idx(ag,agi,title(r['ag']).replace('Sheriffs','Sheriff’s').replace('Dept.','Department'))])
    json.dump({'ev':ev,'ad':ad,'ag':ag,'rows':out},open(f'{OUT}/data/inc/{s}.json','w'),separators=(',',':'))
    print(f"{name:28s} {len(inc):6d} inc  bm roads {len(bm['roads']):5d} labels {len(bm['labels']):2d} km2 {km2:6.1f}  inc {os.path.getsize(f'{OUT}/data/inc/{s}.json')//1024} KB  bm {os.path.getsize(f'{OUT}/data/city/{s}.json')//1024} KB")

# county basemap
cb={'shapes':shapes,'roads':[],'water':[]}
allrings=[r for rs in shapes.values() for r in rs]
def in_county(p): return any(G.pip(p,r) for r in allrings)
for r in G.roads:
    if rank(r['sub'])>=3 and any(in_county(p) for p in r['pts'][::3]): cb['roads'].append({'s':r['sub'],'p':rnd(dp(r['pts'],0.0003))})
for w in G.water:
    b=G.bbox(w['pts'])
    if (b[1]-b[0])>0.006 or (b[3]-b[2])>0.008: cb['water'].append({'p':rnd(dp(w['pts'],0.0003))})
json.dump(cb,open(f'{OUT}/data/county.json','w'),separators=(',',':'))
print('county.json', os.path.getsize(f'{OUT}/data/county.json')//1024,'KB')

dates=sorted(r['t'][:10] for r in rows)
first,last=dates[0],dates[-1]
fmt=lambda d: datetime.date.fromisoformat(d).strftime('%b %-d, %Y')
index={'years':YEARS,'first':first,'last':last,'first_h':fmt(first),'last_h':fmt(last),'cities':cities}
json.dump(index,open(f'{OUT}/data/index.json','w'),separators=(',',':'))
tpl=open('app_template.html').read()
nfiles=len(json.load(open('build/sources.json')))
page=tpl.replace('%(INDEX)s',json.dumps(index,separators=(',',':'))).replace('%(files)s',str(nfiles)).replace('%(first)s',fmt(first)).replace('%(last)s',fmt(last)).replace('%(nlabels)s',f"{len(set(r['e'] for r in rows)):,}")
open(f'{OUT}/index.html','w').write('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'+page.replace('</style>\n<div class="app">','</style>\n</head>\n<body>\n<div class="app">')+'</body>\n</html>\n')
open('build/fragment.html','w').write(page)
print('index.html', os.path.getsize(f'{OUT}/index.html')//1024,'KB; cities', len(cities))
