"""
Yahoo!知恵袋スクレイピングモジュール
検索結果ページおよび個別質問ページからデータを取得する
拡張検索：キーワードに悩み系サフィックスを付加して深い悩みを優先的に取得
"""

import urllib.request
import urllib.parse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import List, Dict, Optional


# 深い悩みを見つけるための検索サフィックス
# ユーザーが「腰痛」と検索 → 「腰痛 辛い」「腰痛 激痛」等で拡張検索
DEEP_SEARCH_SUFFIXES = [
    '',           # 元のキーワードそのまま
    '辛い',
    '激痛',
    '治らない',
    '眠れない',
    '悪化',
    '慢性',
    '何年',
    '助けて',
    '限界',
    '歩けない',
    'コンプレックス',
    '恥ずかしい',
    '人前',
]


def _build_request(url: str) -> urllib.request.Request:
    """ブラウザを模倣したリクエストヘッダーを設定"""
    return urllib.request.Request(url, headers={
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Accept-Language': 'ja,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    })


def _clean_html(text: str) -> str:
    """HTMLタグを除去してプレーンテキストに変換"""
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def search_chiebukuro(keyword: str, num_pages: int = 3) -> List[Dict]:
    """
    Yahoo!知恵袋でキーワード検索し、質問のリストを返す

    Args:
        keyword: 検索キーワード
        num_pages: 取得するページ数（1ページ約10件）

    Returns:
        質問情報のリスト [{title, url, snippet}, ...]
    """
    results = []
    seen_urls = set()

    for page in range(1, num_pages + 1):
        encoded_keyword = urllib.parse.quote(keyword)
        # type=tag を除去し、通常のテキスト検索にする（より多くの結果が得られる）
        url = (
            f'https://chiebukuro.yahoo.co.jp/search'
            f'?p={encoded_keyword}&page={page}'
        )

        try:
            req = _build_request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8')
        except Exception as e:
            print(f"[scraper] Search page {page} fetch error: {e}")
            continue

        # 質問リンクとタイトルを抽出
        result_blocks = re.findall(
            r'<a[^>]*href="(https://detail\.chiebukuro\.yahoo\.co\.jp'
            r'/qa/question_detail/q\d+)[^"]*"[^>]*>(.*?)</a>',
            html, re.DOTALL
        )

        for link_url, title_html in result_blocks:
            # URLの正規化（クエリパラメータを除去し、質問IDで一意にする）
            q_id_match = re.search(r'q(\d+)', link_url)
            if not q_id_match:
                continue
            q_id = q_id_match.group(1)
            clean_url = f'https://detail.chiebukuro.yahoo.co.jp/qa/question_detail/q{q_id}'

            if clean_url in seen_urls:
                continue
            seen_urls.add(clean_url)

            title = _clean_html(title_html)
            if len(title) < 10:
                continue

            results.append({
                'title': title,
                'url': clean_url,
                'snippet': '',
                'full_text': '',
            })

        if page < num_pages:
            time.sleep(0.3)

    return results


def fetch_question_detail(url: str) -> Optional[Dict]:
    """
    個別の質問ページからタイトルと本文を取得する

    Args:
        url: 質問ページのURL

    Returns:
        {title, body, url} or None
    """
    try:
        req = _build_request(url)
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"[scraper] Detail page fetch error: {e}")
        return None

    # OGタグからタイトルと説明を取得
    og_title = ''
    og_desc = ''

    og_title_match = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"', html
    )
    if og_title_match:
        og_title = unescape(og_title_match.group(1))
        # 末尾の " - Yahoo!知恵袋" を除去
        og_title = re.sub(r'\s*-\s*Yahoo!知恵袋\s*$', '', og_title)

    og_desc_match = re.search(
        r'<meta\s+property="og:description"\s+content="([^"]+)"', html
    )
    if og_desc_match:
        og_desc = unescape(og_desc_match.group(1))

    body = og_desc if og_desc else og_title
    title = og_title if og_title else body[:100]

    return {
        'title': title,
        'body': body,
        'url': url,
    }


def _fetch_detail_safe(result: Dict) -> Dict:
    """並列取得用のラッパー（例外を握りつぶす）"""
    detail = fetch_question_detail(result['url'])
    if detail:
        result['full_text'] = detail['body']
        if not result['title'] or len(result['title']) < len(detail['title']):
            result['title'] = detail['title']
    return result


def expanded_search(keyword: str, max_results: int = 100) -> List[Dict]:
    """
    キーワードに悩み系サフィックスを付加して拡張検索する
    「腰痛」→「腰痛 辛い」「腰痛 激痛」等で検索し、
    深い悩みを含む投稿を幅広く取得する

    Args:
        keyword: ユーザーの検索キーワード
        max_results: 最大取得件数

    Returns:
        重複排除済みの質問リスト
    """
    all_results = []
    seen_urls = set()

    for suffix in DEEP_SEARCH_SUFFIXES:
        if len(all_results) >= max_results:
            break

        query = f'{keyword} {suffix}'.strip() if suffix else keyword
        print(f"[scraper] 拡張検索: '{query}'")

        # サフィックスなし（元キーワード）は3ページ、それ以外は2ページ
        pages = 3 if not suffix else 2
        results = search_chiebukuro(query, num_pages=pages)

        new_count = 0
        for r in results:
            if r['url'] not in seen_urls and len(all_results) < max_results:
                seen_urls.add(r['url'])
                all_results.append(r)
                new_count += 1

        print(f"[scraper]   → {new_count}件の新規結果")

        # レート制限対策
        time.sleep(0.3)

    print(f"[scraper] 合計 {len(all_results)}件の質問を取得")
    return all_results


def search_and_fetch(keyword: str, max_details: int = 100) -> List[Dict]:
    """
    拡張検索で多くの質問を取得し、並列で詳細テキストも取得する

    Args:
        keyword: 検索キーワード
        max_details: 詳細を取得する最大件数

    Returns:
        [{title, url, full_text}, ...]
    """
    # 拡張検索で多くの質問URLを取得
    results = expanded_search(keyword, max_results=max_details)

    # 並列で詳細ページを取得（5並列）
    print(f"[scraper] {len(results)}件の詳細を並列取得中...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_fetch_detail_safe, r): r
            for r in results
        }
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[scraper] Detail fetch error: {e}")

    print(f"[scraper] 詳細取得完了")
    return results


if __name__ == '__main__':
    # テスト実行
    results = search_and_fetch('腰痛', max_details=20)
    for r in results[:5]:
        print(f"Title: {r['title'][:80]}")
        print(f"URL: {r['url']}")
        print(f"Text: {r['full_text'][:150]}")
        print('---')
    print(f"\n合計: {len(results)}件")
