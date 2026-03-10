#!/usr/bin/env python3
"""
サロン向け お悩みリサーチツール
Yahoo!知恵袋から深い悩みを検索・分析するWebアプリケーション

ローカル実行:
    pip install flask gunicorn
    python3 app.py
    → ブラウザで http://localhost:8080 にアクセス
"""

import json
import os
import re
import sys

from flask import Flask, request, jsonify, send_from_directory

# 同ディレクトリのモジュールをインポート
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper import search_and_fetch
from analyzer import analyze_results, analyze_concern
from ai_search_patterns import generate_search_patterns_ai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, 'static'))

PORT = int(os.environ.get('PORT', 8080))


# ========== ページ配信 ==========

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)


# ========== API ==========

@app.route('/api/search')
def api_search():
    """キーワード検索API"""
    keyword = request.args.get('keyword', '').strip()

    if not keyword:
        return jsonify({'error': 'キーワードを入力してください'}), 400

    try:
        import time as _time
        start = _time.time()
        print(f"[search] キーワード: {keyword}")

        # AI検索パターン生成（擬音・二次的損失・失敗体験・真の願望）
        patterns = generate_search_patterns_ai(keyword)
        pattern_elapsed = _time.time() - start
        print(f"[search] パターン生成完了 ({pattern_elapsed:.1f}秒, source={patterns['source']})")

        raw_results = search_and_fetch(
            keyword,
            max_details=100,
            custom_suffixes=patterns['suffixes'],
        )
        elapsed = _time.time() - start
        print(f"[search] {len(raw_results)}件の投稿を取得 ({elapsed:.1f}秒)")

        analyzed = analyze_results(raw_results)
        total_elapsed = _time.time() - start
        print(f"[search] 分析完了 (合計{total_elapsed:.1f}秒)")

        return jsonify({
            'keyword': keyword,
            'results': analyzed,
            'count': len(analyzed),
        })

    except Exception as e:
        print(f"[search] エラー: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """テキスト分析API"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip() if data else ''

        if not text:
            return jsonify({'error': 'テキストを入力してください'}), 400

        print(f"[analyze] テキスト長: {len(text)}文字")

        # テキストを投稿単位に分割（空行や区切り線で分割）
        segments = re.split(r'\n{2,}|_{3,}|-{3,}|={3,}', text)
        segments = [s.strip() for s in segments if len(s.strip()) > 20]

        if not segments:
            segments = [text]

        results = []
        for segment in segments:
            analysis = analyze_concern(segment)
            results.append({
                'title': segment[:80] + ('...' if len(segment) > 80 else ''),
                'url': '',
                'full_text': segment,
                'snippet': '',
                'analysis': analysis,
            })

        results.sort(key=lambda x: x['analysis']['total_score'], reverse=True)

        print(f"[analyze] {len(results)}件のセグメントを分析完了")

        return jsonify({
            'results': results,
            'count': len(results),
        })

    except Exception as e:
        print(f"[analyze] エラー: {e}")
        return jsonify({'error': str(e)}), 500


# ========== 起動 ==========

if __name__ == '__main__':
    print(f"""
╔══════════════════════════════════════════════════╗
║   サロン向け お悩みリサーチツール                  ║
║                                                  ║
║   ブラウザで以下にアクセスしてください:             ║
║   → http://localhost:{PORT}                       ║
║                                                  ║
║   終了: Ctrl+C                                   ║
╚══════════════════════════════════════════════════╝
""")
    app.run(host='0.0.0.0', port=PORT, debug=False)
