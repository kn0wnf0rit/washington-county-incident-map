#!/usr/bin/env python3
"""County-wide geocoder: OSM centerlines + OSM address points + Washington County grid, restricted per city."""
import re, json, math, difflib, collections, sys
from mask import block_range, mask_address

# county grid (calibrated on Hugo; refit below from address points if enough data)
LON_A, LON_B = -93.104485, 1.987026e-5
LAT_A, LAT_B = 44.947684, 1.462966e-5
M_PER_DEG_LAT = 111_000.0
M_PER_DEG_LON = 111_000.0 * math.cos(math.radians(45.0))

def decode(s):
    parts = s.split('|'); lat, lon = map(int, parts[0].split(',')); pts=[(lat/1e5, lon/1e5)]
    for p in parts[1:]:
        a,b = map(int,p.split(',')); lat+=a; lon+=b; pts.append((lat/1e5, lon/1e5))
    return pts
def dist(a,b): return math.hypot((a[0]-b[0])*M_PER_DEG_LAT, (a[1]-b[1])*M_PER_DEG_LON)

# ---------- load ----------
roads=[]; water=[]; streams=[]; rail=[]; boundary=[]; addrs=[]
seen=set()
for line in open(sys.argv[1] if len(sys.argv)>1 else 'osm_county.txt', encoding='utf-8'):
    line=line.rstrip('\n')
    if not line or line in seen: continue
    seen.add(line)
    kind, name, sub, geom = line.split('|',3)
    if kind=='A':
        hn=int(sub.split(';')[0]); city=sub.split(';')[1] if ';' in sub else ''
        la,lo=map(int,geom.split(',')); addrs.append({'street':name,'hn':hn,'city':city,'pt':(la/1e5,lo/1e5)})
        continue
    pts = decode(geom)
    rec = {'name':name, 'sub':sub, 'pts':pts}
    {'R':roads,'W':water,'S':streams,'L':rail,'B':boundary}[kind].append(rec)
print(f'roads {len(roads)} water {len(water)} streams {len(streams)} rail {len(rail)} boundary {len(boundary)} addr {len(addrs)}', file=sys.stderr)

# ---------- names ----------
ABBR = {'st':'street','ave':'avenue','av':'avenue','blvd':'boulevard','rd':'road','dr':'drive','ct':'court',
        'cir':'circle','trl':'trail','tr':'trail','ln':'lane','pkwy':'parkway','hwy':'highway','pl':'place',
        'n':'north','s':'south','e':'east','w':'west','ne':'northeast','nw':'northwest','se':'southeast','sw':'southwest',
        'grn':'green','aly':'alley','ter':'terrace','sq':'square','pt':'point','hts':'heights','gln':'glen','cv':'cove',
        'xing':'crossing','byp':'bypass','mt':'mount','mtn':'mountain','ext':'extension','pth':'path','ests':'estates',
        'hl':'hill','hls':'hills','lk':'lake','vw':'view','rdg':'ridge','crk':'creek','run':'run','ctr':'center','cor':'corner',
        'st.':'street','saint':'saint','frontage':'frontage','vlg':'village','plz':'plaza','xrd':'crossroad'}
DIRS={'north','south','east','west','northeast','northwest','southeast','southwest'}
def canon(name):
    s = name.lower().strip()
    s = re.sub(r'\bst\.? (?=(croix|paul|mary|marys|john|joseph|peter|anthony|clair|andrew|charles|james)\b)', 'saint ', s)
    s = re.sub(r'[^a-z0-9 ]+',' ', s)
    toks = [ABBR.get(t,t) for t in s.split()]
    toks = [t for t in toks if t not in ('eb','wb','nb','sb','ramp')] or toks
    while toks and toks[-1] in DIRS and len(toks)>1: toks.pop()
    s = ' '.join(toks)
    # highways -> refs
    m = re.fullmatch(r'(?:(?:us|u s|united states) )?(?:highway |hwy )?(61|8|10|12|212)', s)
    if m: return 'us '+m.group(1)
    m = re.fullmatch(r'(?:i|interstate)\s?(\d+[ew]?)', s)
    if m: return 'i '+m.group(1)
    m = re.fullmatch(r'(?:(?:mn|minnesota|state|trunk|tr) )?(?:highway |hwy |th )(\d+)', s)
    if m: return 'mn '+m.group(1)
    m = re.fullmatch(r'(?:county |co |cty )?(?:road |rd |highway |hwy |state aid highway )?(?:csah |cr |cah )?(\d+)', s)
    if m and ('county' in name.lower() or 'csah' in name.lower() or re.match(r'^\s*(co|cr|cty)\b', name.lower())): return 'cr '+m.group(1)
    return s
