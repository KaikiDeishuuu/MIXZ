#!/usr/bin/env python3
import re, json, html, urllib.request, urllib.parse
from html import unescape
from pathlib import Path
from datetime import datetime

TARGETS=[Path('/root/.openclaw/workspace/mixz-site/index.html'), Path('/var/www/mixz/index.html')]
MIN_GOOD_ABSTRACT_LEN = 260
MIN_ACCEPTABLE_ABSTRACT_LEN = 80



def normalize_text(s):
    s = unescape(s or '')
    s = re.sub(r'<[^>]+>', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def looks_like_bad_abstract(title, abstract):
    t = normalize_text(title)
    a = normalize_text(abstract)
    if not a:
        return True
    if len(a) < MIN_ACCEPTABLE_ABSTRACT_LEN:
        return True
    if a == t:
        return True
    if a.endswith(t) or t.endswith(a):
        return True
    if a.startswith('nature ') or a.startswith('science ') or a.startswith('ieee ') or a.startswith('biosensors and bioelectronics'):
        # common metadata-title style fallbacks
        if len(a) < 160:
            return True
    # very high token overlap with title and too short -> likely title/metadata, not abstract
    title_tokens = set(re.findall(r'[a-z0-9]+', t))
    abs_tokens = set(re.findall(r'[a-z0-9]+', a))
    if title_tokens:
        overlap = len(title_tokens & abs_tokens) / max(1, len(title_tokens))
        if overlap > 0.8 and len(a) < 180:
            return True
    return False

def openalex_abs(doi):
    try:
        u='https://api.openalex.org/works/https://doi.org/'+urllib.parse.quote(doi,safe='')
        data=json.load(urllib.request.urlopen(u, timeout=20))
        inv=data.get('abstract_inverted_index')
        if not inv: return None
        n=max(max(v) for v in inv.values())
        words=['']*(n+1)
        for w,poses in inv.items():
            for p in poses: words[p]=w
        a=re.sub(r'\s+',' ',' '.join(words)).strip()
        return a if len(a) >= MIN_ACCEPTABLE_ABSTRACT_LEN else None
    except Exception:
        return None


def s2_abs(doi):
    try:
        u='https://api.semanticscholar.org/graph/v1/paper/DOI:'+urllib.parse.quote(doi,safe='')+'?fields=abstract'
        data=json.load(urllib.request.urlopen(u, timeout=20))
        a=data.get('abstract')
        if not a: return None
        a=re.sub(r'\s+',' ',a).strip()
        return a if len(a) >= MIN_ACCEPTABLE_ABSTRACT_LEN else None
    except Exception:
        return None



def crossref_abs(doi):
    try:
        u='https://api.crossref.org/works/'+urllib.parse.quote(doi, safe='')
        req=urllib.request.Request(u, headers={'User-Agent':'Mozilla/5.0'})
        data=json.load(urllib.request.urlopen(req, timeout=20))
        a=(data.get('message') or {}).get('abstract')
        if not a:
            return None
        a=re.sub(r'<[^>]+>', ' ', a)
        a=unescape(a)
        a=re.sub(r'\s+',' ',a).strip()
        return a if len(a) >= MIN_ACCEPTABLE_ABSTRACT_LEN else None
    except Exception:
        return None


def doi_meta_abs(doi):
    try:
        url='https://doi.org/'+doi
        req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        html_doc=urllib.request.urlopen(req, timeout=20).read().decode('utf-8', 'ignore')
        patterns=[
            r"<meta[^>]+name=['\"]description['\"][^>]+content=['\"]([^'\"]+)['\"]",
            r"<meta[^>]+property=['\"]og:description['\"][^>]+content=['\"]([^'\"]+)['\"]",
            r"<meta[^>]+name=['\"]twitter:description['\"][^>]+content=['\"]([^'\"]+)['\"]",
            r"<meta[^>]+name=['\"]dc.description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        ]
        for pat in patterns:
            m=re.search(pat, html_doc, flags=re.I)
            if m:
                a=unescape(m.group(1))
                a=re.sub(r'\s+',' ',a).strip()
                if len(a) >= MIN_ACCEPTABLE_ABSTRACT_LEN and 'javascript is disabled' not in a.lower():
                    return a
    except Exception:
        return None
    return None


def best_abstract_for_doi(doi, title=''):
    sources = [
        ('openalex', openalex_abs),
        ('semantic_scholar', s2_abs),
        ('crossref', crossref_abs),
        ('doi_meta', doi_meta_abs),
    ]
    tried = []
    fallback = None
    for name, fn in sources:
        a = fn(doi)
        tried.append((name, len(a) if a else 0))
        if not a or looks_like_bad_abstract(title, a):
            continue
        if len(a) >= MIN_GOOD_ABSTRACT_LEN:
            return a, name, tried
        if fallback is None or len(a) > len(fallback[0]):
            fallback = (a, name)
    if fallback:
        return fallback[0], fallback[1], tried
    return None, None, tried

def backfill(path: Path):
    s=path.read_text(encoding='utf-8')
    cards=re.findall(r'<div class="card">.*?</div></div></div>', s, flags=re.S)
    changed=0
    pending=0
    for c in cards:
        if '暂无公开摘要' not in c:
            continue
        pending += 1
        m=re.search(r'https?://doi\.org/([^"<\s]+)', c)
        if not m:
            continue
        doi=m.group(1)
        tm = re.search(r'<div class="title">(.*?)</div>', c, flags=re.S)
        title = html.unescape(tm.group(1)) if tm else ''
        ab, source, tried = best_abstract_for_doi(doi, title=title)
        if not ab:
            continue
        c2=c.replace('暂无公开摘要', html.escape(ab))
        s=s.replace(c,c2,1)
        changed += 1
    path.write_text(s, encoding='utf-8')
    remain=s.count('暂无公开摘要')
    return {'file':str(path),'changed':changed,'remain':remain,'checked':pending}


def main():
    results=[backfill(p) for p in TARGETS if p.exists()]
    print(json.dumps({'time':datetime.now().isoformat(),'results':results}, ensure_ascii=False))

if __name__=='__main__':
    main()
