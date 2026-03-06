"""
ルールベースの悩み分析エンジン
Yahoo!知恵袋の投稿を「緊急性」「悩みの深さ」「コンプレックス度」の3軸で評価する
"""

import re
from typing import Dict, List, Tuple


# ============================================================
# スコアリング用キーワード辞書
# 各カテゴリに対して (キーワード/パターン, 加算ポイント) のリスト
# ============================================================

URGENCY_KEYWORDS: List[Tuple[str, int]] = [
    # --- 最高緊急性 (5点) ---
    (r'激痛', 5),
    (r'歩けな[いく]', 5),
    (r'動けな[いく]', 5),
    (r'立てな[いく]', 5),
    (r'起き[上ら]れな[いく]', 5),
    (r'息が?でき[なず]', 5),
    (r'意識.{0,3}(飛|なくな|薄)', 5),
    (r'救急', 5),
    (r'倒れ', 4),

    # --- 高緊急性 (4点) ---
    (r'眠れな[いく]', 4),
    (r'寝られな[いく]', 4),
    (r'仕事.{0,5}(行けな|できな|休)', 4),
    (r'学校.{0,5}(行けな|休)', 4),
    (r'痛くて.{0,8}(できな|無理|ダメ)', 4),
    (r'痛すぎ', 4),
    (r'突然', 3),
    (r'急に', 3),
    (r'悪化', 4),
    (r'ひどくなっ', 4),
    (r'どんどん', 3),

    # --- 中緊急性 (3点) ---
    (r'辛[いく]', 3),
    (r'つら[いく]', 3),
    (r'苦し[いく]', 3),
    (r'耐えられな[いく]', 4),
    (r'我慢.{0,3}(できな|限界)', 4),
    (r'限界', 3),
    (r'日常生活.{0,5}(支障|影響|困)', 3),
    (r'生活.{0,5}(支障|できな)', 3),
    (r'すぐ.{0,5}(治し|なんとか|楽に)', 3),
    (r'今すぐ', 3),
    (r'助けて', 4),

    # --- やや緊急 (2点) ---
    (r'痛[いく]', 2),
    (r'しびれ', 2),
    (r'だるい', 1),
    (r'重い', 1),
    (r'違和感', 1),
    (r'不安', 2),
    (r'心配', 2),
    (r'困って', 2),
    (r'どうすれば', 2),
    (r'どうしたら', 2),
]

DEPTH_KEYWORDS: List[Tuple[str, int]] = [
    # --- 最深レベル (5点) ---
    (r'何十年', 5),
    (r'[1-9]0年以上', 5),
    (r'一生', 5),
    (r'生まれ.{0,5}(から|つき)', 5),
    (r'もう.{0,5}諦め', 5),
    (r'治る.{0,5}(のか|こと.{0,3}ない)', 5),
    (r'絶望', 5),

    # --- 深いレベル (4点) ---
    (r'何年も', 4),
    (r'[2-9]年(以上|間)?', 4),
    (r'10年', 5),
    (r'長年', 4),
    (r'慢性', 4),
    (r'ずっと', 3),
    (r'昔から', 3),
    (r'(何|色々|いろいろ).{0,5}(試し|やっ)', 4),
    (r'どこ.{0,5}(行っても|通っても)', 4),
    (r'(病院|整形|整体|接骨|鍼灸).{0,8}(行っ|通っ|かかっ)', 3),
    (r'何(軒|件|箇所|ヶ所)', 4),
    (r'改善.{0,3}(しな|されな|できな)', 4),
    (r'治らな[いく]', 4),
    (r'良くならな[いく]', 4),
    (r'変わらな[いく]', 3),

    # --- 中程度 (3点) ---
    (r'半年(以上)?', 3),
    (r'[3-9]ヶ月', 3),
    (r'なかなか', 3),
    (r'繰り返[しす]', 3),
    (r'再発', 3),
    (r'(薬|湿布|注射).{0,5}(効かな|だめ)', 3),
    (r'手術.{0,5}(言われ|勧め|しか)', 4),

    # --- やや深い (2点) ---
    (r'(数|[1-2])ヶ月', 2),
    (r'(数|何)週間', 2),
    (r'最近', 1),
    (r'前から', 2),
]

