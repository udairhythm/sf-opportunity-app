# Salesforce 商談管理アプリ on Databricks Apps

Salesforce上の商談（Opportunity）データをDatabricks Apps上のStreamlitアプリから閲覧・編集・AI分析するWebアプリケーション。

## 機能

### 商談一覧・管理
- ステージ・取引先・金額範囲・CloseDate範囲でフィルタリング
- 商談のステージ・金額・CloseDateを編集しSalesforceに反映
- 商談に紐づく活動履歴（Task）の一覧表示・新規登録

### Ask AI
- Salesforceの商談データをコンテキストとしてLLMに渡すチャットUI
- Databricks Foundation Model API（`databricks-claude-sonnet-4`）によるストリーミング回答
- 例：「今月クローズ予定の商談は？」「ステージ別の商談数は？」

## 技術スタック

| 項目 | 技術 |
|------|------|
| UI | Streamlit |
| SF接続 | simple-salesforce |
| LLM | Databricks Foundation Model API（OpenAI互換） |
| 認証 | SF: アクセストークン / Databricks: サービスプリンシパル（自動） |

## 構成

```
sf-opportunity-app/
├── app.py              # Streamlit メインUI
├── sf_client.py        # Salesforce CRUD操作
├── llm_client.py       # Databricks Foundation Model呼び出し
├── requirements.txt
└── app.yaml            # Databricks Apps設定
```

## ローカル実行

```bash
# 依存パッケージのインストール
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 環境変数の設定
export SF_ACCESS_TOKEN="<sf-access-token>"
export SF_INSTANCE_URL="https://<your-instance>.my.salesforce.com"
export DATABRICKS_HOST="https://<workspace>.cloud.databricks.com"
export DATABRICKS_TOKEN="<pat>"  # またはdatabricks auth loginで認証

# 起動
streamlit run app.py
```

SF CLIでログイン済みの場合：
```bash
export SF_ACCESS_TOKEN=$(sf org display --json | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['accessToken'])")
export SF_INSTANCE_URL=$(sf org display --json | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['instanceUrl'])")
```

## Databricks Appsへのデプロイ

### 1. シークレットの設定

```bash
databricks secrets create-scope sf-opportunity-app
databricks secrets put-secret sf-opportunity-app sf-access-token --string-value "<token>"
databricks secrets put-secret sf-opportunity-app sf-instance-url --string-value "<url>"
```

### 2. アプリの作成・デプロイ

```bash
databricks apps create sf-opportunity-app
databricks workspace mkdirs /Workspace/Users/<user>/apps/sf-opportunity-app

# ソースコードのアップロード
for f in app.py sf_client.py llm_client.py requirements.txt app.yaml; do
  databricks workspace import /Workspace/Users/<user>/apps/sf-opportunity-app/$f --file $f --format AUTO --overwrite
done

# デプロイ
databricks apps deploy sf-opportunity-app --source-code-path /Workspace/Users/<user>/apps/sf-opportunity-app
```

### 3. リソースの追加（API経由）

シークレットリソースとModel Servingエンドポイントをアプリに紐づける：

```bash
curl -X PATCH "https://<workspace>/api/2.0/apps/sf-opportunity-app" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "resources": [
      {"name": "sf-access-token-secret", "secret": {"scope": "sf-opportunity-app", "key": "sf-access-token", "permission": "READ"}},
      {"name": "sf-instance-url-secret", "secret": {"scope": "sf-opportunity-app", "key": "sf-instance-url", "permission": "READ"}},
      {"name": "serving-endpoint", "serving_endpoint": {"name": "databricks-claude-sonnet-4", "permission": "CAN_QUERY"}}
    ]
  }'
```

## SFアクセストークンの更新

トークン期限切れ時：

```bash
SF_TOKEN=$(sf org display --target-org my-dev --json | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['accessToken'])")
databricks secrets put-secret sf-opportunity-app sf-access-token --string-value "$SF_TOKEN"
```

アプリ側はセッション切れを自動検知して再接続するため、シークレット更新後の再デプロイは不要です。
