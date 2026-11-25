#!/usr/bin/env python3
"""Download every weekly IncidentSummary_YYYYMMDD.csv from the Washington County media-report directory into raw/."""
import re, os, sys, time, urllib.request
BASE = 'https://web1.co.washington.mn.us/MediaReports/RMS/'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; washington-county-incident-map; +https://github.com/kn0wnf0rit/washington-county-incident-map)'}
def get(url, tries=4):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            last = e; time.sleep(5 * (i + 1))
    raise SystemExit(f'failed to fetch {url}: {last}')
os.makedirs('raw', exist_ok=True)
listing = get(BASE).decode('utf-8', 'replace')
names = sorted(set(re.findall(r'IncidentSummary_\d{8}\.csv', listing)))
if not names: raise SystemExit('directory listing contained no IncidentSummary files — site layout changed?')
since = sys.argv[1] if len(sys.argv) > 1 else '00000000'   # optional YYYYMMDD: only fetch files on/after this date
got = 0
for n in names:
    if n[16:24] < since: continue
    dest = os.path.join('raw', n)
    if os.path.exists(dest) and os.path.getsize(dest) > 0: continue
    data = get(BASE + n)
    open(dest, 'wb').write(data); got += 1
    time.sleep(0.3)
print(f'{len(names)} weekly files listed, {got} downloaded, newest {names[-1]}')