COMPLEX_KEYWORDS: List[Tuple[str, int]] = [
    # --- 最高コンプレックス (5点) ---
    (r'人前.{0,5}(出[らけれ]な|行けな|無理)', 5),
    (r'外出.{0,5}(できな|したくな|怖)', 5),
    (r'引きこもり', 5),
    (r'死にたい', 5),
    (r'生き.{0,5}(たくな|意味)', 5),

    # --- 高コンプレックス (4点) ---
    (r'恥ずかし[いく]', 4),
    (r'人に(見られ|言え|相談|話せ).{0,5}(たくな|な[いく])', 4),
    (r'隠し(たい|て)', 3),
    (r'人と.{0,5}(会いたくな|会うのが|話すのが)', 4),
    (r'見られ.{0,5}(たくな|怖|嫌)', 4),
    (r'(彼氏|彼女|パートナー|旦那|妻|夫).{0,8}(見せ|知られ|言え|バレ)', 4),
    (r'(結婚|恋愛|出会い).{0,8}(できな|諦め|不安|怖)', 4),
    (r'(温泉|プール|海|銭湯).{0,5}(行けな|入れな|無理)', 4),

    # --- 中コンプレックス (3点) ---
    (r'コンプレックス', 3),
    (r'自信.{0,3}(がな|ない|なく|持て)', 3),
    (r'見た目', 3),
    (r'(目立[つち]|目立って)', 3),
    (r'気になっ', 2),
    (r'気にして', 2),
    (r'気にな[るり]', 2),
    (r'(人の目|周りの目|視線)', 3),
    (r'(情けな|みじめ|惨め)', 3),
    (r'(笑われ|からかわれ|いじ[めら])', 4),
    (r'(写真|鏡).{0,5}(見たくな|映りたくな|嫌)', 3),

    # --- やや気にしている (2点) ---
    (r'(ちょっと|少し).{0,5}(気にな|コンプ)', 2),
    (r'(姿勢|スタイル|体型|体形).{0,5}(悪|気にな)', 2),
    (r'(老けて|年齢.{0,3}(より|以上))', 2),
    (r'(太[っいく]|太り|ぽっちゃり)', 2),
    (r'(猫背|O脚|X脚|反り腰|巻き肩)', 2),
]

# 「表面的な悩み」を検出するパターン（スコアを下げる要因）
SURFACE_INDICATORS: List[Tuple[str, int]] = [
    (r'ちょっと聞きたい', -2),
    (r'素朴な疑問', -3),
    (r'興味.{0,3}(ある|ありま)', -2),
    (r'(おすすめ|オススメ).{0,3}(教えて|ありま)', -1),
]


def _count_keyword_score(text: str, keywords: List[Tuple[str, int]]) -> int:
    """テキスト内のキーワードマッチに基づいてスコアを計算"""
    total = 0
    matched = []
    for pattern, points in keywords:
        matches = re.findall(pattern, text)
        if matches:
            total += points
            matched.append((pattern, points, len(matches)))
    return total, matched


def _normalize_score(raw_score: int, max_expected: int = 15) -> int:
    """生スコアを1-5の5段階に正規化"""
    if raw_score <= 0:
        return 0
    elif raw_score <= 2:
        return 1
    elif raw_score <= 5:
        return 2
    elif raw_score <= 9:
        return 3
    elif raw_score <= 14:
        return 4
    else:
        return 5


