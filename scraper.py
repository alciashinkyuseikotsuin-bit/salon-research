"""
Yahoo!知恵袋スクレイピングモジュール
検索結果ページおよび個別質問ページからデータを取得する
拡張検索：入力キーワードのカテゴリを自動判定し、最適なサフィックスで検索
"""

import urllib.request
import urllib.parse
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from typing import List, Dict, Optional, Tuple


# ============================================================
# カテゴリ別サフィックス辞書
# 入力キーワードがどのカテゴリに属するか判定し、
# そのカテゴリに最適な検索サフィックスを使う
# ============================================================

# カテゴリ判定用キーワード → (カテゴリ名, 判定キーワードリスト)
CATEGORY_PATTERNS: List[Tuple[str, List[str]]] = [
    # 痛み・身体症状系
    ('pain', [
        '腰痛', '肩こり', '頭痛', '膝痛', '首痛', '背中痛',
        '坐骨神経痛', 'ヘルニア', 'ぎっくり腰', '五十肩', '四十肩',
        '腱鞘炎', '関節痛', '神経痛', '筋肉痛', '股関節',
        '痛い', '痛み', '痺れ', 'しびれ', '激痛',
        '脊柱管狭窄', '変形性', '椎間板', 'ストレートネック',
        '手根管', '足底筋膜', 'テニス肘', '腰', '肩', '首', '膝',
    ]),
    # 姿勢・骨格系
    ('posture', [
        '猫背', 'O脚', 'X脚', '反り腰', '巻き肩', '骨盤',
        '姿勢', '歪み', 'ゆがみ', '側弯', 'ストレートネック',
        '背骨', '脊椎', '骨格', '体幹', '均整',
    ]),
    # 美容・見た目系
    ('beauty', [
        '小顔', 'エラ', 'たるみ', 'シワ', 'しわ', 'ほうれい線',
        'むくみ', 'セルライト', '肌荒れ', 'ニキビ', 'にきび',
        '毛穴', 'シミ', 'クマ', 'くすみ', '老け',
        'フェイスライン', 'リフトアップ', '二重あご', '顔',
        '痩身', 'ダイエット', '太り', '痩せ', '体型', '体形',
        'ボディライン', 'バスト', 'ヒップ', '脚やせ', '足やせ',
        '美容', 'エステ', 'フェイシャル',
    ]),
    # 自律神経・メンタル系
    ('mental', [
        '自律神経', '不眠', '眠れない', '不安', 'パニック',
        'うつ', '鬱', 'ストレス', '疲労', '倦怠感', 'だるい',
        '動悸', 'めまい', '耳鳴り', '過呼吸', '息苦しい',
        '食欲不振', '胃腸', '便秘', '下痢', '冷え性',
        '更年期', 'PMS', '月経', '生理痛', 'ホルモン',
        'メンタル', '精神', '心療', '心身',
    ]),
    # 産後・女性特有系
    ('women', [
        '産後', '骨盤矯正', '妊娠中', 'マタニティ',
        '授乳', '育児', '抱っこ', '腱鞘炎',
        '生理痛', 'PMS', '月経不順', '更年期',
        '尿漏れ', '恥骨痛', '尾骨痛',
    ]),
    # スポーツ・怪我系
    ('sports', [
        'スポーツ', '怪我', 'ケガ', '捻挫', '肉離れ',
        '骨折', '脱臼', '打撲', 'アキレス腱', '靭帯',
        '半月板', '野球肘', 'ランナー', 'マラソン',
        'ゴルフ', 'テニス', 'サッカー', 'バスケ',
        'トレーニング', '筋トレ', 'リハビリ',
    ]),
]

# カテゴリ別の最適サフィックス
CATEGORY_SUFFIXES: Dict[str, List[str]] = {
    'pain': [
        '', '辛い', '激痛', '治らない', '眠れない', '悪化',
        '慢性', '何年', '歩けない', '仕事 休む',
        '手術 言われた', '整形外科 効かない',
        '整体 接骨院', '原因不明', '助けて',
    ],
    'posture': [
        '', '治したい', 'コンプレックス', '恥ずかしい', '治らない',
        '矯正', '悩み', '人前', '写真', '見た目',
        '整体', '何年', '自信がない', 'ひどい',
    ],
    'beauty': [
        '', '治らない', 'コンプレックス', '恥ずかしい', '悩み',
        '人に会いたくない', '隠したい', '自信がない',
        '何年', '効果ない', '高額', '繰り返す',
        '鏡 見たくない', 'すっぴん',
    ],
    'mental': [
        '', '辛い', '限界', '助けて', '治らない',
        '眠れない', '仕事 行けない', '何年',
        '悪化', '薬 効かない', '日常生活',
        '理解されない', '死にたい', '引きこもり',
    ],
    'women': [
        '', '辛い', '治らない', '痛い', '悩み',
        'いつまで', '改善しない', '仕事 育児',
        '眠れない', '限界', '病院 行けない',
        'ワンオペ', '相談できない',
    ],
    'sports': [
        '', '治らない', '痛い', '再発', '不安',
        '復帰', '悪化', '手術', 'リハビリ',
        '慢性', '選手生命', '引退',
    ],
}