def canon_ref(ref):
    r = ref.lower().strip().replace('-', ' ')
    r = re.sub(r'\s+',' ', r)
    r = re.sub(r'^(csah|cah|cty|co) ', 'cr ', r)
    r = re.sub(r'^(mn|tr|th) ', 'mn ', r)
    r = re.sub(r'^(us) ', 'us ', r)
    r = re.sub(r'^(i) ', 'i ', r)
    return r
TYPES = {'street','avenue','boulevard','road','drive','court','circle','trail','lane','parkway','way','bay','alcove','path','green',
         'place','terrace','point','curve','cove','glen','ridge','run','crossing','square','heights','loop','row','walk','pass','hill'}
def base(c): return ' '.join(t for t in c.split() if t not in TYPES)

# ---------- city polygons ----------
def pip(pt, poly):
    x,y=pt[1],pt[0]; inside=False; n=len(poly)
    for i in range(n):
        y1,x1=poly[i]; y2,x2=poly[(i+1)%n]
        if (y1>y)!=(y2>y):
            xi=x1+(y-y1)*(x2-x1)/(y2-y1)
            if xi>x: inside=not inside
    return inside
CITY_ALIAS={'BIRCHWOOD VILLAGE':['BIRCHWOOD VILLAGE','BIRCHWOOD'],'SAINT MARYS POINT':["SAINT MARY'S POINT",'SAINT MARYS POINT','ST. MARY\'S POINT'],
            'MARINE ON SAINT CROIX':['MARINE ON ST. CROIX','MARINE ON SAINT CROIX'],'LAKE SAINT CROIX BEACH':['LAKE ST. CROIX BEACH','LAKE SAINT CROIX BEACH'],
            'SAINT PAUL PARK':['ST. PAUL PARK','SAINT PAUL PARK'],'SAINT PAUL':['ST. PAUL','SAINT PAUL'],'STILLWATER TOWNSHIP':['STILLWATER TOWNSHIP','STILLWATER TWP'],
            'DENMARK TOWNSHIP':['DENMARK TOWNSHIP'],'MAY TOWNSHIP':['MAY TOWNSHIP'],'WEST LAKELAND TOWNSHIP':['WEST LAKELAND TOWNSHIP'],
            'BAYTOWN TOWNSHIP':['BAYTOWN TOWNSHIP'],'GREY CLOUD ISLAND TOWNSHIP':['GREY CLOUD ISLAND TOWNSHIP']}
def norm_city(n):
    n=n.upper().replace('ST. ','SAINT ').replace("MARY'S","MARYS").replace(' TWP',' TOWNSHIP').strip()
    return n
polys=collections.defaultdict(list)
for b in boundary:
    polys[norm_city(b['name'])].append(b['pts'])
def city_polys(city):
    for k in [city]+CITY_ALIAS.get(city,[]):
        if norm_city(k) in polys: return polys[norm_city(k)]
    return []

# bounding boxes for quick tests
def bbox(pts):
    return min(p[0] for p in pts),max(p[0] for p in pts),min(p[1] for p in pts),max(p[1] for p in pts)
for r in roads: r['bb']=bbox(r['pts'])

BUF=0.012  # ~1 km
TOWN_GRID={'STILLWATER','BAYPORT','MAHTOMEDI','WILLERNIE','NEWPORT','SAINT PAUL PARK','FOREST LAKE','LAKELAND','LANDFALL','MARINE ON SAINT CROIX',
           'BIRCHWOOD VILLAGE','LAKE SAINT CROIX BEACH','SAINT MARYS POINT','LAKELAND SHORES','DELLWOOD','SAINT PAUL','PINE SPRINGS'}
