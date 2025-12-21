# AICodeReviewer 日本語デモ

このガイドでは、日本語出力モードでのAICodeReviewerの動作を示します。

## 日本語レビューの実行

### コマンド例

```bash
# セキュリティレビュー（日本語）
python -m aicodereviewer examples/sample_project \
  --type security \
  --programmers "デモユーザー" \
  --reviewers "AIレビュアー" \
  --lang ja

# パフォーマンスレビュー（日本語）
python -m aicodereviewer examples/sample_project \
  --type performance \
  --programmers "デモユーザー" \
  --reviewers "AIレビュアー" \
  --lang ja

# ベストプラクティスレビュー（日本語）
python -m aicodereviewer examples/sample_project \
  --type best_practices \
  --programmers "デモユーザー" \
  --reviewers "AIレビュアー" \
  --lang ja
```

## 日本語での出力例

### セキュリティレビュー

```
================================================================================
問題 1/8
================================================================================
ファイル: examples/sample_project/user_auth.py
タイプ: security
深刻度: critical
コードスニペット:
def login(self, username, password):
    """Authenticate user - SECURITY ISSUE: SQL injection vulnerability"""
    query = f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    self.cursor.execute(query)
...

AIフィードバック:
重大なセキュリティ脆弱性: SQLインジェクション

loginメソッドにSQLインジェクション攻撃の脆弱性があります。攻撃者は悪意のある
入力を提供することで、認証をバイパスしたり、機密データを抽出したりできます。

攻撃例:
  ユーザー名: admin' OR '1'='1
  パスワード: anything

推奨事項:
1. プレースホルダーを使用したパラメータ化クエリを使用してください
2. ユーザー入力をSQL文字列に連結しないでください
3. SQLAlchemyなどのORMを使用して、より安全なデータベース操作を行ってください

修正コード例:
  query = "SELECT * FROM users WHERE username=? AND password=?"
  self.cursor.execute(query, (username, password))

深刻度: 致命的 - この脆弱性により認証を完全にバイパスできます
影響: データ漏洩、不正アクセス、データベース侵害の可能性

ステータス: pending

アクション:
  1. 解決済み - 解決済みとしてマークする（プログラムが検証します）
  2. 無視 - この問題を無視する（理由が必要です）
  3. AI修正 - AIにコードを修正させる
  4. コード表示 - ファイル全体を表示する

アクションを選択 (1-4):
```

### パフォーマンスレビュー

```
================================================================================
問題 2/8
================================================================================
ファイル: examples/sample_project/data_processor.py
タイプ: performance
深刻度: high
コードスニペット:
def find_duplicates(self, numbers):
    """PERFORMANCE ISSUE: Nested loops with O(n²) complexity"""
    duplicates = []
    for i in range(len(numbers)):
        for j in range(len(numbers)):
            if i != j and numbers[i] == numbers[j]:
...

AIフィードバック:
パフォーマンス問題: O(n²)の計算量

このfind_duplicatesメソッドは二重ループを使用しており、データ量が増えると
処理時間が二次関数的に増加します。大規模なデータセットでは非常に遅くなります。

現在の実装:
- 時間計算量: O(n²)
- 10,000件のデータで約1億回の比較が必要
- 実行時間: 数秒から数分

推奨される改善:
1. setデータ構造を使用してO(n)の計算量に改善
2. Counterクラスを使用してより効率的に重複をカウント

修正コード例:
  from collections import Counter
  def find_duplicates(self, numbers):
      counter = Counter(numbers)
      return [num for num, count in counter.items() if count > 1]

期待される改善:
- 時間計算量: O(n)
- 10,000件のデータで10,000回の操作のみ
- 実行時間: ミリ秒単位

深刻度: 高 - 大規模データでシステムが著しく遅くなります
影響: ユーザーエクスペリエンスの低下、サーバーリソースの無駄遣い

ステータス: pending
```

### ベストプラクティスレビュー

```
================================================================================
問題 3/8
================================================================================
ファイル: examples/sample_project/calculator.py
タイプ: best_practices
深刻度: medium
コードスニペット:
def calculate_tax(amount):
    return amount * 0.175
...

AIフィードバック:
ベストプラクティス違反: マジックナンバー

税率の値（0.175）がハードコードされており、コードの可読性と保守性を低下させています。

問題点:
1. 0.175が何を意味するのか明確ではない（17.5%の税率）
2. 税率が変更された場合、コード全体を検索して変更する必要がある
3. 異なる税率を使用する場合に柔軟性がない

推奨事項:
1. 名前付き定数として定義する
2. 定数名は大文字で記述する（Pythonの慣例）
3. ドキュメンテーションコメントを追加する

修正コード例:
  # 消費税率（17.5%）
  TAX_RATE = 0.175
  
  def calculate_tax(amount):
      """税額を計算する
      
      Args:
          amount: 税抜き金額
      
      Returns:
          float: 税額
      """
      return amount * TAX_RATE

追加の改善提案:
- 税率を設定ファイルから読み込む
- 地域や商品カテゴリに応じて異なる税率をサポート

深刻度: 中 - 保守性とコード品質に影響
影響: 技術的負債の蓄積、将来のメンテナンスコスト増加

ステータス: pending
```

### エラーハンドリングレビュー

```
================================================================================
問題 4/8
================================================================================
ファイル: examples/sample_project/api_handler.py
タイプ: error_handling
深刻度: high
コードスニペット:
def fetch_data(self, endpoint):
    """ERROR HANDLING ISSUE: No exception handling"""
    response = requests.get(f"{self.base_url}/{endpoint}")
    return response.json()
...

AIフィードバック:
エラーハンドリング不足: 例外処理なし

このメソッドにはネットワークリクエストの例外処理がありません。
ネットワーク障害、タイムアウト、無効なレスポンスなどでアプリケーションがクラッシュします。

発生する可能性のあるエラー:
1. requests.exceptions.ConnectionError - ネットワーク接続の問題
2. requests.exceptions.Timeout - リクエストタイムアウト
3. requests.exceptions.HTTPError - HTTPステータスエラー（404, 500等）
4. ValueError - JSONパースエラー（無効なレスポンス）

推奨される改善:
1. try-exceptブロックで例外をキャッチ
2. 適切なタイムアウト設定を追加
3. HTTPステータスコードを確認
4. 詳細なエラーログを記録
5. デフォルト値またはNoneを返す

修正コード例:
  import logging
  
  def fetch_data(self, endpoint):
      """APIからデータを取得する（例外処理付き）"""
      try:
          response = requests.get(
              f"{self.base_url}/{endpoint}",
              timeout=10
          )
          response.raise_for_status()
          return response.json()
      except requests.exceptions.Timeout:
          logging.error(f"タイムアウト: {endpoint}")
          return None
      except requests.exceptions.HTTPError as e:
          logging.error(f"HTTPエラー: {e.response.status_code}")
          return None
      except requests.exceptions.RequestException as e:
          logging.error(f"リクエストエラー: {e}")
          return None
      except ValueError as e:
          logging.error(f"JSONパースエラー: {e}")
          return None

深刻度: 高 - 本番環境でアプリケーションクラッシュを引き起こす可能性
影響: ユーザーエクスペリエンスの低下、サービスの信頼性低下

ステータス: pending
```

### 保守性レビュー

```
================================================================================
問題 5/8
================================================================================
ファイル: examples/sample_project/utils.py
タイプ: maintainability
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
