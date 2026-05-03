# yamamo-ec-report｜最終設計書 v1.3

## 改訂履歴
- v1.0 (2026-04-24) 初版。前提に「index.html は sample-data.json を読んで surge.sh で動作中」と記載。
- v1.1 (2026-04-24) §4 を実態に合わせて訂正。実際は index.html にデータがハードコードされており、sample-data.json は空。fetch() 化する方針に変更。§9 M3 の文言も微修正。
- v1.2 (2026-05-03)
  - プロジェクト名 `shoyu-ec-report` → `yamamo-ec-report` に変更（surge URLは新URL `yamamo-ec-report-6021.surge.sh` を本番、旧URL `shoyu-ec-report.surge.sh` をデモ用スナップショットとして併存）
  - §3 リポジトリ構成のルートを `yamamo-ec-report/` に変更
  - §4 latest.json のキー構造を **暫定 → 確定**（index.html 表示項目から逆算して全フィールド定義）
  - §5 AIコメントを **200字 → 300字**、4部構成（振り返り／好調点／課題／来月提案）に拡張
  - §9 マイルストーン M2完了反映、M3を3aと3bに分割
- v1.3 (2026-05-03)
  - §4 に **年度（4月〜翌3月）累計ビュー**用の `fiscal-YYYY.json` 構造を追加
  - §4 index.html に **月間/年間 タブUI**＋年度プルダウンを追加
  - §4 年間ビュー専用の **売上比率チャート**（横棒スタック）を追加。注文詳細は年間ビューでは非表示
  - §5 AIコメントに **年間版（年次振り返り・約400字）**を追加
  - §9 マイルストーン M3〜M5 完了反映、M5b（年間タブ）を追加

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

## 3. リポジトリ構成
yamamo-ec-report/
├── .github/workflows/
│   ├── fetch-daily.yml         # [A] 毎日データ取得
│   └── generate-monthly.yml    # [B] 月次レポート生成
├── scripts/
│   ├── oauth_init.py           # 初回認証（ローカル1回のみ）※M2 実装済
│   ├── fetch_daily.py          # BASE APIで前日分を取得 ※M3b
│   ├── generate_monthly.py     # 月次集計＋latest.json生成 ※M4
│   └── ai_comment.py           # AI分析コメント生成 ※M4
├── data/
│   ├── daily/YYYY-MM-DD.json   # 日次生データ
│   ├── latest.json             # index.htmlが読む最新月次データ
│   ├── products.json           # 商品マスタキャッシュ
│   └── archive/YYYY-MM.json    # 過去月次バックアップ
├── index.html                  # 既存を活用（M5で軽微にリファクタしfetch化）
├── sample-data.json            # 開発用ダミー（M3aで投入済の確定構造）
├── yamamo-rogo.png             # 既存
├── starter/                    # ※M0で .gitignore で除外済み（将来要否判断）
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md

## 4. フロントエンドとデータの接続方式

### 現状の実態（v1.1記載）
- 既存の `index.html` は **データがJS内にハードコード**されている（完成イメージ）。
- `sample-data.json` は v1.1 時点で空（`{}`）だったが、**v1.2（M3a）で確定構造のダミーデータを投入済**。
- M5で `index.html` を fetch 化する。

### 方針
- `index.html` を**軽微にリファクタ**し、`fetch('data/latest.json')` で外部JSONを読み込む方式へ変更（M5）。
- `data/latest.json` のキー構造は本書の §4「latest.json 確定キー構造」に従う。
- `sample-data.json` は `latest.json` と同一構造のダミーデータ（M3aで投入済）。

### データファイル構成

| ファイル | 内容 | 生成タイミング |
|---|---|---|
| `data/daily/YYYY-MM-DD.json` | 日次の生データ | fetch_daily.py（毎日） |
| `data/archive/YYYY-MM.json` | 月次集計の確定データ | generate_monthly.py（月次） |
| `data/archive/fiscal-YYYY.json` | 年度（4月〜翌3月）累計データ | generate_monthly.py（月次のついでに再生成） |
| `data/latest.json` | 最新月次のスナップショット | generate_monthly.py（月次） |
| `data/months.json` | 利用可能な月＋年度のインデックス | generate_monthly.py（月次） |

### latest.json 確定キー構造