class CityIndex:
    def __init__(self, city):
        self.city=city
        ps=city_polys(city); self.polys=ps
        if ps:
            bbs=[bbox(p) for p in ps]
            self.bb=(min(b[0] for b in bbs)-BUF,max(b[1] for b in bbs)+BUF,min(b[2] for b in bbs)-BUF,max(b[3] for b in bbs)+BUF)
        else:
            self.bb=None
        self.by_canon=collections.defaultdict(list); self.by_ref=collections.defaultdict(list)
        for r in roads:
            if not self._near(r['bb']): continue
            if r['name']: self.by_canon[canon(r['name'])].append(r)
            sub=r['sub'].split(';')
            for ref in sub[1:]:
                if ref: self.by_ref[canon_ref(ref)].append(r)
        for k,v in self.by_ref.items():
            if k not in self.by_canon: self.by_canon[k]=v
        self.names=list(self.by_canon.keys())
        self.by_base=collections.defaultdict(list)
        for c in self.names: self.by_base[base(c)].append(c)
        self.addr=collections.defaultdict(list)
        for a in addrs:
            if self.bb and (self.bb[0]<=a['pt'][0]<=self.bb[1] and self.bb[2]<=a['pt'][1]<=self.bb[3]):
                self.addr[canon(a['street'])].append(a)
        self.water=[w for w in water if w['name'] and self._near(bbox(w['pts']))]
        self.cache={}
        # per-city grid offset (degrees) from OSM address points on numbered N/S streets inside the polygon
        el=[]; ea=[]
        for a in addrs:
            if not (self.bb and self.bb[0]<=a['pt'][0]<=self.bb[1] and self.bb[2]<=a['pt'][1]<=self.bb[3]): continue
            c=canon(a['street']); m=re.match(r'^(upper |lower )?(\d+)(st|nd|rd|th) (street|avenue|lane|court|circle|place|trail|way)$',c)
            if not m or not self.inside(a['pt']): continue
            k=int(m.group(2))*100+(50 if m.group(1) else 0); sl=a['street'].lower()
            south=re.search(r'\b(south|s)\b',sl) is not None; north=re.search(r'\b(north|n)\b',sl) is not None
            if not (south or north): continue
            ks=-k if south else k
            dlon=a['pt'][1]-(LON_A+LON_B*a['hn']); dlat=a['pt'][0]-(LAT_A+LAT_B*ks)
            if abs(dlon)*M_PER_DEG_LON<900 and abs(dlat)*M_PER_DEG_LAT<900: el.append(dlon); ea.append(dlat)
        if len(el)>=8:
            el.sort(); ea.sort(); self.off=(ea[len(ea)//2], el[len(el)//2]); self.off_n=len(el)
        else:
            self.off=(0.0,0.0); self.off_n=0
    def _near(self, bb):
        if not self.bb: return True
        return not (bb[1]<self.bb[0] or bb[0]>self.bb[1] or bb[3]<self.bb[2] or bb[2]>self.bb[3])
    def inside(self, pt):
        if not self.polys: return True
        return any(pip(pt,p) for p in self.polys)
    def near_poly(self, pt, m=500):
        if not self.polys: return True
        if self.inside(pt): return True
        for p in self.polys:
            for i in range(len(p)):
                if seg_point_dist(pt,p[i],p[(i+1)%len(p)])[0]<=m: return True
        return False
    def size(self,c): return sum(len(r['pts']) for r in self.by_canon[c])
    def resolve(self, raw):
        c = canon(raw)
        if not c: return None
        if c in self.by_canon: return c
        # directional variants: "Frontage Rd W" -> "west frontage road"; "West Broadway Ave" -> "broadway avenue"
        rl=raw.lower().strip()
        md=re.search(r'\b(n|s|e|w|north|south|east|west)\.?\s*$', rl)
        dirs=[ABBR.get(md.group(1),md.group(1))] if md else ['north','south','east','west']
        for d in dirs:
            if d+' '+c in self.by_canon: return d+' '+c
        mt=re.match(r'^(north|south|east|west) (.+)$', c)
        if mt and len(c.split())>=3 and mt.group(2) in self.by_canon: return mt.group(2)
        m = re.fullmatch(r'(\d+)(st|nd|rd|th)', c)
        if m and c+' street' in self.by_canon: return c+' street'
        if c.startswith('us 61'):
            for alt in ('forest boulevard','hastings avenue','east point douglas road','point douglas road'):
                if alt in self.by_canon: return alt
        pref = [x for x in self.names if c.startswith(x+' ') and len(x)>3]
        if pref: return max(pref, key=len)
        b = base(c)
        cands = self.by_base.get(b, [])
        if cands and b:
            typ = [t for t in c.split() if t in TYPES]
            same = [x for x in cands if typ and typ[-1] in x.split()]
            pool = same or cands
            return max(pool, key=self.size)
        num = re.search(r'\d+', c)
        def same_num(x):
            m2 = re.search(r'\d+', x)
            return (m2.group() if m2 else None) == (num.group() if num else None)
        close = [x for x in difflib.get_close_matches(c, self.names, n=3, cutoff=0.87) if same_num(x)]
        if close: return close[0]
        if b:
            close = [x for x in difflib.get_close_matches(b, list(self.by_base.keys()), n=3, cutoff=0.87) if same_num(x)]
            if close: return max(self.by_base[close[0]], key=self.size)
        return None
    # geometry
    def segs(self,c):
        for r in self.by_canon[c]:
            p=r['pts']
            for i in range(len(p)-1): yield p[i],p[i+1]
    def verts(self,c): return [q for r in self.by_canon[c] for q in r['pts']]
    def extent(self,c):
        v=self.verts(c); return min(q[0] for q in v),max(q[0] for q in v),min(q[1] for q in v),max(q[1] for q in v)
    def midpoint(self,c):
        # prefer ways inside the city polygon
        ways=[r for r in self.by_canon[c] if any(self.inside(p) for p in r['pts'][::max(1,len(r['pts'])//4)])] or self.by_canon[c]
        best=None; bl=-1
        for r in ways:
            L=sum(dist(r['pts'][i],r['pts'][i+1]) for i in range(len(r['pts'])-1))
            if L>bl: bl=L; best=r
        p=best['pts']; half=bl/2; acc=0
        for i in range(len(p)-1):
            d=dist(p[i],p[i+1])
            if acc+d>=half:
                t=(half-acc)/d if d else 0
                return (p[i][0]+(p[i+1][0]-p[i][0])*t, p[i][1]+(p[i+1][1]-p[i][1])*t)
        return p[-1]
    def place_target(self, c, idx, target):
        """Point on street c where coordinate idx equals target. Returns (pt, offset_m) or None."""
        hits=[]
        for a,b in self.segs(c):
            lo,hi=sorted((a[idx],b[idx]))
            if lo<=target<=hi and hi>lo:
                t=(target-a[idx])/(b[idx]-a[idx]); hits.append((a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t))
        if hits:
            lat=sum(h[0] for h in hits)/len(hits); lon=sum(h[1] for h in hits)/len(hits)
            if max(dist(h,(lat,lon)) for h in hits) > 250: lat,lon=hits[0]
            return (lat,lon),0.0
        verts=self.verts(c)
        below=[v for v in verts if v[idx]<=target]; above=[v for v in verts if v[idx]>=target]
        if below and above:
            a=max(below,key=lambda v:v[idx]); b=min(above,key=lambda v:v[idx])
            if dist(a,b)<=1300:
                t=(target-a[idx])/(b[idx]-a[idx]) if b[idx]!=a[idx] else 0.5
                return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t), 1.0
        q=min(verts,key=lambda v:abs(v[idx]-target))
        off=abs(q[idx]-target)*(M_PER_DEG_LAT if idx==0 else M_PER_DEG_LON)
        return (q[0],q[1]), off
    def ref_union(self, c):
        refs=set()
        for r in self.by_canon.get(c,[]):
            for ref in r['sub'].split(';')[1:]:
                if ref: refs.add(canon_ref(ref))
        if not refs: return None
        key=c+'+'+'/'.join(sorted(refs))
        if key not in self.by_canon:
            ways={id(w):w for w in self.by_canon[c]}
            for ref in refs:
                for w in self.by_ref.get(ref,[]): ways[id(w)]=w
            self.by_canon[key]=list(ways.values())
        return key
    def base_union(self, c):
        b=base(c)
        if not b or len(b)<4 or re.search(r'\d',b): return None
        names=[x for x in self.by_base.get(b,[]) if x!=c and '+' not in x]
        if not names: return None
        key=c+'+base'
        if key not in self.by_canon:
            ways={id(w):w for w in self.by_canon[c]}
            for x in names:
                for w in self.by_canon[x]: ways[id(w)]=w
            self.by_canon[key]=list(ways.values())
        return key
    def grid_range(self, c, lo, hi, sfx, numbered):
        """Place a house-number range on street c using the county grid. Returns (pt, prec) or None."""
        mnla,mxla,mnlo,mxlo=self.extent(c)
        best=None
        oa,ol=self.off
        interps=[('ew',1,LON_A+ol+LON_B*lo,LON_A+ol+LON_B*hi,mnlo,mxlo)]
        if not numbered:
            if sfx!='S': interps.append(('n',0,LAT_A+oa+LAT_B*lo,LAT_A+oa+LAT_B*hi,mnla,mxla))
            if sfx!='N': interps.append(('s',0,LAT_A+oa-LAT_B*hi,LAT_A+oa-LAT_B*lo,mnla,mxla))
        for kind,idx,t0,t1,e0,e1 in interps:
            o0,o1=max(t0,e0),min(t1,e1)
            scale=M_PER_DEG_LAT if idx==0 else M_PER_DEG_LON
            if o0<=o1:
                pt,off=self.place_target(c,idx,(o0+o1)/2)
                if pt and off<=60:
                    cand=(0,pt,'block')
                    if best is None or cand[0]<best[0]: best=cand
                continue
            gap=(e0-t1 if t1<e0 else t0-e1)*scale
            if gap<=350:
                target=e0 if t1<e0 else e1
                pt,off=self.place_target(c,idx,target)
                if pt:
                    cand=(gap,pt,'block~')
                    if best is None or cand[0]<best[0]: best=cand
        return (best[1],best[2]) if best else None
    def grid_candidates(self, c, n, sfx):
        """All grid interpretations of house number n on street c: list of (pt, off_m, kind)."""
        out=[]
        # E-W street: n -> longitude
        out.append(self.place_target(c,1,LON_A+LON_B*n)+('ew',))
        # N-S street: n -> latitude (north or south of baseline)
        if sfx!='S': out.append(self.place_target(c,0,LAT_A+LAT_B*n)+('n',))
        if sfx!='N': out.append(self.place_target(c,0,LAT_A-LAT_B*n)+('s',))
        return out
    def intersection(self,c1,c2):
        pts=[]; S2=list(self.segs(c2))
        for a,b in self.segs(c1):
            for cc,d in S2:
                x=seg_intersect(a,b,cc,d)
                if x: pts.append(x)
        if pts:
            ins=[p for p in pts if self.inside(p)] or pts
            lat=sum(p[0] for p in ins)/len(ins); lon=sum(p[1] for p in ins)/len(ins)
            if max(dist(p,(lat,lon)) for p in ins)>400: lat,lon=ins[0]
            return lat,lon,'intersection'
        best=(1e9,None)
        V1=self.verts(c1); V2=self.verts(c2); S1=list(self.segs(c1))
        for v in V1:
            for cc,d in S2:
                dd,q=seg_point_dist(v,cc,d)
                if dd<best[0]: best=(dd,((v[0]+q[0])/2,(v[1]+q[1])/2))
        for v in V2:
            for a,b in S1:
                dd,q=seg_point_dist(v,a,b)
                if dd<best[0]: best=(dd,((v[0]+q[0])/2,(v[1]+q[1])/2))
        if best[0]<=200: return best[1][0],best[1][1],'intersection~'
        return None

def seg_intersect(p1,p2,p3,p4):
    d=(p2[0]-p1[0])*(p4[1]-p3[1])-(p2[1]-p1[1])*(p4[0]-p3[0])
    if abs(d)<1e-14: return None
    t=((p3[0]-p1[0])*(p4[1]-p3[1])-(p3[1]-p1[1])*(p4[0]-p3[0]))/d
    u=((p3[0]-p1[0])*(p2[1]-p1[1])-(p3[1]-p1[1])*(p2[0]-p1[0]))/d
    if 0<=t<=1 and 0<=u<=1: return (p1[0]+t*(p2[0]-p1[0]), p1[1]+t*(p2[1]-p1[1]))
    return None
def seg_point_dist(p,a,b):
    ax,ay=a[1]*M_PER_DEG_LON,a[0]*M_PER_DEG_LAT; bx,by=b[1]*M_PER_DEG_LON,b[0]*M_PER_DEG_LAT
    px,py=p[1]*M_PER_DEG_LON,p[0]*M_PER_DEG_LAT; dx,dy=bx-ax,by-ay
    if dx==dy==0: return math.hypot(px-ax,py-ay),a
    t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
    qx,qy=ax+t*dx,ay+t*dy
    return math.hypot(px-qx,py-qy),(qy/M_PER_DEG_LAT,qx/M_PER_DEG_LON)

# ---------- parsing ----------
SEP = re.compile(r'\s*(?:/|&|@|\bAT\b|\bJSO\b|\bJNO\b|\bJWO\b|\bJEO\b|\bOVER\b|\bTO\b|\bAND\b|\bUNDER\b)\s*', re.I)
BLOCK = re.compile(r'^\s*(\d*)\s*(X{2,3})?\s*(?:-\s*(\d{2,5})\s*)?(?:-?\s*(?:BLOCK|BLK)\s*(?:OF\s*)?)?(.*?)\s*$', re.I)
NOISE = re.compile(r'\b(EB|WB|NB|SB|RAMP|EXIT|ENTRANCE|MM|MILE MARKER|BRIDGE)\b', re.I)

PLACES = {'WAKOTA BRIDGE: I494 EB - WASHINGTON':'I494 / HWY 61','WAKOTA BRIDGE: I494 WB - WASHINGTON':'I494 / HWY 61','WAKOTA BRIDGE':'I494 / HWY 61',
          'TANNERS LAKE BOAT LANDING':'Tanners Lake','TANNERS LAKE PARK':'Tanners Lake','LIONS LEVEE PARK BOAT LANDING':'Lions Levee Park'}
PLACE_COORDS = {'STILLWATER LIFT BRIDGE':(45.0567,-92.8037),'BOOM SITE':(45.0800,-92.7950),'ARCOLA BRIDGE':(45.1300,-92.7560),
    'I94 BRIDGE (HUDSON)':(44.9756,-92.7640),'I94 BRIDGE':(44.9756,-92.7640),'HWY 10 BRIDGE (PRESCOTT)':(44.7510,-92.8050),'HWY 10 BRIDGE':(44.7510,-92.8050),
    'SWING BRIDGE':(44.9820,-92.7610),'POINT DOUGLAS PARK':(44.7515,-92.7990),'BIG MARINE PARK':(45.2000,-92.8860),'BIG MARINE LAKE COUNTY PARK':(45.2000,-92.8860),
    'SQUARE LAKE BOAT LANDING':(45.1560,-92.8040),'SQUARE LAKE PARK':(45.1560,-92.8040),'COTTAGE GROVE RAVINE PARK':(44.8455,-92.9180),'GATEWAY TRAIL':(45.0600,-92.9300),
    'SAINT CROIX SCENIC OVERLOOK':(45.0830,-92.7930),'TARTAN HIGH SCHOOL':(44.9880,-92.9590),'LIONS LEVEE PARK':(44.8410,-92.9930),
    'LAKESIDE PARK':(45.0170,-92.7750),'BEACH AT LAKE ST CROIX BEACH PARK':(44.9200,-92.7680),'LAKE ST CROIX BEACH STAIRS':(44.9200,-92.7680),'SUNSET PARK BEACH':(44.9070,-92.7620),
    'AFTON STATE PARK':(44.8500,-92.7800),'WAKOTA BRIDGE':(44.8880,-93.0240)}
def numbered_street(street_raw):
    m = re.match(r'^\s*(upper |lower )?(\d+)(st|nd|rd|th)\b\s*(street|avenue)?\s*(north|south)?', canon(street_raw)+' ')
    if not m: return None
    return int(m.group(2))*100 + (50 if m.group(1) else 0), (m.group(5) or '')

def geocode(ci, addr):
    key=addr
    if key in ci.cache: return ci.cache[key]
    r=_geocode(ci, addr); ci.cache[key]=r; return r

def _geocode(ci, addr):
    a = addr.strip()
    a = re.sub(r'\(.*?\)', '', a).strip()
    if not a or re.search(r'unknown', a, re.I): return None,'none',''
    au = re.sub(r'\s+',' ', re.sub(r'^\s*(?:\d*X{2,3}|\d+)\s+','', a.upper())).strip()
    for k,v in PLACE_COORDS.items():
        if au.startswith(k): return v,'area',k.title()
    a = PLACES.get(au, a)
    a = re.sub(r',\s*[A-Za-z .\']+$', '', a)   # trailing ", City"
    a = re.sub(r'(River|Lake|Beach|Landing|Park)\s*(-|\()\s*[a-z]{1,3}\)?\s*$', r'\1', a, flags=re.I)
    sfx = 'N' if re.search(r'\b(N|NORTH)\s*$', a, re.I) else ('S' if re.search(r'\b(S|SOUTH)\s*$', a, re.I) else '')
    parts = [p for p in SEP.split(a) if p.strip()]
    if len(parts) >= 2:
        parts=[NOISE.sub(' ',p).strip() for p in parts]
        parts=[p for p in parts if p and not re.fullmatch(r'[\dX]+\s*',p)]
        names=[ci.resolve(re.sub(r'^\s*(?:\d*X{2,3}|\d+)\s+','',p)) for p in parts]
        names=[n for n in names if n]
        for i in range(len(names)):
            for j in range(i+1,len(names)):
                if names[i]!=names[j]:
                    r=ci.intersection(names[i],names[j])
                    if r and ci.near_poly((r[0],r[1]),1500): return (r[0],r[1]), r[2], f'{names[i]} & {names[j]}'
        if names:
            m=ci.midpoint(names[0]); return m,'street',names[0]
        return None,'none',''
    a = NOISE.sub(' ', a).strip()
    m = BLOCK.match(a)
    if m and not m.group(2) and not m.group(3) and re.match(r'^\d{1,5}\s+(?![Xx-])\S', a):
        a = re.sub(r'^(\d+)\s+', r'0XXX -\1 ', a); m = BLOCK.match(a)
    if m and (m.group(2) or m.group(3) or re.match(r'^\d{3,5}\s*(BLOCK|BLK)', a, re.I)):
        prefix=m.group(1); xs=m.group(2) or ''; exact=m.group(3); street=m.group(4)
        c = ci.resolve(street)
        if exact:
            lo,hi=block_range(int(exact)); n=(lo+hi)/2; tag='block'   # never place an exact house number; use its block
        elif prefix:
            p=int(prefix); k=len(xs)
            lo=p*10**k; hi=lo+10**k-1; n=(lo+hi)/2; tag='block'
        else:
            lo,hi=(10 if len(xs)==2 else 100),(99 if len(xs)==2 else 999); n=None; tag='xxx'
        # 1) OSM address points on this street within the city
        ap=ci.addr.get(c or canon(street),[])
        if ap:
            inblk=[x for x in ap if lo<=x['hn']<=hi]
            if inblk:
                lat=sum(x['pt'][0] for x in inblk)/len(inblk); lon=sum(x['pt'][1] for x in inblk)/len(inblk)
                if max(dist(x['pt'],(lat,lon)) for x in inblk)<=600:
                    return (lat,lon),('block' if tag!='xxx' else 'block~'),(c or canon(street))
            if n is not None:
                near=min(ap,key=lambda x:abs(x['hn']-n))
                if abs(near['hn']-n)<=250: return near['pt'],'block~',(c or canon(street))
        # 2) county grid on resolved street (range overlap, both orientations)
        ns=numbered_street(street)
        town = ci.city in TOWN_GRID
        allow_grid = (not town) or (lo>=10000) or (ns is not None and ns[1] and lo>=1000)
        if c and allow_grid:
            for key in (c, ci.ref_union(c), ci.base_union(c)):
                if not key: continue
                r=ci.grid_range(key, lo, hi, sfx, ns is not None)
                if r:
                    pt,prec=r
                    if ci.near_poly(pt):
                        return pt,('block~' if (tag=='xxx' or key!=c) and prec=='block' else prec),c
        # 3) pure grid for numbered streets
        if ns and n is not None and n<11000 and not town:
            k,d=ns; d=d or sfx.lower()
            lat=LAT_A+ci.off[0]+(LAT_B*k if d!='south' and d!='s' else -LAT_B*k); lon=LON_A+ci.off[1]+LON_B*n
            if ci.near_poly((lat,lon)): return (lat,lon),'grid',canon(street)
        # 4) street midpoint
        if c:
            mp=ci.midpoint(c); return mp,'street',c
        return None,'none',''
    c = ci.resolve(a)
    if c:
        mp=ci.midpoint(c); return mp,'street',c
    # lake / named water
    ca=canon(re.sub(r'\b(boat landing|landing|county park|park|beach|north|south|east|west|public access|access)\b',' ',a,flags=re.I))
    ca=re.sub(r'\s+',' ',ca).strip()
    for w in ci.water:
        if canon(w['name'])==ca or (ca and ca in canon(w['name'])):
            pts=w['pts']; lat=sum(p[0] for p in pts)/len(pts); lon=sum(p[1] for p in pts)/len(pts)
            return (lat,lon),'area',canon(w['name'])
    mm = re.match(r'^(.+?\b(?:N|NORTH|S|SOUTH))\s+(.+)$', a, re.I)
    if mm:
        n1,n2=ci.resolve(mm.group(1)),ci.resolve(mm.group(2))
        if n1 and n2 and n1!=n2:
            r=ci.intersection(n1,n2)
            if r: return (r[0],r[1]), r[2], f'{n1} & {n2}'
    return None,'none',''

if __name__=='__main__':
    import random
    rows=json.load(open('build/incidents_all.json'))
    bycity=collections.defaultdict(list)
    for r in rows: bycity[r['city']].append(r)
    out=[]; report={}
    JIT={'block':40,'block~':40,'intersection':18,'intersection~':25,'street':60,'grid':60,'area':120}
    for city in sorted(bycity):
        ci=CityIndex(city)
        precs=collections.Counter(); unres=collections.Counter()
        for r in bycity[city]:
            pt,prec,street=geocode(ci,r['a'])
            precs[prec]+=1
            if pt is None: unres[r['a']]+=1; continue
            rnd=random.Random(r['c'] or r['a']); jr=JIT.get(prec,50)
            ang=rnd.random()*2*math.pi; rad=jr*math.sqrt(rnd.random())
            lat=pt[0]+rad*math.cos(ang)/M_PER_DEG_LAT; lon=pt[1]+rad*math.sin(ang)/M_PER_DEG_LON
            r['p']=prec; r['lat']=round(lat,5); r['lon']=round(lon,5); r['st']=street
        n=len(bycity[city]); ok=n-precs['none']
        report[city]={'n':n,'located':ok,'prec':dict(precs),'top_unresolved':unres.most_common(12),'polys':len(ci.polys),'roads':len(ci.names),'addr':sum(len(v) for v in ci.addr.values()),'grid_off_m':[round(ci.off[0]*M_PER_DEG_LAT),round(ci.off[1]*M_PER_DEG_LON)],'grid_off_n':ci.off_n}
        print(f"{city:28s} n={n:6d} located={ok/n*100:5.1f}%  {dict(precs)}", file=sys.stderr)
    json.dump(report,open('build/geocode_report.json','w'),indent=1)
    json.dump(rows,open('build/incidents_geocoded.json','w'))
