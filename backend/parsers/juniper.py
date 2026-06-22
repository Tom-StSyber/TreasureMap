"""TreasureMap -- Juniper JunOS config parser (set and hierarchical)."""
from __future__ import annotations
import re, logging
from typing import Optional
log = logging.getLogger(__name__)

def _cidr(s):
    s = s.rstrip(';').strip()
    if '/' in s:
        ip, pl = s.split('/', 1)
        try: return ip.strip(), int(pl.strip())
        except: return ip.strip(), None
    return s, None

def _iface_new(name):
    return {'name':name,'description':None,'ip_address':None,'prefix_length':None,
            'mac_address':None,'admin_status':'up','oper_status':'up','vlan_mode':'none',
            'vlan_id':None,'trunk_vlans':[],'native_vlan':None,'acl_in':None,
            'acl_out':None,'firewall_policy':None,'speed_mbps':None,'duplex':None}

def _ensure(ifaces, name):
    if name not in ifaces: ifaces[name] = _iface_new(name)

def _acl_new(name):
    return {'name':name,'acl_type':'named','rules':[]}

def _acl_upsert(acl, term, field, value):
    for r in acl['rules']:
        if r.get('description') == term:
            r[field] = value; return
    seq = len(acl['rules'])*10+10
    r = {'sequence':seq,'action':'permit','protocol':'ip','src_network':'any','dst_network':'any','description':term}
    r[field] = value
    acl['rules'].append(r)

def _mgmt_ip(ifaces):
    for n,i in ifaces.items():
        if re.match(r'lo0?',n,re.I) and i.get('ip_address'): return i['ip_address']
    for n,i in ifaces.items():
        if re.match(r'(fxp0|me0|em0|mgmt)',n,re.I) and i.get('ip_address'): return i['ip_address']
    for i in ifaces.values():
        if i.get('ip_address') and i['ip_address'] != '0.0.0.0': return i['ip_address']
    return None

def _dtype(hostname, ifaces):
    h = hostname.lower()
    if any(k in h for k in ('fw','srx','firewall')): return 'firewall'
    if any(k in h for k in ('sw','switch','ex','qfx')): return 'switch'
    if any(k in h for k in ('router','mx','pe','core','edge','border','gw')): return 'router'
    return 'router' if sum(1 for i in ifaces.values() if i.get('ip_address')) >= 2 else 'switch'

def _detect_format(raw):
    return 'set' if sum(1 for l in raw.splitlines() if l.strip().startswith('set ')) > 5 else 'hierarchical'