def analyze_concern(text: str) -> Dict:
    """
    テキストを分析して3軸のスコアを返す

    Args:
        text: 分析対象のテキスト（質問タイトル + 本文）

    Returns:
        {
            urgency: {score: 0-5, raw: int, label: str, matches: []},
            depth: {score: 0-5, raw: int, label: str, matches: []},
            complex: {score: 0-5, raw: int, label: str, matches: []},
            total_score: int,
            priority: str,
        }
    """
    urgency_labels = ['なし', '低い', 'やや高い', '高い', 'かなり高い', '非常に高い']
    depth_labels = ['なし', '浅い', 'やや深い', '深い', 'かなり深い', '非常に深い']
    complex_labels = ['なし', '軽度', 'やや強い', '強い', 'かなり強い', '非常に強い']

    # 各軸のスコア計算
    urgency_raw, urgency_matches = _count_keyword_score(text, URGENCY_KEYWORDS)
    depth_raw, depth_matches = _count_keyword_score(text, DEPTH_KEYWORDS)
    complex_raw, complex_matches = _count_keyword_score(text, COMPLEX_KEYWORDS)

    # 表面的な悩みの補正
    surface_raw, _ = _count_keyword_score(text, SURFACE_INDICATORS)
    urgency_raw += surface_raw
    depth_raw += surface_raw

    # 正規化
    urgency_score = _normalize_score(urgency_raw)
    depth_score = _normalize_score(depth_raw)
    complex_score = _normalize_score(complex_raw)

    total = urgency_score + depth_score + complex_score

    # 優先度判定
    if total >= 12:
        priority = '最優先ターゲット'
        priority_color = '#dc2626'
    elif total >= 9:
        priority = '高優先ターゲット'
        priority_color = '#ea580c'
    elif total >= 6:
        priority = '中優先ターゲット'
        priority_color = '#ca8a04'
    elif total >= 3:
        priority = '低優先'
        priority_color = '#65a30d'
    else:
        priority = '対象外'
        priority_color = '#9ca3af'

    return {
        'urgency': {
            'score': urgency_score,
            'raw': max(0, urgency_raw),
            'label': urgency_labels[urgency_score],
            'matches': [m[0] for m in urgency_matches[:5]],
        },
        'depth': {
            'score': depth_score,
            'raw': max(0, depth_raw),
            'label': depth_labels[depth_score],
            'matches': [m[0] for m in depth_matches[:5]],
        },
        'complex': {
            'score': complex_score,
            'raw': max(0, complex_raw),
            'label': complex_labels[complex_score],
            'matches': [m[0] for m in complex_matches[:5]],
        },
        'total_score': total,
        'priority': priority,
        'priority_color': priority_color,
    }


def analyze_results(results: List[Dict]) -> List[Dict]:
    """
    検索結果リスト全体を分析し、スコア付きで返す

    Args:
        results: [{title, url, full_text, snippet}, ...]

    Returns:
        スコア付き結果リスト（total_scoreで降順ソート）
    """
    analyzed = []
    for result in results:
        # タイトル + 本文 を合わせて分析
        text = result.get('title', '') + ' ' + result.get('full_text', '')
        if not text.strip():
            text = result.get('snippet', '')

        analysis = analyze_concern(text)

        analyzed.append({
            **result,
            'analysis': analysis,
        })

    # total_score で降順ソート
    analyzed.sort(key=lambda x: x['analysis']['total_score'], reverse=True)

    return analyzed


if __name__ == '__main__':
    # テスト
    test_texts = [
        "腰痛で辛い日々を送りながら仕事をしています。激痛で歩けなくなることもあり、"
        "何年も整形外科に通っていますが全く改善しません。もう諦めるしかないのでしょうか。",

        "最近肩が少し凝ります。おすすめのストレッチを教えてください。",

        "顔の歪みがコンプレックスで人に会うのが怖いです。"
        "写真も撮られたくないし、鏡を見るのも嫌です。"
        "整体に何軒も行きましたが治りません。もう5年以上悩んでいます。",
    ]

    for i, text in enumerate(test_texts, 1):
        result = analyze_concern(text)
        print(f"\n=== テスト{i} ===")
        print(f"テキスト: {text[:60]}...")
        print(f"緊急性: {result['urgency']['score']}/5 ({result['urgency']['label']})")
        print(f"深い悩み: {result['depth']['score']}/5 ({result['depth']['label']})")
        print(f"コンプレックス: {result['complex']['score']}/5 ({result['complex']['label']})")
        print(f"合計: {result['total_score']}/15 → {result['priority']}")
