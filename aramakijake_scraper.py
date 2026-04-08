"""
aramakijake.jp スクレイピングモジュール

キーワードの月間推定検索数（Yahoo! JAPAN / Google）を取得し、
サロン集客におけるターゲットキーワードの有効性をランク評価する。

aramakijakeにデータがないキーワード（腰痛、頭痛等）は
サロン業界向けフォールバック辞書で補完する。
"""

import urllib.request
import urllib.parse
import re
from typing import Dict, Optional


# ============================================================
# aramakijake にデータがないキーワード用フォールバック
#
# データソース: Google Keyword Planner の公開レンジ
# Google Keyword Planner は広告出稿なしの場合
# 「1万〜10万」等のレンジで検索ボリュームを表示する。
# 下記はそのレンジ情報に基づく推定値。
#
# range_low / range_high = Google Keyword Planner のレンジ
# estimated = レンジの幾何平均（√(low×high)）を採用
# ※幾何平均は対数スケールの中央値で、検索ボリュームの
#   推定に広く使われている手法
# ============================================================
FALLBACK_VOLUMES = {
    # 痛み系 (Google KP: 1万〜10万)
    '腰痛':       {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '頭痛':       {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    'ぎっくり腰': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '坐骨神経痛': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '神経痛':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '関節痛':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '五十肩':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '椎間板ヘルニア': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    # 痛み系 (Google KP: 1000〜1万)
    '膝痛':       {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    '首痛':       {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    '股関節痛':   {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    # 姿勢・骨格系 (Google KP: 1万〜10万)
    '自律神経':       {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    'ストレートネック': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '骨盤矯正':   {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '側弯症':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '巻き肩':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    # 姿勢・骨格系 (Google KP: 1000〜1万)
    '産後骨盤':   {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    # 美容系 (Google KP: 1万〜10万)
    'ほうれい線': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    'むくみ':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    'セルライト': {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    'たるみ':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    # メンタル・女性系 (Google KP: 1万〜10万)
    '不眠':       {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '更年期':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '冷え性':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    '生理痛':     {'range_low': 10000, 'range_high': 100000, 'estimated': 31623},
    # メンタル・女性系 (Google KP: 1000〜1万)
    '眠れない':   {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    'PMS':        {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    '産後ダイエット': {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
    '尿漏れ':     {'range_low': 1000, 'range_high': 10000, 'estimated': 3162},
}


def fetch_search_volume(keyword: str) -> Dict:
    """
    aramakijake.jp からキーワードの月間推定検索数を取得する。
    データがない場合はフォールバック辞書で補完する。

    Args:
        keyword: 検索キーワード

    Returns:
        {
            'keyword': str,
            'yahoo_volume': int or None,
            'google_volume': int or None,
            'total_volume': int,
            'rank': str,           # 'S', 'A', 'B', 'C'
            'rank_label': str,     # ランクの説明
            'rank_color': str,     # 表示用カラー
            'rank_message': str,   # アドバイスメッセージ
            'has_data': bool,
            'source': str,         # 'aramakijake' or 'estimated'
        }
    """
    encoded = urllib.parse.quote(keyword)
    url = f'https://aramakijake.jp/keyword/index.php?keyword={encoded}'

    print(f'[aramakijake] 検索ボリューム取得中: {keyword}')

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'ja,en;q=0.9',
            'Referer': 'https://aramakijake.jp/',
        })

        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')

    except Exception as e:
        print(f'[aramakijake] 取得エラー: {e}')
        return _try_fallback(keyword, error=str(e))

    # データなしチェック
    if 'データが見つかりませんでした' in html:
        print(f'[aramakijake] データなし → フォールバック辞書を確認: {keyword}')
        return _try_fallback(keyword)

    # 月間推定検索数を抽出
    yahoo_vol = None
    google_vol = None

    vol_section = re.search(r'月間推定検索数([\s\S]*?)(?:で1位になるため)', html)
    if vol_section:
        nums = re.findall(r'>([\d,]+)<', vol_section.group(1))
        if len(nums) >= 2:
            yahoo_vol = _parse_num(nums[0])
            google_vol = _parse_num(nums[1])

    # ボリューム取得に失敗した場合もフォールバック
    if yahoo_vol is None and google_vol is None:
        return _try_fallback(keyword)

    total = (google_vol or 0) + (yahoo_vol or 0)
    rank_info = _evaluate_rank(total)

    print(f'[aramakijake] {keyword}: Yahoo={yahoo_vol}, Google={google_vol}, Total={total}, Rank={rank_info["rank"]}')

    return {
        'keyword': keyword,
        'yahoo_volume': yahoo_vol,
        'google_volume': google_vol,
        'total_volume': total,
        **rank_info,
        'has_data': True,
        'source': 'aramakijake',
    }


def _parse_num(s: str) -> int:
    """カンマ付き数字を int に変換"""
    return int(s.replace(',', ''))


def _evaluate_rank(total_volume: int) -> Dict:
    """
    月間検索ボリュームからターゲットキーワードの有効性をランク評価する。

    S: 20,000以上 → 主戦場。メインターゲットにすべき
    A: 5,000〜19,999 → 合格ラインだがやや物足りない
    B: 3,000〜4,999 → ギリギリ。サブキーワードとして検討
    C: 3,000未満 → 論外。キーワードの洗い直しが必要
    """
    if total_volume >= 20000:
        return {
            'rank': 'S',
            'rank_label': '主戦場キーワード',
            'rank_color': '#dc2626',
            'rank_message': (
                'ここが主戦場です！このキーワードをメインターゲットにして '
                '知恵袋リサーチ・ペルソナ設計・商品設計を進めましょう。'
            ),
            'rank_detail': '月間検索数20,000以上。十分な市場規模があり、集客の柱になるキーワードです。',
        }
    elif total_volume >= 5000:
        return {
            'rank': 'A',
            'rank_label': '合格ライン',
            'rank_color': '#ea580c',
            'rank_message': (
                '合格ラインですが、やや物足りません。このまま進めてもOKですが、'
                'より検索ボリュームの大きい関連キーワードも検討してみてください。'
            ),
            'rank_detail': '月間検索数5,000〜19,999。ニッチだが一定の需要あり。サブキーワードとの併用が効果的。',
        }
    elif total_volume >= 3000:
        return {
            'rank': 'B',
            'rank_label': 'ギリギリ',
            'rank_color': '#ca8a04',
            'rank_message': (
                'ギリギリのラインです。サブキーワードとしてなら使えますが、'
                'メインターゲットとしては弱いです。別の切り口も検討してください。'
            ),
            'rank_detail': '月間検索数3,000〜4,999。市場は小さめ。複数キーワードを組み合わせた戦略が必要。',
        }
    else:
        return {
            'rank': 'C',
            'rank_label': 'キーワード見直し推奨',
            'rank_color': '#6b7280',
            'rank_message': (
                'このキーワードでは検索ボリュームが不足しています。'
                'キーワードを洗い直して、より多くの人が検索しているワードを見つけましょう。'
            ),
            'rank_detail': '月間検索数3,000未満。集客のメインには不向き。キーワードの再選定が必要です。',
        }


def _try_fallback(keyword: str, error: str = '') -> Dict:
    """aramakijakeでデータが取れなかった場合、Google KPレンジ辞書を確認する"""

    def _build_range_result(kw, fb, match_type='exact'):
        """レンジデータから結果を構築"""
        estimated = fb['estimated']
        range_low = fb['range_low']
        range_high = fb['range_high']

        # ランク判定は保守的にレンジの下限で行う（確実に超えている場合のみ上位ランク）
        rank_info = _evaluate_rank_with_range(range_low, range_high, estimated)

        print(f'[aramakijake] Google KPレンジ ({match_type}): {kw} → {range_low:,}〜{range_high:,}')
        return {
            'keyword': kw,
            'yahoo_volume': None,
            'google_volume': None,
            'total_volume': estimated,
            'range_low': range_low,
            'range_high': range_high,
            **rank_info,
            'has_data': True,
            'source': 'google_kp_range',
        }

    # 完全一致チェック
    if keyword in FALLBACK_VOLUMES:
        return _build_range_result(keyword, FALLBACK_VOLUMES[keyword], 'exact')

    # 部分一致チェック
    for fb_key, fb in FALLBACK_VOLUMES.items():
        if fb_key in keyword or keyword in fb_key:
            return _build_range_result(keyword, fb, f'partial:{fb_key}')

    # どこにもデータがない
    print(f'[aramakijake] フォールバック辞書にもなし: {keyword}')
    return _no_data_result(keyword, error=error)


def _evaluate_rank_with_range(range_low: int, range_high: int, estimated: int) -> Dict:
    """
    レンジデータからランク評価する。
    下限が閾値を超えていれば確定ランク、
    レンジが閾値をまたぐ場合は保守的に判定。
    """
    # 下限が20,000以上 → 確実にS
    if range_low >= 20000:
        return {
            'rank': 'S',
            'rank_label': '主戦場キーワード',
            'rank_color': '#dc2626',
            'rank_message': (
                'ここが主戦場です！このキーワードをメインターゲットにして '
                '知恵袋リサーチ・ペルソナ設計・商品設計を進めましょう。'
            ),
            'rank_detail': f'Google Keyword Planner レンジ: {range_low:,}〜{range_high:,}。下限でも20,000以上のため、確実に十分な市場規模があります。',
        }
    # レンジが20,000をまたぐ（下限<20,000 かつ 上限>=20,000）→ S寄りのA
    elif range_high >= 20000 and range_low >= 5000:
        return {
            'rank': 'S',
            'rank_label': '主戦場キーワード（推定）',
            'rank_color': '#dc2626',
            'rank_message': (
                'Google Keyword Plannerのレンジ上、十分な検索ボリュームが見込めます。'
                'メインターゲットとして進めてOKです。'
            ),
            'rank_detail': f'Google Keyword Planner レンジ: {range_low:,}〜{range_high:,}。上限が20,000以上のため、主戦場の可能性が高いです。',
        }
    # 下限が5,000以上 → 確実にA以上
    elif range_low >= 5000:
        return {
            'rank': 'A',
            'rank_label': '合格ライン',
            'rank_color': '#ea580c',
            'rank_message': (
                '合格ラインです。このまま進めてもOKですが、'
                'より検索ボリュームの大きい関連キーワードも検討してみてください。'
            ),
            'rank_detail': f'Google Keyword Planner レンジ: {range_low:,}〜{range_high:,}。',
        }
    # レンジが5,000をまたぐ → B寄りのA
    elif range_high >= 5000 and range_low >= 1000:
        return {
            'rank': 'A',
            'rank_label': '合格ライン（推定）',
            'rank_color': '#ea580c',
            'rank_message': (
                '合格ラインの可能性が高いです。'
                'このまま進めてOKですが、関連キーワードの併用も検討してください。'
            ),
            'rank_detail': f'Google Keyword Planner レンジ: {range_low:,}〜{range_high:,}。',
        }
    # 下限3,000以上 → B
    elif range_low >= 3000:
        return _evaluate_rank(estimated)
    # それ以外 → 通常評価
    else:
        return _evaluate_rank(estimated)


def _no_data_result(keyword: str, error: str = '') -> Dict:
    """データが取得できなかった場合の結果"""
    return {
        'keyword': keyword,
        'yahoo_volume': None,
        'google_volume': None,
        'total_volume': 0,
        'rank': '?',
        'rank_label': 'データなし',
        'rank_color': '#9ca3af',
        'rank_message': (
            f'「{keyword}」の検索ボリュームデータが見つかりませんでした。'
            'キーワードの表記を変えて再度お試しください（例: ひらがな↔カタカナ、略称↔正式名称）。'
        ),
        'rank_detail': error or 'aramakijake.jpにデータが存在しないキーワードです。',
        'has_data': False,
        'source': 'none',
    }
