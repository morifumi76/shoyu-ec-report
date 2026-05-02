# yamamo-ec-report

## 概要
森田醤油醸造元のBASE ECショップから売上データを毎日蓄積し、月次レポート（HTML）を毎月1日に自動生成してGitHub Pagesで公開する自動化ツール。

## 技術スタック
- 言語: Python 3.11+（データ取得・集計スクリプト）
- フロントエンド: HTML + Tailwind CSS（CDN版）+ Vanilla JavaScript
- CI/CD: GitHub Actions（毎日取得ジョブ + 月次生成ジョブの2系統）
- デプロイ先: GitHub Pages
- AI: GitHub Models（月次AI分析コメント生成・予定）

## フォルダ構成
- `docs/specs/` : 設計書・仕様書（現行は v1.2）
- `scripts/` : Python スクリプト群（今後追加）
  - `oauth_init.py` : 初回認証（ローカル1回のみ）
  - `fetch_daily.py` : 前日分データ取得
  - `generate_monthly.py` : 月次集計＋latest.json生成
  - `ai_comment.py` : AI分析コメント生成
- `data/` : データ保管（今後追加）
  - `daily/YYYY-MM-DD.json` : 日次生データ
  - `latest.json` : index.htmlが読む最新月次データ
  - `archive/YYYY-MM.json` : 過去月次バックアップ
- `.github/workflows/` : GitHub Actions 定義（今後追加）
- `index.html` : レポートUI（ルート直下）
- `sample-data.json` : 開発用ダミーデータ
- `yamamo-rogo.png` : ロゴ画像
- `starter/` : 旧テンプレ残骸（.gitignoreで除外済み・将来要否判断）

## このプロジェクト固有のルール
- 設計書（`docs/specs/yamamo-ec-report｜最終設計書 v1.2.md`）に従って実装する。差分が生じたら**設計書を先に更新**してから実装を変更する。
- 既存ファイル（`index.html` / `sample-data.json` / `yamamo-rogo.png`）は不用意に上書きしない。
- `main` ブランチへの直接pushは禁止。必ず feature ブランチ + PR 方式で進める。
- 削除系コマンド（`rm -rf` 等）は一切使わない。
- APIキー等の秘密情報は `.env` で管理し、絶対にコミットしない。
- マイルストーン（M0〜M7）単位で「計画提示 → 確認 → 実装 → 動作確認」のサイクルを回す。次のマイルストーンに進む前に必ず確認を取る。

## 主要な外部サービス
- BASE（EC基盤）: OAuth 2.0 で API 利用。Secrets に `BASE_CLIENT_ID` / `BASE_CLIENT_SECRET` / `BASE_REFRESH_TOKEN` を登録。
- GitHub Actions: 毎日 09:00 JST でデータ取得、毎月1日 10:00 JST でレポート生成。
- GitHub Models: AI分析コメント生成に使用（予定）。
- GitHub Pages: レポート公開先。

## 現在の状態
- M0 実施中（2026-04-24〜）
  - `starter/` 整理、設計書v1.1化、README更新、.gitignore作成、CLAUDE.md作成
- 次はM1（BASE開発者アプリ登録・ユーザー作業）
