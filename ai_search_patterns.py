"""
AI検索パターン生成モジュール

Claude APIを使用して、キーワードに関連する
「擬音・擬態語」「二次的損失」「失敗体験」「真の願望」
の4カテゴリで検索パターンを自動生成する。
エラー時はカテゴリベースのフォールバックに切り替え。
"""

import json
import os
import re


def generate_search_patterns_ai(keyword):
    """
    Claude APIでキーワードから検索パターンを生成する。

    4カテゴリ × 3パターン + 基本パターン5個 = 最大17個のサフィックスを返す。
    Vercel 60sタイムアウト対策のため、max_tokens=800で高速化。

    Args:
        keyword: ユーザーの検索キーワード（例: "腰痛"）

    Returns:
        {
            'suffixes': ['ズキズキ', '子供と遊べない', ...],
            'categories': {
                'onomatopoeia': [...],    # 擬音・擬態語
                'secondary_loss': [...],  # 二次的損失
                'failed_experience': [...], # 失敗体験
                'true_desire': [...]      # 真の願望
            },
            'source': 'ai' or 'fallback'
        }
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        print('[patterns] ANTHROPIC_API_KEY未設定 → フォールバック')
        return _fallback_patterns(keyword)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        system_prompt = """あなたはサロン（整体院・接骨院・エステ・鍼灸院）のマーケティングリサーチ専門家です。
Yahoo!知恵袋で「深い悩み」を持つ見込み客の投稿を見つけるための検索キーワードを生成してください。

以下の4カテゴリそれぞれ3個ずつ、合計12個の「検索用サフィックス」を生成すること。
サフィックスはメインキーワードの後ろに付けて検索する短い語句です（2〜6語程度）。

必ず以下のJSON形式で出力:
{
  "onomatopoeia": ["サフィックス1", "サフィックス2", "サフィックス3"],
  "secondary_loss": ["サフィックス1", "サフィックス2", "サフィックス3"],
  "failed_experience": ["サフィックス1", "サフィックス2", "サフィックス3"],
  "true_desire": ["サフィックス1", "サフィックス2", "サフィックス3"]
}"""

        user_prompt = f"""キーワード「{keyword}」について、Yahoo!知恵袋で深い悩みを見つけるための検索サフィックスを生成してください。

【擬音・擬態語（onomatopoeia）】
「{keyword}」に悩む人が使う生々しい擬音語・体感表現（例: ズキズキ、パンパン、鏡を見るのがツライ）

【二次的損失（secondary_loss）】
「{keyword}」のせいで諦めていること・できなくなったこと（例: 子供と走れない、好きな服が着られない、旅行に行けない）

【失敗体験（failed_experience）】
「{keyword}」で試して効果がなかった体験（例: 整形外科 効かない、サプリ ダメだった、マッサージ 一時的）

【真の願望（true_desire）】
「{keyword}」が治った先で本当にしたいこと（例: 昔の服を着て同窓会に行きたい、孫を抱っこしたい）

JSON形式のみ出力。説明文不要。"""

        print(f'[patterns] Claude APIで検索パターン生成中... keyword={keyword}')

        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=800,
            timeout=15.0,
            system=system_prompt,
            messages=[{'role': 'user', 'content': user_prompt}],
        )

        response_text = message.content[0].text.strip()
        print(f'[patterns] Claude API応答取得 ({len(response_text)}文字)')

        # JSONを抽出
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            raise ValueError('JSON が見つかりません')

        categories = json.loads(json_match.group())

        # バリデーション
        required_keys = ['onomatopoeia', 'secondary_loss', 'failed_experience', 'true_desire']
        for key in required_keys:
            if key not in categories or not isinstance(categories[key], list):
                raise ValueError(f'カテゴリ {key} が不正です')

        # サフィックスリストを構築
        # 基本サフィックス（必須）+ AI生成の4カテゴリ
        base_suffixes = ['', '辛い', '治らない', '悩み', '助けて']
        ai_suffixes = []
        for key in required_keys:
            for s in categories[key][:3]:
                if isinstance(s, str) and s.strip():
                    ai_suffixes.append(s.strip())

        all_suffixes = base_suffixes + ai_suffixes
        print(f'[patterns] AI生成完了: {len(ai_suffixes)}個のAIパターン + {len(base_suffixes)}個の基本パターン = {len(all_suffixes)}個')

        return {
            'suffixes': all_suffixes,
            'categories': categories,
            'source': 'ai',
        }

    except Exception as e:
        print(f'[patterns] Claude APIエラー: {e} → フォールバック')
        return _fallback_patterns(keyword)


def _fallback_patterns(keyword):
    """カテゴリベースのフォールバック"""
    from scraper import _detect_category
    category, suffixes = _detect_category(keyword)

    # カテゴリサフィックスからカテゴリ別に振り分け
    categories = {
        'onomatopoeia': [],
        'secondary_loss': [],
        'failed_experience': [],
        'true_desire': [],
    }

    print(f'[patterns] フォールバック: カテゴリ={category}, サフィックス={len(suffixes)}個')

    return {
        'suffixes': suffixes,
        'categories': categories,
        'source': 'fallback',
    }
