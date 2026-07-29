#!/usr/bin/env python3
"""Same lead-length measurement as lead_length_sample.py, but sourcing
titles from each wiki's most-viewed articles (Pageviews API, most recent
complete month) instead of a uniform random sample."""

import json
import time
import ssl
import urllib.request
import urllib.parse
import csv
import sys
import certifi

SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

WIKIS = [
    'en.wikipedia.org', 'es.wikipedia.org', 'fr.wikipedia.org', 'de.wikipedia.org',
    'it.wikipedia.org', 'ja.wikipedia.org', 'ru.wikipedia.org', 'zh.wikipedia.org',
    'pl.wikipedia.org', 'nl.wikipedia.org', 'pt.wikipedia.org', 'fa.wikipedia.org',
    'he.wikipedia.org', 'ko.wikipedia.org', 'ar.wikipedia.org', 'id.wikipedia.org',
    'uk.wikipedia.org', 'tr.wikipedia.org', 'vi.wikipedia.org', 'cs.wikipedia.org',
]

CJK = {'ja.wikipedia.org', 'zh.wikipedia.org', 'ko.wikipedia.org'}
CHAR_THRESHOLD = 550
WORD_THRESHOLD = 300
TARGET_N = 200
BATCH = 20
YEAR, MONTH = 2026, '06'
UA = 'lead-length-research-script/1.0 (jscherer@wikimedia.org; Minerva pagination estimate)'


def http_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt == 2:
                print(f'  FAILED {url}: {e}', file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))


def api_call(wiki, params):
    params = dict(params, format='json')
    url = f'https://{wiki}/w/api.php?' + urllib.parse.urlencode(params)
    return http_get(url)


def get_top_titles(wiki):
    project = wiki.replace('.org', '')
    url = (f'https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{project}/'
           f'all-access/{YEAR}/{MONTH}/all-days')
    data = http_get(url)
    if not data:
        return []
    articles = data['items'][0]['articles']
    return [a['article'] for a in articles]


def get_ns0_extracts(wiki, candidate_titles, target_n):
    """Fetch info+extracts for candidates in rank order, keep first target_n
    that are real mainspace (ns=0) articles."""
    kept = {}  # title -> extract, insertion order = rank order
    i = 0
    while i < len(candidate_titles) and len(kept) < target_n:
        chunk = candidate_titles[i:i + BATCH]
        i += BATCH
        data = api_call(wiki, {
            'action': 'query', 'prop': 'extracts|info', 'exintro': 1, 'explaintext': 1,
            'redirects': 1, 'titles': '|'.join(chunk),
        })
        if not data:
            continue
        pages = data.get('query', {}).get('pages', {})
        # titles/redirects get normalized (underscores->spaces etc) so match by
        # scanning the returned pages rather than re-keying on the request titles
        for page in pages.values():
            if page.get('ns') != 0:
                continue
            title = page.get('title')
            if title in ('Main_Page', 'Main Page'):
                continue
            extract = page.get('extract', '') or ''
            if not extract:
                continue
            if title in kept:
                continue
            if len(kept) < target_n:
                kept[title] = extract
        time.sleep(0.2)
    return kept


def measure(wiki, extract):
    is_cjk = wiki in CJK
    if is_cjk:
        length = len(extract.strip())
        over = length > CHAR_THRESHOLD
    else:
        length = len(extract.split())
        over = length > WORD_THRESHOLD
    return length, over


def main():
    rows = []
    summary = []
    for wiki in WIKIS:
        print(f'Fetching top articles for {wiki}...', file=sys.stderr)
        candidates = get_top_titles(wiki)
        if not candidates:
            summary.append({'wiki': wiki, 'n_sampled': 0, 'pct_over': 0, 'median_length': 0,
                             'unit': 'chars' if wiki in CJK else 'words'})
            continue
        extracts = get_ns0_extracts(wiki, candidates, TARGET_N)
        n_over = 0
        n_total = 0
        lengths = []
        for title, extract in extracts.items():
            length, over = measure(wiki, extract)
            lengths.append(length)
            n_total += 1
            if over:
                n_over += 1
            rows.append({
                'wiki': wiki, 'title': title, 'length': length,
                'unit': 'chars' if wiki in CJK else 'words', 'over_threshold': over,
            })
        pct = (n_over / n_total * 100) if n_total else 0
        median = sorted(lengths)[len(lengths) // 2] if lengths else 0
        summary.append({
            'wiki': wiki, 'n_sampled': n_total, 'unit': 'chars' if wiki in CJK else 'words',
            'threshold': CHAR_THRESHOLD if wiki in CJK else WORD_THRESHOLD,
            'pct_over': round(pct, 1), 'median_length': median,
        })
        print(f'  {wiki}: {n_total} kept, {pct:.1f}% over threshold, median {median}', file=sys.stderr)

    with open('lead_length_top_raw.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['wiki', 'title', 'length', 'unit', 'over_threshold'])
        w.writeheader()
        w.writerows(rows)

    with open('lead_length_top_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print('\n--- SUMMARY (most-read articles) ---')
    for s in summary:
        print(f"{s['wiki']}: {s['pct_over']}% over ({s['n_sampled']} sampled, median {s['median_length']} {s['unit']})")


if __name__ == '__main__':
    main()
