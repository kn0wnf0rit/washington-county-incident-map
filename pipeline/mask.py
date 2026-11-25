import re
def block_of(n):
    if n >= 1000: return f'{n//1000}XXX'
    if n >= 100: return 'XXX'
    return 'XX'
def mask_address(a):
    """Reduce any exact house number the county left in the log to the block form it normally publishes."""
    s = re.sub(r'\s+', ' ', a.strip())
    m = re.match(r'^(\d*)(X{2,3})\s*-\s*(\d{1,5})\s*(.*)$', s, re.I)
    if m:
        return (m.group(1)+m.group(2).upper() + ' ' + m.group(4)).strip()
    m = re.match(r'^(\d{1,5})\s+(?![Xx-])(\S.*)$', s)
    if m and not re.match(r'^(BLOCK|BLK)\b', m.group(2), re.I) and not re.match(r'^0\s', s):
        return block_of(int(m.group(1))) + ' ' + m.group(2)
    s = re.sub(r'\b(P\.?O\.? BOX)\s*\d+', r'\1', s, flags=re.I)
    return s
def block_range(n):
    if n >= 1000: return (n//1000)*1000, (n//1000)*1000+999
    if n >= 100: return (n//100)*100, (n//100)*100+99
    return 10, 99
