"""
AI分析コメント生成スクリプト（GitHub Models 連携）

generate_monthly.py から `--with-ai` 経由で呼ばれることを想定。
ローカルで単体テストもできる:
    python scripts/ai_comment.py --input data/latest.json

GITHUB_TOKEN 環境変数が必要:
- GitHub Actions では `${{ secrets.GITHUB_TOKEN }}` で自動付与される
- ローカル実行時は GitHub Personal Access Token（models:read 権限）を export しておく

設計書 §5「AIコメントの立て付け（4部構成・300字±50字）」に準拠。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

# GitHub Models（OpenAI互換エンドポイント）
MODELS_API_URL = "https://models.inference.ai.azure.com/chat/completions"
MODEL_ID = "gpt-4o-mini"

REQUEST_TIMEOUT_SEC = 60


def build_prompt(payload: dict) -> str:
    """設計書 §5 のプロンプト骨子に従ってユーザープロンプトを組み立てる。"""
    summary = payload.get("summary", {})
    total_sales = summary.get("totalSales", 0)
    order_count = summary.get("orderCount", 0)
    avg = summary.get("averageOrderValue", 0)
    mom = summary.get("monthOverMonthPct")
    mom_text = f"{mom}%" if mom is not None else "—（前月データなし）"

    top5 = payload.get("productRanking", [])[:5]
    if top5:
        top5_text = "\n".join(
            f"  {p['rank']}位: {p['name']} ({p['quantity']}個・¥{p['sales']:,}・構成比{p['sharePct']}%)"
            for p in top5
        )
    else:
        top5_text = "  （販売実績なし）"

    daily_sales = payload.get("dailySales", [])
    peak_day = max(daily_sales, key=lambda d: d["sales"], default=None)
    peak_text = (
        f"{peak_day['day']}日（¥{peak_day['sales']:,}）"
        if peak_day and peak_day["sales"] > 0
        else "突出した日なし"
    )
    sales_days = sum(1 for d in daily_sales if d["sales"] > 0)

    return (
        f"あなたは森田醤油醸造元（家業の醤油蔵）のEC売上を毎月分析するアナリストです。\n"
        f"以下のデータをもとに、家業オーナー向けの月次振り返りコメントを書いてください。\n\n"
        f"【月】{payload.get('monthLabel', '')}\n"
        f"【売上総額】¥{total_sales:,}\n"
        f"【注文件数】{order_count}件\n"
        f"【平均単価】¥{avg:,}\n"
        f"【前月比】{mom_text}\n"
        f"【売上があった日数】{sales_days}日\n"
        f"【ピーク日】{peak_text}\n"
        f"【商品ランキングTOP5】\n{top5_text}\n\n"
        "## 出力ルール\n"
        "- 文字数: 300字 ±50字（必ず守る）\n"
        "- 構成: 以下の4部を順に書く（小見出しは付けず、1つの自然な文章に繋げる）\n"
        "  1. 今月の振り返り（事実）約80字 — 売上・注文件数・前月比・トップ商品\n"
        "  2. 好調だった点（考察）約60字 — 何が売上に貢献したかの分析\n"
        "  3. 課題・反省点 約60字 — 伸び悩んだ点や改善余地\n"
        "  4. 来月への提案 約100字 — 具体施策を1〜2個\n"
        "- トーン: 穏やかだが前向き、家業への敬意を感じさせる\n"
        "- 過度に楽観/悲観な表現や、根拠のない予測は避ける\n"
        "- 注文件数が極端に少ない月でも、励ましつつ建設的な提案を入れる\n"
    )


def generate_comment(payload: dict) -> str:
    """GitHub Models API を叩いて AIコメントを返す。"""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN が環境変数にありません。\n"
            "  - GitHub Actions では secrets.GITHUB_TOKEN が自動付与されます\n"
            "  - ローカル実行時は models:read 権限を持つ Personal Access Token を export してください"
        )

    response = requests.post(
        MODELS_API_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL_ID,
            "messages": [
                {"role": "user", "content": build_prompt(payload)},
            ],
            "temperature": 0.7,
            "max_tokens": 800,
        },
        timeout=REQUEST_TIMEOUT_SEC,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub Models API エラー: HTTP {response.status_code}\n"
            f"レスポンス: {response.text[:500]}"
        )

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"レスポンス形式が想定外です: {data}") from e


def main() -> int:
    parser = argparse.ArgumentParser(description="AIコメント生成（単体テスト用）")
    parser.add_argument(
        "--input",
        default="data/latest.json",
        help="入力JSONファイル（デフォルト: data/latest.json）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"エラー: {input_path} が見つかりません。")
        return 1

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    try:
        comment = generate_comment(payload)
    except Exception as e:
        print(f"失敗: {e}")
        return 1

    print(comment)
    print(f"\n（{len(comment)}字）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
