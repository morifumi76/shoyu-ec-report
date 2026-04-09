# shoyu-ec-report

森田醤油醸造元のEC売上（BASE）を自動集計し、
月次レポートを届ける自動化ツール。

## 4つのパーツ
- トリガー：毎月定期実行（GitHub Actions）
- ソース元：BASE（EC売上データ）
- 処理する場所：GitHub Actions
- 届ける先：LINE or メール

## 技術スタック
- HTML + Tailwind CSS（レポートUI）
- BASE API（データ取得）