```jsonc
{
  // 対象月
  "month": "2026-03",                     // ISO形式（処理用）
  "monthLabel": "2026年3月",              // 日本語表示用
  "generatedAt": "2026-04-01",            // 生成日（YYYY-MM-DD）

  // 月次サマリ（4枚カードに対応）
  "summary": {
    "totalSales": 287400,                 // 月間売上合計（円）
    "orderCount": 43,                     // 注文件数
    "averageOrderValue": 6684,            // 平均単価（円、小数四捨五入）
    "monthOverMonthPct": 12.3             // 前月比%（初月運用時は null → 画面で「—」表示）
  },

  // 日別売上推移グラフ
  "dailySales": [
    { "day": 1,  "sales": 4200 },
    { "day": 2,  "sales": 8800 }
    // ... その月の日数分（28〜31件）
  ],

  // グラフY軸の最大値（生成時に自動計算）
  "chartScale": {
    "leftMax":  25000,   // = ceil(max(dailySales) * 1.2 / 5000) * 5000
    "rightMax": 350000   // = ceil(totalSales * 1.1 / 50000) * 50000
  },

  // 商品別売上ランキング（全件・降順）
  "productRanking": [
    {
      "rank": 1,
      "name": "ギフトセット1L3本",
      "quantity": 8,
      "sales": 52800,
      "sharePct": 18.4                    // 売上構成比（小数1桁）
    }
    // ... 全件
  ],

  // 注文詳細（直近10件・新しい順）
  "recentOrders": [
    {
      "date": "3/31",                     // 表示用の短縮日付（M/D）
      "orderNumber": "BASE側の注文ID",     // BASE API の unique_key 等
      "productName": "ギフトセット1L3本",
      "quantity": 1,
      "amount": 6600,
      "shippingArea": "東京都"            // 都道府県のみ
    }
    // ... 10件
  ],

  // AI分析コメント（§5参照）
  "aiComment": "3月は売上¥287,400・注文43件で、前月比+12.3%と..."
}
```

### Y軸スケール自動計算ルール（月次）
- `leftMax` = `ceil(max(dailySales) * 1.2 / 5000) * 5000`（例: 最大18,200 → 25,000）
- `rightMax` = `ceil(totalSales * 1.1 / 50000) * 50000`（例: 287,400 → 350,000）
- 切り上げ単位（5,000 / 50,000）は将来必要に応じて見直す。

### fiscal-YYYY.json 確定キー構造（年度ビュー）

```jsonc
{
  "fiscalYear": 2026,                     // 年度（=4月始まりの年）
  "fiscalLabel": "2026年度",              // 表示用
  "period": {
    "start": "2026-04",
    "end":   "2027-03"
  },
  "generatedAt": "2026-05-03",

  "summary": {
    "totalSales": 35600,                  // 年間売上合計
    "orderCount": 9,                      // 年間注文件数
    "averageOrderValue": 3956,            // 平均単価
    "yearOverYearPct": null               // 前年同期比%（前年度のfiscalアーカイブが無ければnull）
  },

  // 月別売上（4月〜翌3月の12ヶ月固定）
  "monthlySales": [
    { "month": "2026-04", "monthLabel": "4月",  "sales": 35600 },
    { "month": "2026-05", "monthLabel": "5月",  "sales": 0 }
    // ... 12件
  ],

  "chartScale": {
    "leftMax":  50000,                    // ceil(max(monthlySales)*1.2/50000)*50000
    "rightMax": 500000                    // ceil(totalSales*1.1/500000)*500000
  },

  // 商品ランキング：12ヶ月分の月次productRankingを商品名でマージ
  "productRanking": [
    { "rank": 1, "name": "...", "quantity": 10, "sales": 9400, "sharePct": 26.4 }
    // ... 全件
  ],

  "aiComment": ""                         // 年間版AIコメント（§5参照）
}
```

### Y軸スケール自動計算ルール（年次）
- `leftMax` = `ceil(max(monthlySales) * 1.2 / 50000) * 50000`
- `rightMax` = `ceil(totalSales * 1.1 / 500000) * 500000`

### index.html のタブUI仕様（v1.3で追加）

ヘッダー直下に **月間 / 年間** のタブ切り替えを配置：
- 月間タブ → 右上に **月プルダウン**、`data/archive/YYYY-MM.json` を fetch
- 年間タブ → 右上に **年度プルダウン**、`data/archive/fiscal-YYYY.json` を fetch

年間ビューの構成（月間ビューとの差分）：
| セクション | 月間 | 年間 |
|---|---|---|
| サマリ4枚 | 月間売上・件数・平均・前月比 | 年間売上・件数・平均・前年同期比 |
| 棒グラフ | 日別31本＋日次累積 | 月別12本＋月次累積 |
| 商品ランキング | 月内全件 | 年度内全件 |
| **売上比率チャート** | なし | **横棒スタック（全商品）** |
| 注文詳細10件 | 表示 | **非表示** |
| AIコメント | 月次振り返り | **年次振り返り** |

### months.json 構造

```jsonc
{
  "available": ["2026-04"],               // YYYY-MM の昇順
  "latest":    "2026-04",
  "fiscalAvailable": [2026],              // 年度の昇順
  "fiscalLatest":    2026
}
```

