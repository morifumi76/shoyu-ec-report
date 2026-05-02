"""
BASE API から指定日（デフォルト=前日）の注文データを取得し
data/daily/YYYY-MM-DD.json に保存する。

使い方:
    python scripts/fetch_daily.py                 # 前日分
    python scripts/fetch_daily.py --date 2026-05-01
    python scripts/fetch_daily.py --date 2026-05-01 --force  # 既存ファイル上書き
    python scripts/fetch_daily.py --dry-run       # 保存せず内容だけ表示

タイムゾーンは Asia/Tokyo（JST）固定。日付境界は JST の 0:00〜23:59:59。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# scripts/ をパスに追加してから base_api をインポート
sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_api import (  # noqa: E402
    BaseApiError,
    fetch_order_detail,
    fetch_orders_in_range,
    refresh_access_token,
    update_env_value,
)

# JST固定（設計書 §6 に準拠）
JST = timezone(timedelta(hours=9))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "daily"
ENV_PATH = PROJECT_ROOT / ".env"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BASE API から指定日の注文を取得")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="取得する日付（YYYY-MM-DD）。省略時は前日（JST）。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="既存の data/daily/YYYY-MM-DD.json があっても上書きする。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ファイル保存せず、取得結果を標準出力に表示するだけ。",
    )
    return parser.parse_args()


def determine_target_date(arg_date: str | None) -> date:
    """取得対象日を決定する。引数省略時は JST 基準の前日。"""
    if arg_date:
        return datetime.strptime(arg_date, "%Y-%m-%d").date()
    today_jst = datetime.now(JST).date()
    return today_jst - timedelta(days=1)


def jst_day_range_str(target: date) -> tuple[str, str]:
    """指定日の JST 0:00 〜 23:59:59 を BASE API 互換の文字列で返す。

    BASE API の start_ordered / end_ordered は "YYYY-MM-DD HH:MM:SS" 形式を期待する。
    """
    return (
        f"{target.isoformat()} 00:00:00",
        f"{target.isoformat()} 23:59:59",
    )


def normalize_order(order: dict) -> dict:
    """BASE API /1/orders/detail のレスポンス（detail["order"]）を daily JSON 用に整形する。

    /1/orders（リスト）は商品明細・配送先を返さないため、必ず詳細レスポンスを渡すこと。
    """
    # 注文時刻（UNIX秒 → ISO形式 JST）
    ordered_unix = order.get("ordered") or 0
    ordered_at = (
        datetime.fromtimestamp(int(ordered_unix), JST).isoformat()
        if ordered_unix
        else ""
    )

    # 配送先都道府県：order_receiver優先、無ければトップレベルのprefecture
    receiver = order.get("order_receiver") or {}
    shipping_area = receiver.get("prefecture") or order.get("prefecture") or ""

    # 商品明細
    items = []
    for it in order.get("order_items", []) or []:
        items.append({
            "name": it.get("title", ""),
            "quantity": int(it.get("amount") or 0),
            "unitPrice": int(it.get("price") or 0),
        })

    return {
        "orderId": order.get("unique_key", ""),
        "orderedAt": ordered_at,
        "totalAmount": int(order.get("total") or 0),
        "shippingArea": shipping_area,
        "items": items,
    }


def build_daily_payload(target: date, detailed_orders: list[dict]) -> dict:
    """daily JSON のペイロードを組み立てる。

    detailed_orders は normalize_order() 済の注文リスト。
    """
    total_sales = sum(o["totalAmount"] for o in detailed_orders)
    return {
        "date": target.isoformat(),
        "fetchedAt": datetime.now(JST).isoformat(timespec="seconds"),
        "orderCount": len(detailed_orders),
        "totalSales": total_sales,
        "orders": detailed_orders,
    }


def save_daily(payload: dict, target: date, force: bool) -> Path:
    """data/daily/YYYY-MM-DD.json に保存する。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{target.isoformat()}.json"

    if out_path.exists() and not force:
        raise FileExistsError(
            f"{out_path} はすでに存在します。上書きする場合は --force を付けてください。"
        )

    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return out_path


def main() -> int:
    args = parse_args()

    if not ENV_PATH.exists():
        print("エラー: .env がありません。先に oauth_init.py を実行してください。")
        return 1
    load_dotenv(ENV_PATH)

    client_id = os.getenv("BASE_CLIENT_ID", "").strip()
    client_secret = os.getenv("BASE_CLIENT_SECRET", "").strip()
    refresh_token = os.getenv("BASE_REFRESH_TOKEN", "").strip()
    if not (client_id and client_secret and refresh_token):
        print("エラー: .env に BASE_CLIENT_ID / BASE_CLIENT_SECRET / BASE_REFRESH_TOKEN が必要です。")
        return 1

    target = determine_target_date(args.date)
    start_str, end_str = jst_day_range_str(target)

    print("=" * 60)
    print(f" 取得対象: {target.isoformat()} (JST)")
    print(f" 期間: {start_str} ~ {end_str}")
    print("=" * 60)

    # access_token 取得
    print("\naccess_token を取得中...")
    try:
        access_token, new_refresh, expires_in = refresh_access_token(
            client_id, client_secret, refresh_token
        )
    except BaseApiError as e:
        print(f"認証失敗: {e}")
        return 1
    print(f"  → 取得成功（有効期限 {expires_in} 秒）")

    # トークンローテーションが発生した場合は .env を更新
    if new_refresh and new_refresh != refresh_token:
        update_env_value("BASE_REFRESH_TOKEN", new_refresh)
        print("  → 新しい refresh_token を .env に保存しました（ローテーション対応）")

    # 注文一覧取得（slim なリスト）
    print("\n注文一覧を取得中...")
    try:
        order_summaries = fetch_orders_in_range(access_token, start_str, end_str)
    except BaseApiError as e:
        print(f"取得失敗: {e}")
        return 1
    print(f"  → {len(order_summaries)} 件")

    # 各注文の詳細（商品明細・配送先）を取得して整形
    detailed: list[dict] = []
    if order_summaries:
        print("\n各注文の詳細を取得中...")
        for i, summary in enumerate(order_summaries, 1):
            unique_key = summary.get("unique_key")
            if not unique_key:
                print(f"  [{i}/{len(order_summaries)}] unique_key が無いためスキップ")
                continue
            try:
                detail_resp = fetch_order_detail(access_token, unique_key)
            except BaseApiError as e:
                print(f"  [{i}/{len(order_summaries)}] 詳細取得失敗 ({unique_key}): {e}")
                continue
            order_obj = detail_resp.get("order", {})
            detailed.append(normalize_order(order_obj))
            print(f"  [{i}/{len(order_summaries)}] {unique_key} ¥{order_obj.get('total', 0):,}")

    payload = build_daily_payload(target, detailed)

    if args.dry_run:
        print("\n[dry-run] 以下を保存せず表示のみ:\n")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        out_path = save_daily(payload, target, args.force)
    except FileExistsError as e:
        print(f"\n{e}")
        return 1

    print(f"\n保存しました: {out_path}")
    print(f"  注文件数: {payload['orderCount']}")
    print(f"  売上合計: ¥{payload['totalSales']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
