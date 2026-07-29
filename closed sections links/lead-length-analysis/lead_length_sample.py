#!/usr/bin/env python3
"""Sample random articles across top wikis, measure lead-section length,
estimate % over a word/char threshold (300 words, ~550 chars for CJK)."""

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
SAMPLE_SIZE = 200
BATCH = 20
UA = 'lead-length-research-script/1.0 (jscherer@wikimedia.org; Minerva pagination estimate)'

def api_call(wiki, params, retries=3):
    params = dict(params, format='json')
    url = f'https://{wiki}/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20, context=SSL_CONTEXT) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            if attempt == retries - 1:
                print(f'  FAILED {wiki} {params.get("titles","random")}: {e}', file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))

def get_random_titles(wiki, n):
    titles = []
    remaining = n
    while remaining > 0:
        batch_n = min(remaining, 20)  # API max for rnlimit without bot flag safety margin
        data = api_call(wiki, {
            'action': 'query', 'list': 'random', 'rnnamespace': 0, 'rnlimit': batch_n,
        })
        if not data:
            break
        titles.extend(p['title'] for p in data['query']['random'])
        remaining -= batch_n
        time.sleep(0.1)
    return titles

def get_extracts(wiki, titles):
    results = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        data = api_call(wiki, {
            'action': 'query', 'prop': 'extracts', 'exintro': 1, 'explaintext': 1,
            'redirects': 1, 'titles': '|'.join(chunk),
        })
        if not data:
            continue
        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            title = page.get('title')
            extract = page.get('extract', '') or ''
            results[title] = extract
        time.sleep(0.2)
    return results

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
        print(f'Sampling {wiki}...', file=sys.stderr)
        titles = get_random_titles(wiki, SAMPLE_SIZE)
        extracts = get_extracts(wiki, titles)
        n_over = 0
        n_total = 0
        lengths = []
        for title, extract in extracts.items():
            if not extract:
                continue
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
        print(f'  {wiki}: {n_total} sampled, {pct:.1f}% over threshold, median {median}', file=sys.stderr)

    with open('lead_length_raw.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['wiki', 'title', 'length', 'unit', 'over_threshold'])
        w.writeheader()
        w.writerows(rows)

    with open('lead_length_summary.json', 'w') as f:
        json.dump(summary, f, indent=2)

    print('\n--- SUMMARY ---')
    for s in summary:
        print(f"{s['wiki']}: {s['pct_over']}% over ({s['n_sampled']} sampled, median {s['median_length']} {s['unit']})")

if __name__ == '__main__':
    main()
