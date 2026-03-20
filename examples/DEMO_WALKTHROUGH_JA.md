# AICodeReviewer 日本語デモ

このガイドは、サンプルプロジェクトを使って日本語出力でレビューを試すための簡潔な手順です。

## 目的

以下を安全に確認できます。
- 日本語出力が有効か
- CLIレビューの対話フローが理解できるか
- レポート生成が期待どおりか

## 最初に読むもの

- [sample_project/README.md](sample_project/README.md)
- 英語版の詳細手順: [DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)

英語版を正本とし、この日本語ガイドは日本語レビュー実行の補助として使ってください。

## 日本語レビューの実行

まずはドライラン:

```bash
aicodereviewer examples/sample_project --type security --lang ja --dry-run
```

実際のレビュー:

```bash
aicodereviewer examples/sample_project --type security --programmers "デモユーザー" --reviewers "AIレビュアー" --lang ja
```

## 日本語レビューで確認したいポイント

- 問題の説明が日本語で出ること
- 深刻度とタイプが理解しやすいこと
- 対話アクションがレビューの流れに沿っていること

## 対話アクション

現在のCLIフローでは、以下の操作を確認できます。
- `RESOLVED`
- `IGNORE`
- `AI FIX`
- `VIEW CODE`
- `SKIP`
- 検証失敗時の強制解決

## 代表的な検出例

- `security`: SQLインジェクション、弱いハッシュ、危険なデシリアライズ
- `performance`: O(n^2)アルゴリズム、無駄なI/O、非効率な処理
- `best_practices`: マジックナンバー、命名、重複ロジック
- `error_handling`: 例外処理不足、bare except、入力検証不足
- `maintainability`: 深いネスト、長すぎる関数、読みにくい変数名

## 関連ガイド

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
- [Project README](../README.md)
- [CLI Guide](../docs/cli.md)
深刻度: high
コードスニペット:
def check_eligibility(age, income, credit_score, employment_status, has_collateral):
    if age >= 18:
        if income > 30000:
            if credit_score > 600:
                if employment_status == "employed":
                    if has_collateral:
...

AIフィードバック:
保守性の問題: 深いネスト構造

このcheck_eligibilityメソッドは5段階のネストされた条件文を持ち、
コードの可読性と保守性を著しく低下させています。

問題点:
1. 複雑なロジックフローが追跡困難
2. 新しい条件の追加が困難
3. テストケースの作成が複雑
4. バグの混入リスクが高い
5. コードレビューが困難

推奨される改善:
1. 早期リターンパターンを使用
2. ガード節で無効な条件を先にチェック
3. 複雑な条件をヘルパーメソッドに分割

修正コード例:
  def check_eligibility(age, income, credit_score, employment_status, has_collateral):
      """融資の適格性をチェック"""
      # ガード節：基本要件チェック
      if age < 18:
          return "rejected"
      
      if income <= 30000:
          return "rejected"
      
      if credit_score <= 600:
          return "rejected"
      
      if employment_status != "employed":
          return "rejected"
      
      # 担保またはハイスコアで承認
      if has_collateral or credit_score > 700:
          return "approved"
      
      return "rejected"

追加の改善提案:
- 承認/拒否の理由を返す
- 条件を設定可能にする
- ロジックをビジネスルールクラスに抽出

期待される効果:
- 可読性: 大幅に向上（ネストレベル1のみ）
- 保守性: 条件の追加・変更が容易
- テスト性: 各条件を個別にテスト可能

深刻度: 高 - 長期的な保守コストに影響
影響: 開発速度の低下、バグリスクの増加

ステータス: pending
```

## 日本語サマリーレポート例

レビュー完了後、以下のような日本語サマリーが生成されます：

```
AIコードレビューレポート
==================================================

プロジェクト: examples/sample_project
レビュータイプ: security
スコープ: project
スキャンファイル数: 5
品質スコア: 42/100
プログラマー: デモユーザー
レビュアー: AIレビュアー
生成日時: 2025-12-21 16:30:00
言語: ja

問題サマリー:
------------------------------
解決済み: 2
無視: 1
未処理: 5

詳細な問題:
==================================================

