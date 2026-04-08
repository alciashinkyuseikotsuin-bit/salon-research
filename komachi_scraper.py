"""
発言小町（komachi.yomiuri.co.jp）スクレイピングモジュール

DuckDuckGo site検索でキーワード関連トピックを発見し、
発言小町APIで本文を取得する。
Yahoo!知恵袋と並行して、より深い悩み・体験談を収集する。
"""

import urllib.request
import urllib.parse
import re
import json
import time
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed


# 発言小町API設定
KOMACHI_API_HOST = 'https://komachi.yomiuri.co.jp'
KOMACHI_API_VERSION = 'v1'
KOMACHI_API_KEY = 'PkPOOPNwQycncl67iWhc8VphBkZkGfQavZXXOppi'


def search_komachi(keyword: str, max_results: int = 20) -> List[Dict]:
    """
    DuckDuckGo site検索で発言小町のキーワード関連トピックを取得し、
    APIで本文を取得する。

    Args:
        keyword: 検索キーワード（例: "腰痛"）
        max_results: 最大取得件数

    Returns:
        [{title, url, full_text, source, res_count, genre}, ...]
    """
    print(f'[komachi] 発言小町検索開始: {keyword}')

    # Step 1: Yahoo! JAPAN検索で発言小町のトピックIDを取得
    topic_ids = _search_yahoo(keyword, max_results=max_results)
    print(f'[komachi] Yahoo検索から{len(topic_ids)}件のトピックIDを取得')

    if not topic_ids:
        print('[komachi] トピックが見つかりませんでした')
        return []

    # Step 2: APIで各トピックの本文を並列取得
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_topic, tid): tid
            for tid in topic_ids[:max_results]
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    results.append(result)
            except Exception as e:
                print(f'[komachi] Topic fetch error: {e}')

    print(f'[komachi] {len(results)}件のトピックを取得完了')
    return results


def _search_yahoo(keyword: str, max_results: int = 20) -> List[str]:
    """
    Yahoo! JAPAN検索で site:komachi.yomiuri.co.jp のトピックIDを取得する。

    Returns:
        トピックIDのリスト
    """
    topic_ids = []
    seen = set()

    # 2ページ分取得（1ページ10件）
    for page_start in [1, 11]:
        if len(topic_ids) >= max_results:
            break

        query = urllib.parse.quote(f'{keyword} site:komachi.yomiuri.co.jp')
        url = f'https://search.yahoo.co.jp/search?p={query}&b={page_start}'

        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': (
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'ja',
            })

            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode('utf-8', errors='replace')

        except Exception as e:
            print(f'[komachi] Yahoo検索エラー (page={page_start}): {e}')
            continue

        # komachi URL内のトピックIDを抽出
        ids_in_page = re.findall(
            r'komachi\.yomiuri\.co\.jp/topics/(?:id/)?(\d+)',
            html
        )

        for tid in ids_in_page:
            if tid not in seen and len(topic_ids) < max_results:
                seen.add(tid)
                topic_ids.append(tid)

        if page_start == 1:
            time.sleep(0.3)

    return topic_ids


def _fetch_topic(topic_id: str) -> Dict:
    """
    発言小町APIから個別トピックの本文を取得する。

    Args:
        topic_id: トピックID

    Returns:
        {title, url, full_text, source, res_count, genre} or None
    """
    url = f'{KOMACHI_API_HOST}/api/{KOMACHI_API_VERSION}/topics/{topic_id}'

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'X-API-KEY': KOMACHI_API_KEY,
            'Accept': 'application/json',
        })

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))

    except Exception as e:
        print(f'[komachi] Topic {topic_id} fetch error: {e}')
        return None

    topic = data.get('topic', data)
    if not isinstance(topic, dict):
        return None

    title = topic.get('title', '')
    content = topic.get('content', '')
    short_content = topic.get('shortContent', '')
    genre = topic.get('genre', {})
    genre_name = genre.get('name', '') if isinstance(genre, dict) else ''
    res_count = topic.get('resCount', 0)

    body = content or short_content
    if not body and not title:
        return None

    return {
        'title': title,
        'url': f'https://komachi.yomiuri.co.jp/topics/{topic_id}',
        'full_text': body,
        'snippet': body[:200] if body else '',
        'source': 'komachi',
        'source_label': '発言小町',
        'res_count': res_count,
        'genre': genre_name,
    }


if __name__ == '__main__':
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else '腰痛'
    print(f'テスト検索: "{keyword}"')
    results = search_komachi(keyword, max_results=10)
    for r in results[:5]:
        print(f'\nTitle: {r["title"][:60]}')
        print(f'URL: {r["url"]}')
        print(f'Genre: {r["genre"]}')
        print(f'Replies: {r["res_count"]}')
        print(f'Text: {r["full_text"][:120]}')
    print(f'\n合計: {len(results)}件')