# --- Set format ---
def _parse_set(raw, hostname):
    ifaces, acls = {}, {}
    m = re.search(r'set system host-name\s+(\S+)', raw)
    if m and hostname == 'unknown': hostname = m.group(1)
    model = 'JunOS Device'
    m = re.search(r'#\s*Model:\s*(\S+)', raw, re.I)
    if m: model = m.group(1)
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r'set interfaces (\S+) description [\'"]?(.+?)[\'"]?\s*$', line)
        if m:
            n,d = m.group(1),m.group(2); _ensure(ifaces,n); ifaces[n]['description']=d; continue
        m = re.match(r'set interfaces (\S+) disable\s*$', line)
        if m:
            n=m.group(1); _ensure(ifaces,n); ifaces[n]['admin_status']='disabled'; continue
        m = re.match(r'set interfaces (\S+) unit (\d+) family inet address (\S+)', line)
        if m:
            b,u,a = m.group(1),m.group(2),m.group(3).rstrip(';')
            k = f'{b}.{u}' if u!='0' else b; _ensure(ifaces,k)
            ip,pl = _cidr(a); ifaces[k]['ip_address']=ip
            if pl: ifaces[k]['prefix_length']=pl
            ifaces[k]['vlan_mode']='routed'; continue
        m = re.match(r'set interfaces (\S+) unit (\d+) family ethernet-switching vlan members (\S+)', line)
        if m:
            b,u,v = m.group(1),m.group(2),m.group(3).rstrip(';')
            k = f'{b}.{u}' if u!='0' else b; _ensure(ifaces,k)
            try:
                vid = int(v)
                if ifaces[k]['vlan_mode'] == 'trunk':
                    if vid not in ifaces[k]['trunk_vlans']:
                        ifaces[k]['trunk_vlans'].append(vid)
                else:
                    ifaces[k]['vlan_id'] = vid
                    ifaces[k]['vlan_mode'] = 'access'
            except: pass
            continue
        m = re.match(r'set interfaces (\S+) unit (\d+) family ethernet-switching interface-mode trunk', line)
        if m:
            b,u = m.group(1),m.group(2); k=f'{b}.{u}' if u!='0' else b
            _ensure(ifaces,k); ifaces[k]['vlan_mode']='trunk'; continue
        m = re.match(r'set interfaces (\S+) unit (\d+) family inet filter (input|output) (\S+)', line)
        if m:
            b,u,d,f = m.groups(); f=f.rstrip(';'); k=f'{b}.{u}' if u!='0' else b
            _ensure(ifaces,k)
            if d=='input': ifaces[k]['acl_in']=f
            else: ifaces[k]['acl_out']=f
            ifaces[k]['firewall_policy']=f; continue
        m = re.match(r'set firewall family inet filter (\S+) term (\S+) then (accept|reject|discard)', line)
        if m:
            fn,tn,ac = m.groups()
            if fn not in acls: acls[fn]=_acl_new(fn)
            acls[fn]['rules'].append({'sequence':len(acls[fn]['rules'])*10+10,
                'action':'permit' if ac=='accept' else 'deny','protocol':'ip',
                'src_network':'any','dst_network':'any','description':tn}); continue
        m = re.match(r'set firewall family inet filter (\S+) term (\S+) from source-address (\S+)', line)
        if m:
            fn,tn,src = m.groups()
            if fn not in acls: acls[fn]=_acl_new(fn)
            _acl_upsert(acls[fn],tn,'src_network',src.rstrip(';')); continue
        m = re.match(r'set firewall family inet filter (\S+) term (\S+) from destination-address (\S+)', line)
        if m:
            fn,tn,dst = m.groups()
            if fn not in acls: acls[fn]=_acl_new(fn)
            _acl_upsert(acls[fn],tn,'dst_network',dst.rstrip(';')); continue
        m = re.match(r'set firewall family inet filter (\S+) term (\S+) from protocol (\S+)', line)
        if m:
            fn,tn,pr = m.groups()
            if fn not in acls: acls[fn]=_acl_new(fn)
            _acl_upsert(acls[fn],tn,'protocol',pr.rstrip(';')); continue
    mgmt = _mgmt_ip(ifaces)
    return {'device':{'name':hostname,'hostname':hostname,'vendor':'Juniper','model':model,
            'os':'JunOS','management_ip':mgmt or '0.0.0.0','device_type':_dtype(hostname,ifaces),
            'tags':['junos','parsed']},
            'interfaces':list(ifaces.values()),'acls':list(acls.values())}

# --- Hierarchical format ---
def _seg_val(path, kw):
    """Find path segment starting with kw; return remainder or '' or None."""
    for seg in path:
        if seg == kw: return ''
        if seg.startswith(kw + ' '): return seg[len(kw)+1:].strip()
    return None

