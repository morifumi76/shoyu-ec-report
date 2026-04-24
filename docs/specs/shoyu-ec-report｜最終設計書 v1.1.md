# shoyu-ec-report｜最終設計書 v1.1

## 改訂履歴
- v1.0 (2026-04-24) 初版。前提に「index.html は sample-data.json を読んで surge.sh で動作中」と記載。
- v1.1 (2026-04-24) §4 を実態に合わせて訂正。実際は index.html にデータがハードコードされており、sample-data.json は空。fetch() 化する方針に変更。§9 M3 の文言も微修正。

## 1. システム概要
森田醤油醸造元のBASE ECショップから売上データを**毎日蓄積**し、
**月次レポート（HTML）を毎月1日に自動生成**、GitHub Pagesで公開する。

## 2. 2系統のワークフロー
─────────────────────────────────────
[A] 毎日 09:00 JST  → データ取得ジョブ
    BASE API → data/daily/YYYY-MM-DD.json に追記
    （保険として毎日取得。API障害時も影響最小化）

[B] 毎月 1日 10:00 JST → 月次レポート生成ジョブ
    前月分 daily/*.json を集計
    → data/latest.json に書き出し
    → AI分析コメントをClaude API等で生成
    → index.html がlatest.jsonを読んで描画
    → git commit & push（GitHub Pages自動デプロイ）
─────────────────────────────────────

## 3. リポジトリ構成（既存を尊重）
shoyu-ec-report/
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
├── index.html                  # 既存を活用（M5で軽微にリファクタしfetch化）
├── sample-data.json            # 既存（現状は空。M3で開発用ダミーを投入）
├── yamamo-rogo.png             # 既存
├── starter/                    # ※M0で .gitignore で除外済み（将来要否判断）
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md                   # 「月次」→「日次蓄積＋月次レポート」に更新

## 4. フロントエンドとデータの接続方式（v1.1で訂正）

### 現状の実態
- 既存の `index.html` は **データがJS内にハードコード**されている（完成イメージ）。
- `sample-data.json` は**中身が空（`{}`）**であり、`index.html` は一切 `fetch()` していない。
- surge.sh へのデプロイ実績は確認できず、現時点は単体HTMLの状態。

### 方針
- `index.html` を**軽微にリファクタ**し、`fetch('data/latest.json')` で外部JSONを読み込む方式へ変更する（M5で実施）。
- `data/latest.json` のキー構造は、**既存 index.html のハードコード値の形に合わせて設計**する（M3で確定）。
- `sample-data.json` は開発用ダミーとして、`latest.json` と同一構造で埋め直す（M3で対応）。
- 既存デザイン（月次サマリ／日別推移グラフ／商品ランキング／注文詳細／AIコメント）は全部保持。

### latest.json に必要なキー（暫定・M3で確定）
- `month`（対象年月、例: `"2026-03"`）
- `summary`: 月間売上合計、注文件数、平均単価、前月比%
- `dailySales`: 日別売上の配列（31日分）
- `productRanking`: 商品名・販売数・売上金額・構成比 のリスト
- `recentOrders`: 直近10件（注文日・注文番号・商品名・数量・金額・配送先）
- `aiComment`: AI分析コメント本文（200字程度）

## 5. AI分析コメント生成方式
選択肢：
  案① GitHub Models（推奨・無料枠あり）
      - GitHub Actions内で `actions/ai-inference` や models API を呼び出す
      - GITHUB_TOKEN で認証、追加セットアップ不要
      - gpt-4o-mini 等で月1回呼び出し → ほぼコスト0
  
  案② Anthropic Claude API（従量課金）
      - ANTHROPIC_API_KEY をSecretsに登録
      - Claude 3.5 Haiku で月1回 → 約$0.01/回
      - キミはClaude Proユーザーだけど、ProはAPI含まないので別課金

→ **案①（GitHub Models）を推奨**。キミの運用ポリシー（コスト抑制）に合致。

プロンプト骨子：
「前月データ（月間売上・前月比・商品別ランキング）を渡す
 → 200字程度で考察コメント生成
 → トーン：穏やかだが前向き、次月施策示唆を含む」

## 6. BASE API 利用仕様
- 認証：OAuth 2.0（Authorization Code Flow）
- 初回：oauth_init.py をローカル実行 → refresh_token取得
- 運用：GitHub Actions で refresh_token → access_token を都度取得
- エンドポイント：
  - GET /1/orders?start_ordered=前日0時&end_ordered=前日23:59:59
  - GET /1/items（商品マスタ、月次ジョブ時のみ更新）
- タイムゾーン：Asia/Tokyo（日付境界はJSTで判定）
- リトライ：429/5xx時は指数バックオフで最大3回

## 7. GitHub Secrets（登録必要）
- BASE_CLIENT_ID
- BASE_CLIENT_SECRET
- BASE_REFRESH_TOKEN
- REPO_PAT（refresh_token自動更新用・optional）

## 8. セキュリティ・運用
- .env は絶対コミットしない（.gitignore必須）
- mainブランチには Actions経由のみ書き込み（[skip ci]付与でループ回避）
- 手動再実行可能（workflow_dispatch トリガー併用）
- 失敗時はActionsのデフォルトメール通知のみ（将来拡張）

## 9. マイルストーン
M0: starter/ 中身整理（docs/specs/ 昇格、残りは .gitignore で除外）、README・CLAUDE.md整備
M1: BASE開発者アプリ登録（手動）← ユーザー作業
M2: oauth_init.py 実装・ローカル認証
M3: latest.json キー構造の**設計**（index.html表示項目から逆算）＋sample-data.json 開発用ダミー投入 ＋ fetch_daily.py 実装
M4: generate_monthly.py + ai_comment.py 実装
M5: index.html の軽微リファクタ（fetch('data/latest.json') 化）
M6: GitHub Actions 両ワークフロー設定
M7: 本番検証（手動トリガー → 翌月1日自動実行確認）

<!--
=============================================================
[v1.0 原文アーカイブ] 2026-04-24 時点の内容を参考保存
=============================================================

# shoyu-ec-report｜最終設計書 v1.0

## 1. システム概要
森田醤油醸造元のBASE ECショップから売上データを**毎日蓄積**し、
**月次レポート（HTML）を毎月1日に自動生成**、GitHub Pagesで公開する。

## 2. 2系統のワークフロー
─────────────────────────────────────
[A] 毎日 09:00 JST  → データ取得ジョブ
    BASE API → data/daily/YYYY-MM-DD.json に追記
    （保険として毎日取得。API障害時も影響最小化）

[B] 毎月 1日 10:00 JST → 月次レポート生成ジョブ
    前月分 daily/*.json を集計
    → data/latest.json に書き出し
    → AI分析コメントをClaude API等で生成
    → index.html がlatest.jsonを読んで描画
    → git commit & push（GitHub Pages自動デプロイ）
─────────────────────────────────────

## 3. リポジトリ構成（既存を尊重）
shoyu-ec-report/
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
├── index.html                  # 既存をそのまま活用
├── sample-data.json            # 既存（開発用に残す）
├── yamamo-rogo.png             # 既存
├── starter/                    # ※Cursor初回で中身確認・要ならリネーム
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md                   # 「月次」→「日次蓄積＋月次レポート」に更新

## 4. sample-data.json の構造を踏襲
既存の index.html は sample-data.json を読んで surge.sh で動作中。
→ latest.json は sample-data.json と**完全に同じキー構造**にする。
→ フロントエンド（index.html）の改修は最小限：読込先を latest.json に変更するのみ。
→ 既存デザイン（月次サマリ／日別推移グラフ／商品ランキング／注文詳細／AIコメント）全部保持。

## 5. AI分析コメント生成方式
（v1.1と同一のため省略）

## 6. BASE API 利用仕様
（v1.1と同一のため省略）

## 7. GitHub Secrets（登録必要）
（v1.1と同一のため省略）

## 8. セキュリティ・運用
（v1.1と同一のため省略）

## 9. マイルストーン
M0: starter/ 中身確認・必要に応じ整理
M1: BASE開発者アプリ登録（手動）← ユーザー作業
M2: oauth_init.py 実装・ローカル認証
M3: fetch_daily.py 実装・sample-data.json構造調査
M4: generate_monthly.py + ai_comment.py 実装
M5: index.html の読込先を latest.json に変更
M6: GitHub Actions 両ワークフロー設定
M7: 本番検証（手動トリガー → 翌月1日自動実行確認）
=============================================================
-->