## 5. AI分析コメント生成方式

### 生成手段
- 案① **GitHub Models（推奨・無料枠あり）**
  - GitHub Actions内で `actions/ai-inference` や models API を呼び出す
  - GITHUB_TOKEN で認証、追加セットアップ不要
  - gpt-4o-mini 等で月1回呼び出し → ほぼコスト0
- 案② Anthropic Claude API（従量課金）
  - ANTHROPIC_API_KEY をSecretsに登録
  - Claude 3.5 Haiku で月1回 → 約$0.01/回

→ **案①（GitHub Models）を推奨**（運用コスト抑制）。

### 月次コメントの立て付け（v1.2で確定）
- **文字数**: 300字 ±50字
- **構成**: 4部構成
  1. **今月の振り返り**（80字程度）— 売上総額・注文件数・前月比・トップ商品など事実ベース
  2. **好調だった点**（60字程度）— 特に売れた商品、伸びているカテゴリ、ピークだった日や週などの考察
  3. **課題・反省点**（60字程度）— 売上が落ちた要因、低調商品、改善余地のあるポイント
  4. **来月への提案**（100字程度）— 具体的な施策案（SNS、季節性活用、ギフト訴求、リピーター施策など）
- **トーン**: 穏やかだが前向き、家業への敬意を感じさせる
- **必ず含める要素**: 売上総額、前月比、トップ3商品、来月の具体施策1〜2個
- **避ける表現**: 過度に楽観/悲観な言い回し、根拠のない予測

### 年次コメントの立て付け（v1.3で追加）
- **文字数**: 400字 ±50字
- **構成**: 4部構成
  1. **年度の総括**（100字程度）— 年間売上・注文件数・前年比・トップ商品の年間ベース実績
  2. **季節トレンド・伸びた商品**（80字程度）— 月別推移から見える季節性、好調商品カテゴリの分析
  3. **積み残し・課題**（80字程度）— 年度通して伸び悩んだ点、改善余地、構造的な課題
  4. **来年度の方向性**（140字程度）— 来年度の重点施策、新商品検討、季節別キャンペーンの全体設計
- **トーン**: 月次同様。年度全体を俯瞰した「経営者目線」の語り口で
- **必ず含める要素**: 年間売上、前年比（あれば）、トップ3商品、来年度の重点施策2〜3個

### プロンプト骨子
```
あなたは森田醤油醸造元のEC売上を毎月分析するアナリストです。
以下のデータをもとに、家業オーナー向けの月次振り返りコメントを300字程度で書いてください。

【月】{monthLabel}
【売上総額】¥{totalSales}
【注文件数】{orderCount}件
【前月比】{monthOverMonthPct}%
【商品ランキングTOP5】{top5の商品名・販売数・売上}
【日別売上の推移】{dailySalesから読み取れる傾向}

構成は以下の4部:
1. 今月の振り返り（事実）
2. 好調だった点（考察）
3. 課題・反省点
4. 来月への提案（具体施策1〜2個）

トーン: 穏やかだが前向き、家業への敬意を感じさせる。
```

## 6. BASE API 利用仕様
- 認証：OAuth 2.0（Authorization Code Flow）
- 初回：oauth_init.py をローカル実行 → refresh_token取得（M2 実施済）
- 運用：GitHub Actions で refresh_token → access_token を都度取得
- エンドポイント：
  - GET /1/orders?start_ordered=前日0時&end_ordered=前日23:59:59
  - GET /1/items（商品マスタ、月次ジョブ時のみ更新）
- スコープ: read_users / read_orders / read_items
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
- 公開URL：
  - 本番（更新あり）: https://yamamo-ec-report-6021.surge.sh/
  - デモ用スナップショット（更新なし・固定）: https://shoyu-ec-report.surge.sh/

## 9. マイルストーン
- M0: ✅ starter/ 整理、設計書v1.1化、README・CLAUDE.md整備
- M1: ✅ BASE開発者アプリ登録（手動・ユーザー作業）
- M2: ✅ oauth_init.py 実装・ローカル認証
- M3a: ✅ 設計書v1.2 + sample-data.json ダミー投入
- M3b: ✅ fetch_daily.py 実装
- M4: ✅ generate_monthly.py + ai_comment.py 実装
- M5: ✅ index.html を fetch化＋月プルダウン追加
- M5b: 🚧 月間/年間タブ追加＋fiscal-YYYY.json 集計＋年度プルダウン＋売上比率チャート（**本PR**）
- M6: GitHub Actions 両ワークフロー設定（毎日09:00 / 毎月1日10:00 JST）
- M7: 本番検証（手動トリガー → 翌月1日自動実行確認）
