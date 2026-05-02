# yamamo-ec-report

森田醤油醸造元のBASE ECショップから売上データを**毎日蓄積**し、**月次レポート（HTML）を毎月1日に自動生成**してGitHub Pagesで公開する自動化ツール。

## 概要

| 項目 | 内容 |
|---|---|
| ソース元 | BASE（OAuth 2.0 API） |
| データ取得頻度 | 毎日 09:00 JST（前日分） |
| レポート生成頻度 | 毎月1日 10:00 JST（前月分） |
| 処理場所 | GitHub Actions |
| 出力先 | GitHub Pages（HTMLレポート） |
| AI分析 | GitHub Models で月次コメント生成 |

## 2系統のワークフロー

```
[A] 毎日 09:00 JST  → データ取得ジョブ（fetch-daily.yml）
    BASE API → data/daily/YYYY-MM-DD.json に追記

[B] 毎月 1日 10:00 JST → 月次レポート生成ジョブ（generate-monthly.yml）
    前月分 daily/*.json を集計
    → data/latest.json に書き出し
    → AI分析コメント生成
    → index.html がlatest.jsonを読んで描画
    → git commit & push（GitHub Pages自動デプロイ）
```

## 技術スタック

- 言語: Python 3.11+
- フロントエンド: HTML + Tailwind CSS（CDN版）+ Vanilla JavaScript
- CI/CD: GitHub Actions
- デプロイ先: GitHub Pages
- AI: GitHub Models（`actions/ai-inference` 利用予定）

## フォルダ構成

```
yamamo-ec-report/
├── .github/workflows/
│   ├── fetch-daily.yml         # [A] 毎日データ取得
│   └── generate-monthly.yml    # [B] 月次レポート生成
├── scripts/
│   ├── oauth_init.py           # 初回認証（ローカル1回のみ）
│   ├── fetch_daily.py          # BASE APIで前日分を取得
│   ├── generate_monthly.py     # 月次集計＋latest.json生成
│   └── ai_comment.py           # AI分析コメント生成
├── data/
│   ├── daily/YYYY-MM-DD.json   # 日次生データ
│   ├── latest.json             # index.htmlが読む最新月次データ
│   ├── products.json           # 商品マスタキャッシュ
│   └── archive/YYYY-MM.json    # 過去月次バックアップ
├── docs/specs/                 # 設計書（v1.2）
├── index.html                  # レポートUI
├── sample-data.json            # 開発用ダミーデータ
├── yamamo-rogo.png             # ロゴ画像
├── .env.example
├── .gitignore
├── requirements.txt
├── CLAUDE.md                   # プロジェクト固有ルール
└── README.md
```

※ `.github/workflows/`, `scripts/`, `data/`, `.env.example`, `requirements.txt` はM2以降のマイルストーンで順次追加予定。

## セットアップ（M1以降に有効）

### 1. BASE開発者アプリ登録（手動・1回のみ）
[BASE Developers](https://developers.thebase.in/) でアプリを登録し、`client_id` と `client_secret` を取得する。

### 2. 初回OAuth認証（ローカル・1回のみ）

```bash
pip install -r requirements.txt
cp .env.example .env   # client_id / client_secret を記入
python scripts/oauth_init.py
```

ブラウザが開き、BASEアカウントで認可すると `refresh_token` が表示される。

### 3. GitHub Secrets に登録

| Secret名 | 用途 |
|---|---|
| `BASE_CLIENT_ID` | BASE API クライアントID |
| `BASE_CLIENT_SECRET` | BASE API シークレット |
| `BASE_REFRESH_TOKEN` | 上記で取得したリフレッシュトークン |
| `REPO_PAT` | refresh_token自動更新用（任意） |

## 開発ルール

- 設計書（`docs/specs/yamamo-ec-report｜最終設計書 v1.2.md`）に従って実装する
- `main` ブランチへの直pushは禁止。feature ブランチ + PR 方式
- APIキー等は `.env` で管理し、絶対にコミットしない（`.gitignore` 済）
- マイルストーン単位で「計画提示 → 確認 → 実装 → 動作確認」のサイクル

## マイルストーン

| # | 内容 | 状態 |
|---|---|---|
| M0 | starter/ 整理、設計書v1.1化、README更新、.gitignore作成 | ✅ 完了 |
| M1 | BASE開発者アプリ登録（手動） | ✅ 完了 |
| M2 | `oauth_init.py` 実装・ローカル認証 | ✅ 完了 |
| M3a | 設計書v1.2化、`sample-data.json` ダミー投入 | 🚧 進行中 |
| M3b | `fetch_daily.py` 実装 | 未着手 |
| M4 | `generate_monthly.py` + `ai_comment.py` 実装 | 未着手 |
| M5 | `index.html` の軽微リファクタ（fetch化） | 未着手 |
| M6 | GitHub Actions 両ワークフロー設定 | 未着手 |
| M7 | 本番検証 | 未着手 |

## ライセンス

Private / 森田醤油醸造元

## 作者

森田文弥 / ジョウホウソース株式会社