問題 1:
  ファイル: examples/sample_project/user_auth.py
  タイプ: security
  深刻度: critical
  ステータス: resolved
  説明: user_auth.pyのレビューフィードバック
  コード: def login(self, username, password):...
  AIフィードバック: 重大なセキュリティ脆弱性: SQLインジェクション...

問題 2:
  ファイル: examples/sample_project/user_auth.py
  タイプ: security
  深刻度: high
  ステータス: pending
  説明: user_auth.pyのレビューフィードバック
  コード: def hash_password(self, password):...
  AIフィードバック: 弱いハッシュアルゴリズム（MD5）の使用...

[... 続く ...]
```

## インタラクティブプロンプト（日本語）

### アクション選択

```
アクションを選択 (1-4): 1
✅ 問題が解決済みとしてマークされました！
```

```
アクションを選択 (1-4): 2
この問題を無視する理由を入力してください: デモファイルのため、本番環境では使用しない
✅ 理由付きで問題が無視されました。
```

```
アクションを選択 (1-4): 3

🤖 AIが以下の修正を提案します:
================================================================================
[修正内容のdiffが表示されます]
================================================================================
このAI修正を適用しますか？ (y/n): y
📁 バックアップを作成しました: user_auth.py.backup
✅ AI修正が正常に適用されました！
```

## すべてのレビュータイプ（日本語コマンド）

```bash
# セキュリティレビュー
python -m aicodereviewer examples/sample_project \
  --type security --programmers "山田太郎" --reviewers "AIレビュアー" --lang ja

# パフォーマンスレビュー  
python -m aicodereviewer examples/sample_project \
  --type performance --programmers "山田太郎" --reviewers "AIレビュアー" --lang ja

# ベストプラクティスレビュー
python -m aicodereviewer examples/sample_project \
  --type best_practices --programmers "山田太郎" --reviewers "AIレビュアー" --lang ja

# エラーハンドリングレビュー
python -m aicodereviewer examples/sample_project \
  --type error_handling --programmers "山田太郎" --reviewers "AIレビュアー" --lang ja

# 保守性レビュー
python -m aicodereviewer examples/sample_project \
  --type maintainability --programmers "山田太郎" --reviewers "AIレビュアー" --lang ja
```

## 期待される問題数（日本語レビュー）

| レビュータイプ | 問題数 | 深刻度の分布 |
|---------------|--------|-------------|
| セキュリティ (security) | 5-8 | 致命的: 2-3, 高: 2-3, 中: 1-2 |
| パフォーマンス (performance) | 6-8 | 高: 2-3, 中: 3-4, 低: 1-2 |
| ベストプラクティス (best_practices) | 8-10 | 中: 3-4, 低: 4-6 |
| エラーハンドリング (error_handling) | 6-7 | 高: 2-3, 中: 2-3, 低: 1-2 |
| 保守性 (maintainability) | 3-5 | 高: 2-3, 中: 1-2 |

## 日本語と英語の違い

### 技術用語の扱い

- **コード**: 常に元のまま（英語の変数名、関数名など）
- **AIフィードバック**: 完全に日本語
- **技術用語**: 一般的な用語は日本語、固有名詞は英語（例: SQLインジェクション、JSON、API）

### レポート形式

英語版と同じ構造ですが、すべての説明文が日本語になります：
- ファイルパスとコード: そのまま
- 問題の説明: 日本語
- 推奨事項: 日本語
- コメント: 日本語

## ヒント

1. **日本語フィードバックの精度** - Claude 3.5 Sonnetは日本語でも高品質な分析を提供
2. **技術用語の一貫性** - 業界標準の用語を使用
3. **コード例** - 日本語コメント付きで提供
4. **レポート** - JSON（英語キー）+ 日本語サマリー

## トラブルシューティング

**問題**: 日本語が文字化けする
```bash
# PowerShellの場合
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

**問題**: デフォルト言語を日本語にしたい
```bash
# システム言語が日本語の場合、--lang defaultで自動的に日本語になります
python -m aicodereviewer examples/sample_project --type security \
  --programmers "山田太郎" --reviewers "AIレビュアー" --lang default
```

---

詳細については、メインの[README.md](../README.md)および[DEMO_WALKTHROUGH.md](DEMO_WALKTHROUGH.md)を参照してください。
