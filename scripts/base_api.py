"""
BASE API 共通処理モジュール

- access_token の取得（refresh_token から）
- リトライ付きAPI呼び出し（429/5xx で指数バックオフ最大3回）
- 注文一覧の自動ページネーション取得
- .env への refresh_token 上書き保存

oauth_init.py と fetch_daily.py / generate_monthly.py から共通利用される。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

# BASE API エンドポイント
TOKEN_URL = "https://api.thebase.in/1/oauth/token"
ORDERS_URL = "https://api.thebase.in/1/orders"
ITEMS_URL = "https://api.thebase.in/1/items"

# プロジェクトルート（このファイルの2つ上）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

# リトライ設定
MAX_RETRIES = 3
BACKOFF_BASE_SEC = 2  # 1回目=2秒、2回目=4秒、3回目=8秒


class BaseApiError(RuntimeError):
    """BASE API 呼び出しに失敗したときに投げる例外。"""


def update_env_value(key: str, value: str) -> None:
    """.env の指定キーを上書き（無ければ追記）する。

    BASE_REFRESH_TOKEN の自動更新（トークンローテーション対応）等で使う。
    """
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_line = f"{key}={value}"
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> tuple[str, Optional[str], int]:
    """refresh_token を使って access_token を新規発行する。

    BASE API はトークンローテーション方式の可能性があるため、
    レスポンスに新しい refresh_token が含まれる場合は呼び出し側で .env に保存する。

    Returns:
        (access_token, 新しい refresh_token または None, expires_in 秒)
    """
    response = _post_with_retry(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
    payload = response.json()
    access_token = payload.get("access_token")
    new_refresh = payload.get("refresh_token")  # ローテーションされた場合のみ
    expires_in = int(payload.get("expires_in", 0))

    if not access_token:
        raise BaseApiError(f"access_token がレスポンスにありません: {payload}")

    return access_token, new_refresh, expires_in


def get_with_retry(url: str, access_token: str, params: Optional[dict] = None) -> dict:
    """access_token 付きで GET し、JSON を返す。429/5xx は指数バックオフでリトライ。"""
    headers = {"Authorization": f"Bearer {access_token}"}
    response = _request_with_retry("GET", url, headers=headers, params=params)
    return response.json()


def fetch_orders_in_range(
    access_token: str,
    start_str: str,
    end_str: str,
    page_size: int = 20,
) -> list[dict]:
    """指定期間の注文を全件取得する。ページネーション自動。

    BASE API の start_ordered / end_ordered は "YYYY-MM-DD HH:MM:SS" 文字列形式を期待する
    （Unix秒では効かない実態を 2026-05-03 動作確認済）。
    BASE API の limit 上限は 20。注文が少ない日は 1 リクエストで終わる。
    """
    all_orders: list[dict] = []
    offset = 0

    while True:
        payload = get_with_retry(
            ORDERS_URL,
            access_token,
            params={
                "start_ordered": start_str,
                "end_ordered": end_str,
                "limit": page_size,
                "offset": offset,
                "order": "asc",
            },
        )
        orders = payload.get("orders", [])
        all_orders.extend(orders)

        # 返ってきた件数が page_size 未満なら最終ページ
        if len(orders) < page_size:
            break
        offset += page_size

    return all_orders


def fetch_order_detail(access_token: str, unique_key: str) -> dict:
    """注文1件の詳細（商品明細・配送先含む）を取得する。

    /1/orders は商品明細・配送先を返さないため、注文ごとに本エンドポイントを
    別途呼んで補完する必要がある（2026-05-03 動作確認済）。

    Returns:
        BASE API のレスポンス全体（{"order": {...}} の形）
    """
    detail_url = f"{ORDERS_URL}/detail/{unique_key}"
    return get_with_retry(detail_url, access_token)


# ---- 内部関数 ----

def _request_with_retry(
    method: str,
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    data: Optional[dict] = None,
) -> requests.Response:
    """429/5xx で指数バックオフリトライ。それ以外のエラーはすぐ例外化する。"""
    last_error: Optional[str] = None
    for attempt in range(MAX_RETRIES + 1):
        response = requests.request(
            method, url, headers=headers, params=params, data=data, timeout=30
        )

        if response.status_code == 200:
            return response

        # 4xx（429除く）は再試行しない
        if 400 <= response.status_code < 500 and response.status_code != 429:
            raise BaseApiError(
                f"API エラー: HTTP {response.status_code}\n"
                f"URL: {url}\n"
                f"レスポンス: {response.text[:500]}"
            )

        # 429 / 5xx はリトライ対象
        last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        if attempt < MAX_RETRIES:
            wait = BACKOFF_BASE_SEC * (2 ** attempt)
            print(f"  → リトライ {attempt + 1}/{MAX_RETRIES}（{wait}秒待機）: {last_error}")
            time.sleep(wait)

    raise BaseApiError(f"リトライ上限({MAX_RETRIES}回)に達しました: {last_error}")


def _post_with_retry(url: str, data: dict) -> requests.Response:
    """トークン取得用 POST。Content-Type は requests が自動設定。"""
    return _request_with_retry("POST", url, data=data)
