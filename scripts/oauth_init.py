"""
BASE API OAuth 2.0 初回認証スクリプト

使い方:
    python scripts/oauth_init.py

このスクリプトを実行すると:
  1. ブラウザが自動で開き、BASEの認可画面が表示される
  2. ユーザーが「許可」をクリックすると localhost:8080/callback にリダイレクトされる
  3. 受け取った認可コードを access_token / refresh_token と交換する
  4. refresh_token を .env に書き込む（次回以降の自動取得に使う）

実行は通常1回だけ。ログインユーザーがアプリを再認可した場合や、
refresh_token を失効させたい場合のみ再実行する。
"""

from __future__ import annotations

import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

# BASE API のエンドポイント
AUTHORIZE_URL = "https://api.thebase.in/1/oauth/authorize"
TOKEN_URL = "https://api.thebase.in/1/oauth/token"

# 取得するスコープ（権限）。設計書 §6 に基づく
SCOPES = ["read_users", "read_orders", "read_items"]

# 実行ディレクトリではなく、このスクリプトのプロジェクトルートを基準にする
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"


class CallbackHandler(BaseHTTPRequestHandler):
    """localhost:PORT/callback に飛んでくる認可コードを受け取るハンドラ。"""

    # クラス変数として、受け取った code を保持する
    received_code: Optional[str] = None
    received_error: Optional[str] = None

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler の規約名)
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # /callback 以外には反応しない
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        if "error" in params:
            CallbackHandler.received_error = params["error"][0]
            body = self._html("認可エラー", f"エラー: {CallbackHandler.received_error}")
            self.send_response(400)
        elif "code" in params:
            CallbackHandler.received_code = params["code"][0]
            body = self._html(
                "認可成功",
                "認可コードを受け取りました。<br>このタブは閉じて、ターミナルに戻ってください。",
            )
            self.send_response(200)
        else:
            body = self._html("不明なリクエスト", "code も error もありません。")
            self.send_response(400)

        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # 標準のアクセスログを抑制（うるさいので）
        return

    @staticmethod
    def _html(title: str, message: str) -> str:
        return (
            f"<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
            f"<title>{title}</title></head><body style='font-family:sans-serif;padding:2em;'>"
            f"<h1>{title}</h1><p>{message}</p></body></html>"
        )


def build_authorize_url(client_id: str, redirect_uri: str) -> str:
    """BASE の認可URLを組み立てる。"""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> dict:
    """認可コードを access_token / refresh_token に交換する。"""
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"トークン取得に失敗しました: HTTP {response.status_code}\n{response.text}"
        )
    return response.json()


def update_env_refresh_token(refresh_token: str) -> None:
    """.env の BASE_REFRESH_TOKEN 行を上書き（無ければ追記）する。"""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_line = f"BASE_REFRESH_TOKEN={refresh_token}"
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith("BASE_REFRESH_TOKEN="):
            lines[i] = new_line
            replaced = True
            break
    if not replaced:
        lines.append(new_line)

    # ファイル末尾の改行を保証
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    # .env を読み込む（無ければエラー）
    if not ENV_PATH.exists():
        print("エラー: .env ファイルが見つかりません。")
        print(f"  {ENV_PATH} に .env.example をコピーして、")
        print("  BASE_CLIENT_ID と BASE_CLIENT_SECRET を記入してください。")
        return 1

    load_dotenv(ENV_PATH)
    client_id = os.getenv("BASE_CLIENT_ID", "").strip()
    client_secret = os.getenv("BASE_CLIENT_SECRET", "").strip()
    port = int(os.getenv("OAUTH_CALLBACK_PORT", "8080"))

    if not client_id or not client_secret:
        print("エラー: .env の BASE_CLIENT_ID / BASE_CLIENT_SECRET が空です。")
        return 1

    redirect_uri = f"http://localhost:{port}/callback"
    auth_url = build_authorize_url(client_id, redirect_uri)

    print("=" * 60)
    print(" BASE OAuth 初回認証")
    print("=" * 60)
    print(f"\nコールバックURL: {redirect_uri}")
    print("（BASE Developers のアプリ設定と一致している必要があります）\n")
    print("ブラウザを開きます。BASEで「許可」をクリックしてください。")
    print(f"もしブラウザが開かない場合は、以下のURLを手動で開いてください:\n  {auth_url}\n")

    # ローカルサーバーを先に立ち上げてから、ブラウザを開く
    server = HTTPServer(("localhost", port), CallbackHandler)
    webbrowser.open(auth_url)

    print(f"localhost:{port} でコールバックを待機中... (Ctrl+C で中止)")
    try:
        # 1リクエスト処理したら抜ける（=コールバック受信したら抜ける）
        while CallbackHandler.received_code is None and CallbackHandler.received_error is None:
            server.handle_request()
    except KeyboardInterrupt:
        print("\n中止しました。")
        return 1
    finally:
        server.server_close()

    if CallbackHandler.received_error:
        print(f"\n認可エラー: {CallbackHandler.received_error}")
        return 1

    code = CallbackHandler.received_code
    assert code is not None
    print("\n認可コードを受信しました。トークンと交換します...")

    try:
        tokens = exchange_code_for_tokens(code, client_id, client_secret, redirect_uri)
    except RuntimeError as e:
        print(f"\n{e}")
        return 1

    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")

    if not refresh_token:
        print("\nエラー: レスポンスに refresh_token が含まれていません。")
        print(f"レスポンス: {tokens}")
        return 1

    update_env_refresh_token(refresh_token)

    print("\n" + "=" * 60)
    print(" 認証成功！")
    print("=" * 60)
    print(f"  refresh_token を {ENV_PATH} に保存しました。")
    print(f"  access_token (有効期限 {expires_in} 秒): {access_token[:20]}...")
    print("\n後ほどM6で、この refresh_token を GitHub Secrets に登録します。")
    print("（変数名: BASE_REFRESH_TOKEN）\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