def _hier_leaf(line, path, ifaces, acls):
    line = line.rstrip(';').strip()
    if not line: return

    if path and path[0] == 'interfaces' and len(path) >= 2:
        base = path[1]
        uv = _seg_val(path, 'unit')
        key = (f'{base}.{uv}' if uv and uv != '0' else base)
        _ensure(ifaces, key)
        m = re.match(r'description\s+"?(.+?)"?\s*$', line)
        if m: ifaces[key]['description'] = m.group(1).strip('"'); return
        if line == 'disable': ifaces[key]['admin_status'] = 'disabled'; return
        m = re.match(r'address\s+(\S+)$', line)
        if m:
            if _seg_val(path,'family inet') is not None:
                ip,pl = _cidr(m.group(1)); ifaces[key]['ip_address']=ip
                if pl: ifaces[key]['prefix_length']=pl
                ifaces[key]['vlan_mode']='routed'
            elif _seg_val(path,'family inet6') is not None:
                if not ifaces[key].get('ip_address'):
                    ip,pl = _cidr(m.group(1)); ifaces[key]['ip_address']=ip
                    if pl: ifaces[key]['prefix_length']=pl
            return
        m = re.match(r'members\s+(\S+)$', line)
        if m:
            try:
                vid = int(m.group(1))
                if ifaces[key]['vlan_mode'] == 'trunk':
                    if vid not in ifaces[key]['trunk_vlans']:
                        ifaces[key]['trunk_vlans'].append(vid)
                else:
                    ifaces[key]['vlan_id'] = vid
                    ifaces[key]['vlan_mode'] = 'access'
            except: pass
            return
        m = re.match(r'interface-mode\s+(access|trunk)$', line)
        if m: ifaces[key]['vlan_mode']=m.group(1); return
        m = re.match(r'(input|output)\s+(\S+)$', line)
        if m:
            d,f = m.groups()
            if d=='input': ifaces[key]['acl_in']=f
            else: ifaces[key]['acl_out']=f
            ifaces[key]['firewall_policy']=f; return

    if path and path[0] == 'firewall':
        fn = _seg_val(path, 'filter')
        if fn is None: return
        if fn not in acls: acls[fn]=_acl_new(fn)
        tn = _seg_val(path, 'term')
        if tn is None: return
        m = re.match(r'(accept|reject|discard)$', line)
        if m:
            _acl_upsert(acls[fn],tn,'action','permit' if m.group(1)=='accept' else 'deny'); return
        m = re.match(r'source-address\s+(\S+)$', line)
        if m: _acl_upsert(acls[fn],tn,'src_network',m.group(1)); return
        m = re.match(r'destination-address\s+(\S+)$', line)
        if m: _acl_upsert(acls[fn],tn,'dst_network',m.group(1)); return
        m = re.match(r'protocol\s+(\S+)$', line)
        if m: _acl_upsert(acls[fn],tn,'protocol',m.group(1)); return
        m = re.match(r'destination-port\s+(\d+)$', line)
        if m:
            try: _acl_upsert(acls[fn],tn,'dst_port',int(m.group(1)))
            except: pass
            return

def _parse_hier(raw, hostname):
    ifaces, acls, path = {}, {}, []
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            m = re.match(r'host-name\s+(\S+)', line.lstrip('#').strip())
            if m and hostname=='unknown': hostname=m.group(1).rstrip(';')
            continue
        m = re.match(r'host-name\s+(\S+)', line)
        if m and (not path or path == ['system']):
            if hostname=='unknown': hostname=m.group(1).rstrip(';')
            continue
        opens, closes = line.count('{'), line.count('}')
        if opens and not closes:
            tok = line.rstrip('{').strip()
            if tok: path.append(tok)
            continue
        if closes and not opens:
            for _ in range(closes):
                if path: path.pop()
            continue
        if opens and closes: continue
        _hier_leaf(line, path, ifaces, acls)
    model = 'JunOS Device'
    m = re.search(r'Model:\s*(\S+)', raw, re.I)
    if m: model = m.group(1)
    mgmt = _mgmt_ip(ifaces)
    return {'device':{'name':hostname,'hostname':hostname,'vendor':'Juniper','model':model,
            'os':'JunOS','management_ip':mgmt or '0.0.0.0','device_type':_dtype(hostname,ifaces),
            'tags':['junos','parsed']},
            'interfaces':list(ifaces.values()),'acls':list(acls.values())}

# --- Public API ---
def parse_junos(raw, hostname='unknown'):
    """Parse a JunOS config string (set or hierarchical). Returns dict: device, interfaces, acls."""
    fmt = _detect_format(raw)
    log.info('JunOS format: %s  hostname_hint=%s', fmt, hostname)
    result = _parse_set(raw, hostname) if fmt == 'set' else _parse_hier(raw, hostname)
    log.info('Parsed %s: %d ifaces, %d acls', result['device']['name'],
             len(result['interfaces']), len(result['acls']))
    return result
