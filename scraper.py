"""
Yahoo!知恵袋スクレイピングモジュール
検索結果ページおよび個別質問ページからデータを取得する
"""

import urllib.request
import urllib.parse
import re
import json
import time
from html import unescape
from typing import List, Dict, Optional


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


def search_chiebukuro(keyword: str, num_pages: int = 2) -> List[Dict]:
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
        url = (
            f'https://chiebukuro.yahoo.co.jp/search'
            f'?p={encoded_keyword}&type=tag&page={page}'
        )

        try:
            req = _build_request(url)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read().decode('utf-8')
        except Exception as e:
            print(f"[scraper] Search page {page} fetch error: {e}")
            continue

        # 質問リンクを抽出
        link_pattern = (
            r'href="(https://detail\.chiebukuro\.yahoo\.co\.jp'
            r'/qa/question_detail/q\d+)[^"]*"'
        )
        links = re.findall(link_pattern, html)

        # 検索結果のタイトルとスニペットを抽出
        # <a> タグ内のテキストからタイトルを取得
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
            time.sleep(0.5)

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


def search_and_fetch(keyword: str, max_details: int = 15) -> List[Dict]:
    """
    キーワードで検索し、上位の質問の詳細テキストも取得する

    Args:
        keyword: 検索キーワード
        max_details: 詳細を取得する最大件数

    Returns:
        [{title, url, full_text}, ...]
    """
    results = search_chiebukuro(keyword, num_pages=2)

    for i, result in enumerate(results[:max_details]):
        detail = fetch_question_detail(result['url'])
        if detail:
            result['full_text'] = detail['body']
            if not result['title'] or len(result['title']) < len(detail['title']):
                result['title'] = detail['title']

        if i < max_details - 1:
            time.sleep(0.3)

    return results


if __name__ == '__main__':
    # テスト実行
    results = search_and_fetch('腰痛 辛い', max_details=3)
    for r in results[:3]:
        print(f"Title: {r['title'][:80]}")
        print(f"URL: {r['url']}")
        print(f"Text: {r['full_text'][:150]}")
        print('---')
