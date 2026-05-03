"""
月次集計スクリプト

data/daily/YYYY-MM-*.json を集計し、設計書 v1.2 §4 の latest.json 構造に整形して
data/latest.json と data/archive/YYYY-MM.json に書き出す。

使い方:
    python scripts/generate_monthly.py                        # 前月分（デフォルト）
    python scripts/generate_monthly.py --month 2026-04
    python scripts/generate_monthly.py --month 2026-04 --with-ai      # AIコメント込み
    python scripts/generate_monthly.py --month 2026-04 --force        # archive上書き
    python scripts/generate_monthly.py --month 2026-04 --no-latest    # latest.json更新せず
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# JST固定（設計書 §6）
JST = timezone(timedelta(hours=9))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = PROJECT_ROOT / "data" / "daily"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive"
LATEST_PATH = PROJECT_ROOT / "data" / "latest.json"
MONTHS_INDEX_PATH = PROJECT_ROOT / "data" / "months.json"

# Y軸スケール自動計算の切り上げ単位（設計書 §4）
LEFT_AXIS_UNIT = 5000      # 日別売上（円）
RIGHT_AXIS_UNIT = 50000    # 累積売上（円）
LEFT_AXIS_MIN = 5000
RIGHT_AXIS_MIN = 50000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="月次集計＋latest.json生成")
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="対象月 YYYY-MM。省略時は前月（JST）。",
    )
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="AIコメントを生成して aiComment に埋め込む（GITHUB_TOKEN 必要）。",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="data/archive/YYYY-MM.json を上書きする。",
    )
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="data/latest.json を更新しない（archiveのみ書き出し）。",
    )
    return parser.parse_args()


def determine_target_month(arg_month: str | None) -> str:
    """対象月（YYYY-MM）を決定する。省略時は JST 基準の前月。"""
    if arg_month:
        # 形式チェック
        datetime.strptime(arg_month, "%Y-%m")
        return arg_month
    today = datetime.now(JST).date()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return last_of_prev_month.strftime("%Y-%m")


def load_daily_files(target_month: str) -> list[dict]:
    """data/daily/YYYY-MM-*.json を全件読み込む。空ファイルでも含める。"""
    files = sorted(DAILY_DIR.glob(f"{target_month}-*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def collect_all_orders(daily_data: list[dict]) -> list[dict]:
    """日次データを月内の全注文配列にフラット化する。"""
    orders: list[dict] = []
    for d in daily_data:
        orders.extend(d.get("orders", []))
    return orders


def compute_summary(orders: list[dict], target_month: str) -> dict:
    """月次サマリ（4枚カード分）を算出する。"""
    total_sales = sum(o["totalAmount"] for o in orders)
    order_count = len(orders)
    average = round(total_sales / order_count) if order_count else 0
    return {
        "totalSales": total_sales,
        "orderCount": order_count,
        "averageOrderValue": average,
        "monthOverMonthPct": compute_mom_pct(target_month, total_sales),
    }


def compute_mom_pct(target_month: str, this_total: int) -> float | None:
    """前月の archive と比較して前月比%を算出。前月データが無ければ None。"""
    year, month = map(int, target_month.split("-"))
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    prev_path = ARCHIVE_DIR / f"{prev_year:04d}-{prev_month:02d}.json"
    if not prev_path.exists():
        return None
    prev_data = json.loads(prev_path.read_text(encoding="utf-8"))
    prev_total = prev_data.get("summary", {}).get("totalSales", 0)
    if not prev_total:
        return None
    return round((this_total - prev_total) / prev_total * 100, 1)


def compute_daily_sales(daily_data: list[dict], target_month: str) -> list[dict]:
    """その月の各日について {day, sales} の配列を組み立てる。"""
    year, month = map(int, target_month.split("-"))
    days_in_month = calendar.monthrange(year, month)[1]

    by_day: dict[int, int] = {}
    for d in daily_data:
        try:
            day = int(d["date"].split("-")[2])
        except (KeyError, ValueError, IndexError):
            continue
        by_day[day] = d.get("totalSales", 0)

    return [
        {"day": d, "sales": by_day.get(d, 0)}
        for d in range(1, days_in_month + 1)
    ]


def compute_chart_scale(daily_sales: list[dict], total_sales: int) -> dict:
    """Y軸最大値を自動計算する（設計書 §4 のルール）。"""
    max_daily = max((d["sales"] for d in daily_sales), default=0)
    left_max = max(
        LEFT_AXIS_MIN,
        math.ceil(max_daily * 1.2 / LEFT_AXIS_UNIT) * LEFT_AXIS_UNIT,
    )
    right_max = max(
        RIGHT_AXIS_MIN,
        math.ceil(total_sales * 1.1 / RIGHT_AXIS_UNIT) * RIGHT_AXIS_UNIT,
    )
    return {"leftMax": left_max, "rightMax": right_max}


def compute_product_ranking(orders: list[dict], total_sales: int) -> list[dict]:
    """商品名でグルーピングし、売上降順のランキングを作る。

    sharePct = 商品売上 / 月間売上合計 × 100（小数1桁）。
    送料を含む totalSales が分母になるため、足し合わせは100%未満になり得る。
    """
    by_name: dict[str, dict] = {}
    for o in orders:
        for item in o.get("items", []):
            name = item.get("name") or "(名称不明)"
            qty = int(item.get("quantity") or 0)
            unit_price = int(item.get("unitPrice") or 0)
            sales = qty * unit_price
            if name not in by_name:
                by_name[name] = {"quantity": 0, "sales": 0}
            by_name[name]["quantity"] += qty
            by_name[name]["sales"] += sales

    sorted_items = sorted(by_name.items(), key=lambda kv: kv[1]["sales"], reverse=True)

    ranking: list[dict] = []
    for rank, (name, data) in enumerate(sorted_items, start=1):
        share = (
            round(data["sales"] / total_sales * 100, 1) if total_sales else 0.0
        )
        ranking.append({
            "rank": rank,
            "name": name,
            "quantity": data["quantity"],
            "sales": data["sales"],
            "sharePct": share,
        })
    return ranking


def compute_recent_orders(orders: list[dict], limit: int = 10) -> list[dict]:
    """月内の注文を新しい順に最大 limit 件返す。"""
    sorted_orders = sorted(
        orders,
        key=lambda o: o.get("orderedAt", ""),
        reverse=True,
    )
    result: list[dict] = []
    for o in sorted_orders[:limit]:
        items = o.get("items", []) or []
        # 商品が複数あるときは「先頭商品 ほかN点」と表記
        if len(items) == 1:
            product_name = items[0].get("name", "")
        elif len(items) > 1:
            product_name = f"{items[0].get('name', '')} ほか{len(items) - 1}点"
        else:
            product_name = ""
        total_qty = sum(int(item.get("quantity") or 0) for item in items)

        date_label = ""
        ordered_at = o.get("orderedAt", "")
        if ordered_at:
            try:
                dt = datetime.fromisoformat(ordered_at)
                date_label = f"{dt.month}/{dt.day}"
            except ValueError:
                pass

        result.append({
            "date": date_label,
            "orderNumber": o.get("orderId", ""),
            "productName": product_name,
            "quantity": total_qty,
            "amount": int(o.get("totalAmount") or 0),
            "shippingArea": o.get("shippingArea", ""),
        })
    return result


def format_month_label(target_month: str) -> str:
    year, month = target_month.split("-")
    return f"{year}年{int(month)}月"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def rebuild_months_index() -> dict:
    """data/archive/ をスキャンして data/months.json を作り直す。

    index.html の月プルダウン用。
    GitHub Pages（静的サイト）ではディレクトリ列挙ができないため、
    利用可能な月の一覧を別ファイルとして公開する必要がある。
    """
    months: list[str] = []
    for f in ARCHIVE_DIR.glob("*.json"):
        name = f.stem  # "2026-04"
        # YYYY-MM 形式チェック
        try:
            datetime.strptime(name, "%Y-%m")
            months.append(name)
        except ValueError:
            continue
    months.sort()  # 昇順
    payload = {
        "available": months,
        "latest": months[-1] if months else None,
    }
    write_json(MONTHS_INDEX_PATH, payload)
    return payload


def main() -> int:
    args = parse_args()

    try:
        target_month = determine_target_month(args.month)
    except ValueError:
        print(f"エラー: --month は YYYY-MM 形式で指定してください。受け取り: {args.month}")
        return 1

    daily_data = load_daily_files(target_month)
    if not daily_data:
        print(f"エラー: data/daily/{target_month}-*.json が見つかりません。")
        print("  fetch_daily.py で日次データを取得してください。")
        return 1

    print(f"対象月: {target_month}")
    print(f"日次ファイル: {len(daily_data)} 件")

    # 集計
    orders = collect_all_orders(daily_data)
    summary = compute_summary(orders, target_month)
    daily_sales = compute_daily_sales(daily_data, target_month)
    chart_scale = compute_chart_scale(daily_sales, summary["totalSales"])
    product_ranking = compute_product_ranking(orders, summary["totalSales"])
    recent_orders = compute_recent_orders(orders, limit=10)

    payload = {
        "month": target_month,
        "monthLabel": format_month_label(target_month),
        "generatedAt": datetime.now(JST).date().isoformat(),
        "summary": summary,
        "dailySales": daily_sales,
        "chartScale": chart_scale,
        "productRanking": product_ranking,
        "recentOrders": recent_orders,
        "aiComment": "",
    }

    # AIコメント（任意）
    if args.with_ai:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from ai_comment import generate_comment  # noqa: E402

        print("\nAIコメントを生成中...")
        try:
            payload["aiComment"] = generate_comment(payload)
            print(f"  → 生成完了（{len(payload['aiComment'])}字）")
        except Exception as e:
            print(f"  → 失敗: {e}")
            print("  → aiComment は空のままにします")

    # archive 書き出し（既存なら --force 必須）
    archive_path = ARCHIVE_DIR / f"{target_month}.json"
    if archive_path.exists() and not args.force:
        print(f"\nエラー: {archive_path} はすでに存在します。--force で上書きしてください。")
        return 1
    write_json(archive_path, payload)

    # latest.json 書き出し（常に上書き、ただし --no-latest 指定時はスキップ）
    if not args.no_latest:
        write_json(LATEST_PATH, payload)

    # months.json を再構築（index.htmlの月プルダウン用）
    months_index = rebuild_months_index()

    # サマリ表示
    print("\n保存しました:")
    print(f"  {archive_path}")
    if not args.no_latest:
        print(f"  {LATEST_PATH}")
    print(f"  {MONTHS_INDEX_PATH} （利用可能な月: {len(months_index['available'])}件）")
    print(f"  売上合計: ¥{summary['totalSales']:,}")
    print(f"  注文件数: {summary['orderCount']}")
    print(f"  平均単価: ¥{summary['averageOrderValue']:,}")
    mom = summary["monthOverMonthPct"]
    print(f"  前月比: {f'{mom}%' if mom is not None else '— (前月データなし)'}")
    print(f"  商品ランキング: {len(product_ranking)} 種")
    print(f"  注文詳細: {len(recent_orders)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