# どのカテゴリにも該当しない場合の汎用サフィックス
DEFAULT_SUFFIXES = [
    '', '辛い', '治らない', '悩み', 'コンプレックス',
    '助けて', '限界', '何年', '悪化', '眠れない',
    '恥ずかしい', '人前', '改善しない', '原因',
]


def _detect_category(keyword: str) -> Tuple[str, List[str]]:
    """
    入力キーワードからカテゴリを自動判定し、最適なサフィックスリストを返す

    Args:
        keyword: ユーザーの検索キーワード

    Returns:
        (カテゴリ名, サフィックスリスト)
    """
    keyword_lower = keyword.strip()

    # 各カテゴリのマッチスコアを計算
    best_category = None
    best_score = 0

    for category, patterns in CATEGORY_PATTERNS:
        score = 0
        for pattern in patterns:
            if pattern in keyword_lower:
                # 完全一致に近いほど高スコア
                score += len(pattern)
        if score > best_score:
            best_score = score
            best_category = category

    if best_category and best_score > 0:
        print(f"[scraper] カテゴリ判定: '{keyword}' → {best_category}")
        return best_category, CATEGORY_SUFFIXES[best_category]
    else:
        print(f"[scraper] カテゴリ判定: '{keyword}' → 汎用（該当なし）")
        return 'default', DEFAULT_SUFFIXES


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

    og_title = ''
    og_desc = ''

    og_title_match = re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"', html
    )
    if og_title_match:
        og_title = unescape(og_title_match.group(1))
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


def expanded_search(keyword: str, max_results: int = 100, custom_suffixes: List[str] = None) -> List[Dict]:
    """
    入力キーワードのカテゴリを自動判定し、
    カテゴリに最適なサフィックスで拡張検索する

    custom_suffixesが渡された場合はそれを優先使用する（AI生成パターン対応）

    例: 「腰痛」→ pain カテゴリ → 「腰痛 激痛」「腰痛 歩けない」等
    例: 「小顔」→ beauty カテゴリ → 「小顔 コンプレックス」「小顔 効果ない」等

    Args:
        keyword: ユーザーの検索キーワード
        max_results: 最大取得件数
        custom_suffixes: カスタムサフィックスリスト（AI生成など）

    Returns:
        重複排除済みの質問リスト
    """
    if custom_suffixes:
        suffixes = custom_suffixes
        print(f"[scraper] カスタムサフィックス {len(suffixes)}個で検索開始（AI生成）")
    else:
        category, suffixes = _detect_category(keyword)
        print(f"[scraper] カテゴリ '{category}' のサフィックス {len(suffixes)}個で検索開始")

    all_results = []
    seen_urls = set()

    for suffix in suffixes:
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


def search_and_fetch(keyword: str, max_details: int = 100, custom_suffixes: List[str] = None) -> List[Dict]:
    """
    拡張検索で多くの質問を取得し、並列で詳細テキストも取得する

    Args:
        keyword: 検索キーワード
        max_details: 詳細を取得する最大件数
        custom_suffixes: カスタムサフィックスリスト（AI生成など）

    Returns:
        [{title, url, full_text}, ...]
    """
    results = expanded_search(keyword, max_results=max_details, custom_suffixes=custom_suffixes)

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
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else '腰痛'
    print(f"テスト検索: '{keyword}'")

    category, suffixes = _detect_category(keyword)
    print(f"カテゴリ: {category}")
    print(f"サフィックス: {suffixes}\n")

    results = search_and_fetch(keyword, max_details=20)
    for r in results[:5]:
        print(f"Title: {r['title'][:80]}")
        print(f"URL: {r['url']}")
        print(f"Text: {r['full_text'][:150]}")
        print('---')
    print(f"\n合計: {len(results)}件")
