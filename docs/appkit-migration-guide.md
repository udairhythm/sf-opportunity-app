# AppKit Migration Guide: 商談管理アプリ

> 現行の Streamlit ベース商談管理アプリ（`sf-opportunity-app/`）を、AppKit（React + TypeScript）で新規プロジェクトとして再構築する際のガイドドキュメント。

---

## 目次

1. [現行アプリの概要](#1-現行アプリの概要)
2. [AppKit / app-templates の概要](#2-appkit--app-templates-の概要)
3. [新規プロジェクト設計案](#3-新規プロジェクト設計案)
4. [流用可能なコード](#4-流用可能なコード)
5. [実装ステップバイステップ](#5-実装ステップバイステップ)
6. [デプロイ手順](#6-デプロイ手順)
7. [注意事項](#7-注意事項)

---

## 1. 現行アプリの概要

### 1.1 機能一覧

| 機能 | 説明 |
|------|------|
| 商談一覧 | Salesforce の Opportunity を一覧表示 |
| フィルタ | ステージ / 取引先 / 金額範囲 / CloseDate 範囲で絞り込み |
| 商談編集 | ステージ・金額・CloseDate を更新 |
| 商談作成 | 新規 Opportunity を Salesforce に作成 |
| 活動履歴 | 商談に紐づく Task の一覧表示 |
| 活動登録 | 新規 Task を Salesforce に作成 |
| Ask AI | 商談データを文脈にした AI チャット（ストリーミング応答） |

### 1.2 ファイル構成

```
sf-opportunity-app/
├── app.py            # Streamlit メインアプリ（UI + ルーティング）
├── sf_client.py      # Salesforce CRUD クライアント
├── llm_client.py     # Databricks Foundation Model API クライアント
├── app.yaml          # Databricks Apps デプロイ設定
└── requirements.txt  # Python 依存パッケージ
```

| ファイル | 役割 |
|----------|------|
| `app.py` | Streamlit UI の全画面（商談一覧・フィルタ・編集・作成・活動履歴・Ask AI）を定義。SF 接続の初期化・キャッシュ・リトライも担当 |
| `sf_client.py` | Salesforce REST API を `simple-salesforce` 経由で操作。Opportunity / Task / Account の CRUD とメタデータ取得 |
| `llm_client.py` | Databricks Model Serving の OpenAI 互換エンドポイントに接続。システムプロンプト構築とストリーミングチャット |
| `app.yaml` | Databricks Apps のランタイム設定（起動コマンド・環境変数・リソース定義） |
| `requirements.txt` | `simple-salesforce>=1.12.0`, `openai>=1.0.0`, `databricks-sdk>=0.20.0` |

### 1.3 データフロー

```
[Salesforce]
    │
    ├── 読み取り: Lakeflow Connect → ya_catalog_demo.salesforce.*
    │             （現行アプリでは SF REST API 直接クエリを使用）
    │
    └── 書き込み: SF REST API（simple-salesforce 経由）
                  ├── Opportunity.update()
                  ├── Opportunity.create()
                  └── Task.create()

[Databricks Model Serving]
    └── databricks-claude-sonnet-4 エンドポイント
        └── OpenAI 互換 API でストリーミング応答
```

**補足**: 現行アプリは SF REST API で直接読み取りしているが、将来的には Lakeflow Connect で同期済みの `ya_catalog_demo.salesforce` カタログのテーブルを SQL Warehouse 経由で読み取ることで、SF API コール数の削減とパフォーマンス向上が見込める。

### 1.4 認証方式

| 対象 | 方式 | 詳細 |
|------|------|------|
| Salesforce | OAuth refresh token | `SF_REFRESH_TOKEN` + `SF_CLIENT_ID` で access token を自動更新。フォールバックとして access token 直指定、ユーザー名/パスワード認証も対応 |
| Databricks | SDK 統合認証 | Apps ランタイムではサービスプリンシパル自動認証。ローカル開発では `DATABRICKS_TOKEN` 環境変数 or `databricks auth login` CLI |

### 1.5 Databricks リソース設定

- **Secret Scope**: `sf-opportunity-app`
  - `sf-refresh-token` — Salesforce OAuth refresh token
  - `sf-client-id` — Salesforce Connected App の Client ID
  - `sf-login-url` — Salesforce ログイン URL（`https://login.salesforce.com`）
- **Serving Endpoint**: `databricks-claude-sonnet-4`

---

## 2. AppKit / app-templates の概要

### 2.1 AppKit の仕組み

[AppKit](https://github.com/databricks/appkit) は Databricks Apps 上でフルスタック React アプリを構築するためのフレームワーク。

- **フロントエンド**: React + TypeScript（Vite ベース）
- **バックエンド**: Node.js SDK（Databricks API との統合）
- **プラグインシステム**:
  - **Analytics** — SQL Warehouse 経由のデータクエリ・可視化
  - **Lakebase** — Lakebase (PostgreSQL) との CRUD 操作
  - **Genie** — Genie Space との対話型 AI チャット
  - **Files** — Unity Catalog Volumes のファイル操作

### 2.2 app-templates の推奨テンプレート

[app-templates](https://github.com/databricks/app-templates) リポジトリから、本アプリの再構築に適したテンプレート:

| テンプレート | 特徴 | 本アプリとの関連 |
|-------------|------|-----------------|
| `appkit-todo` | CRUD パターンの参考実装（Lakebase + React） | 商談の一覧・作成・編集・削除パターンに最も近い |
| `genie-app` | AI チャット UI の参考実装（Genie プラグイン） | Ask AI 画面の UI パターンに活用可能 |

### 2.3 テンプレートの使い方

```bash
# テンプレートからプロジェクト作成
npx create-appkit-app sf-opportunity-app-v2 --template appkit-todo

# ローカル開発サーバー起動
cd sf-opportunity-app-v2
npm install
npm run dev
```

> **注意**: テンプレートのコマンドや構成は AppKit のバージョンにより変更される可能性があるため、利用時には公式リポジトリの最新 README を確認すること。

---

## 3. 新規プロジェクト設計案

### 3.1 プロジェクト構成

```
sf-opportunity-app-v2/
├── frontend/               # React + Vite フロントエンド
│   ├── src/
│   │   ├── components/     # UI コンポーネント
│   │   │   ├── OpportunityList.tsx
│   │   │   ├── OpportunityDetail.tsx
│   │   │   ├── OpportunityForm.tsx
│   │   │   ├── TaskHistory.tsx
│   │   │   ├── TaskForm.tsx
│   │   │   ├── FilterPanel.tsx
│   │   │   └── AskAI.tsx
│   │   ├── hooks/          # カスタム hooks
│   │   ├── types/          # TypeScript 型定義
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/                # FastAPI バックエンド
│   ├── main.py             # FastAPI アプリ + ルーティング
│   ├── sf_client.py        # 現行コード流用
│   ├── llm_client.py       # 現行コード流用
│   └── requirements.txt
├── app.yaml                # Databricks Apps 設定
└── databricks.yml          # DAB 設定（オプション）
```

### 3.2 技術スタック

| レイヤー | 技術 | 補足 |
|---------|------|------|
| フロントエンド | React + TypeScript + Vite | AppKit コンポーネント活用 |
| バックエンド | FastAPI (Python) | 現行の `sf_client.py` / `llm_client.py` をそのまま流用 |
| データ読み取り | SQL Warehouse 経由 | Lakeflow Connect 同期済みテーブルから読み取り |
| データ書き込み | SF REST API | `simple-salesforce` 経由で直接書き込み |
| AI | Databricks Model Serving | OpenAI 互換 API + SSE ストリーミング |

### 3.3 現行機能 → AppKit マッピング表

| 現行機能（Streamlit） | 新規実装方式 |
|----------------------|-------------|
| `st.dataframe` + `on_select` | React テーブルコンポーネント（TanStack Table 等） |
| `st.selectbox` / `st.multiselect` フィルタ | `FilterPanel.tsx`（React state 管理） |
| `st.form` 編集・作成 | `OpportunityForm.tsx` + fetch API |
| `st.tabs` 活動履歴 | React タブ or アコーディオン |
| `st.chat_message` + `st.write_stream` | `AskAI.tsx` + SSE（EventSource） |
| `st.cache_data` | React Query / SWR でクライアントサイドキャッシュ |
| `st.session_state` | React state / URL パラメータ |

### 3.4 API 設計

#### エンドポイント一覧

| メソッド | パス | 説明 | データソース |
|---------|------|------|-------------|
| `GET` | `/api/opportunities` | 商談一覧取得 | SQL Warehouse |
| `GET` | `/api/opportunities/:id` | 商談詳細取得 | SQL Warehouse |
| `PUT` | `/api/opportunities/:id` | 商談更新 | SF REST API |
| `POST` | `/api/opportunities` | 商談作成 | SF REST API |
| `GET` | `/api/opportunities/:id/tasks` | 活動履歴取得 | SF REST API |
| `POST` | `/api/opportunities/:id/tasks` | 活動登録 | SF REST API |
| `GET` | `/api/accounts` | 取引先一覧 | SQL Warehouse |
| `GET` | `/api/stages` | ステージ一覧 | SF REST API |
| `POST` | `/api/chat` | AI チャット（SSE） | Model Serving |

#### リクエスト / レスポンス例

> **注意**: 現行の `sf_client.get_opportunities()` は日本語カラム名（`商談名`, `取引先`, `ステージ`, `金額`, `作成日`）の DataFrame を返す。API レスポンスでは下記のように snake_case に正規化する想定。FastAPI ルート実装時にカラム名のマッピング処理が必要。

**GET /api/opportunities**

```json
// Query params: ?stage=Closed Won&account=Acme&amount_min=100000&amount_max=500000
// Response:
{
  "opportunities": [
    {
      "id": "006xxx",
      "name": "Acme - Enterprise License",
      "account_name": "Acme Corp",
      "stage": "Closed Won",
      "amount": 300000,
      "close_date": "2026-03-15",
      "created_date": "2026-01-10"
    }
  ],
  "total": 1
}
```

**PUT /api/opportunities/:id**

```json
// Request body:
{
  "stage": "Negotiation/Review",
  "amount": 500000,
  "close_date": "2026-06-30"
}
// Response:
{ "success": true }
```

**POST /api/opportunities**

```json
// Request body:
{
  "name": "新規商談",
  "account_id": "001xxx",
  "stage": "Prospecting",
  "amount": 100000,
  "close_date": "2026-12-31"
}
// Response:
{ "id": "006yyy" }
```

**POST /api/opportunities/:id/tasks**

```json
// Request body:
{
  "subject": "初回ミーティング",
  "description": "製品デモを実施",
  "status": "Completed",
  "activity_date": "2026-04-01"
}
// Response:
{ "id": "00Txxx" }
```

**POST /api/chat（SSE ストリーミング）**

```json
// Request body:
{
  "messages": [
    { "role": "user", "content": "今月クローズ予定の商談は？" }
  ]
}
// Response: text/event-stream
// data: {"content": "今月"}
// data: {"content": "クローズ"}
// data: {"content": "予定の商談は..."}
// data: [DONE]
```

---

## 4. 流用可能なコード

### 4.1 sf_client.py

現行の `sf_client.py` は FastAPI ルートからほぼそのまま呼び出せる。

#### 関数一覧

| 関数 | シグネチャ | 説明 |
|------|----------|------|
| `get_connection` | `() -> Salesforce` | SF 接続を確立。OAuth refresh token → access token → ユーザー名/パスワードの優先順位 |
| `get_opportunities` | `(sf: Salesforce) -> pd.DataFrame` | 全 Opportunity を取得。カラム: `Id`, `商談名`, `取引先`, `ステージ`, `金額`, `CloseDate`, `作成日` |
| `update_opportunity` | `(sf: Salesforce, opp_id: str, fields: dict[str, Any]) -> bool` | Opportunity を更新。`fields` は SF API フィールド名（例: `StageName`, `Amount`, `CloseDate`） |
| `create_opportunity` | `(sf: Salesforce, name: str, account_id: str, stage: str, amount: float, close_date: str) -> str` | 新規 Opportunity 作成。戻り値は新規 ID |
| `get_tasks` | `(sf: Salesforce, opp_id: str) -> pd.DataFrame` | 指定 Opportunity の Task 一覧。カラム: `Id`, `件名`, `説明`, `ステータス`, `活動日` |
| `create_task` | `(sf: Salesforce, opp_id: str, subject: str, description: str, status: str, activity_date: str) -> str` | 新規 Task 作成。戻り値は新規 ID |
| `get_accounts_with_ids` | `(sf: Salesforce) -> list[dict]` | Account の `Id` と `Name` を取得。戻り値: `[{"Id": "001xxx", "Name": "Acme"}]` |
| `get_accounts` | `(sf: Salesforce) -> list[str]` | Account 名の一覧（フィルタ用） |
| `get_stage_names` | `(sf: Salesforce) -> list[str]` | Opportunity の StageName ピックリスト値を取得 |

#### FastAPI ルートからの呼び出し例

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sf_client

app = FastAPI()

# Startup event for SF connection
sf = None

@app.on_event("startup")
async def startup():
    global sf
    sf = sf_client.get_connection()

@app.get("/api/opportunities")
async def list_opportunities(
    stage: str | None = None,
    account: str | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
):
    df = sf_client.get_opportunities(sf)
    # Apply filters
    if stage:
        df = df[df["ステージ"] == stage]
    if account:
        df = df[df["取引先"] == account]
    if amount_min is not None:
        df = df[df["金額"].fillna(0) >= amount_min]
    if amount_max is not None:
        df = df[df["金額"].fillna(0) <= amount_max]
    return {"opportunities": df.to_dict(orient="records"), "total": len(df)}

class OpportunityUpdate(BaseModel):
    stage: str | None = None
    amount: float | None = None
    close_date: str | None = None

@app.put("/api/opportunities/{opp_id}")
async def update_opp(opp_id: str, body: OpportunityUpdate):
    fields = {}
    if body.stage is not None:
        fields["StageName"] = body.stage
    if body.amount is not None:
        fields["Amount"] = body.amount
    if body.close_date is not None:
        fields["CloseDate"] = body.close_date
    if not fields:
        raise HTTPException(400, "No fields to update")
    sf_client.update_opportunity(sf, opp_id, fields)
    return {"success": True}
```

### 4.2 llm_client.py

現行の `llm_client.py` を SSE レスポンスに変換する。

#### 関数一覧

| 関数 | シグネチャ | 説明 |
|------|----------|------|
| `get_llm_client` | `() -> OpenAI` | Databricks Model Serving の OpenAI 互換クライアントを生成 |
| `get_model_name` | `() -> str` | Serving Endpoint 名を返す（デフォルト: `databricks-claude-sonnet-4`） |
| `build_system_prompt` | `(sf_data_json: str) -> str` | SF データを埋め込んだシステムプロンプトを構築 |
| `chat_stream` | `(client: OpenAI, model: str, messages: list[dict]) -> Generator[str, None, None]` | ストリーミングチャット。チャンクごとにテキストを yield |

#### 認証フロー（`_get_databricks_auth`）

1. `DATABRICKS_TOKEN` 環境変数（ローカル開発用 PAT）
2. Databricks SDK 統合認証（Apps ランタイムのサービスプリンシパル）
3. Databricks CLI フォールバック（`databricks auth token`）

#### FastAPI SSE 変換例

```python
import json
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import llm_client
import sf_client

app = FastAPI()

class ChatRequest(BaseModel):
    messages: list[dict]

@app.post("/api/chat")
async def chat(req: ChatRequest):
    # Build context from SF data
    sf = sf_client.get_connection()
    opp_df = sf_client.get_opportunities(sf)
    opp_json = opp_df.to_json(orient="records", force_ascii=False)

    client = llm_client.get_llm_client()
    model = llm_client.get_model_name()
    system_prompt = llm_client.build_system_prompt(opp_json)

    api_messages = [{"role": "system", "content": system_prompt}]
    # Include last 10 turns
    api_messages.extend(req.messages[-10:])

    def event_stream():
        for chunk in llm_client.chat_stream(client, model, api_messages):
            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

### 4.3 app.yaml — リソース定義テンプレート

現行の `app.yaml` を新規プロジェクト用に変換する際のテンプレート:

```yaml
# sf-opportunity-app-v2/app.yaml
command:
  - "uvicorn"
  - "backend.main:app"
  - "--host"
  - "0.0.0.0"
  - "--port"
  - "8000"

env:
  - name: SF_REFRESH_TOKEN
    valueFrom: sf-refresh-token-secret
  - name: SF_CLIENT_ID
    valueFrom: sf-client-id-secret
  - name: SF_LOGIN_URL
    valueFrom: sf-login-url-secret
  - name: SERVING_ENDPOINT_NAME
    value: "databricks-claude-sonnet-4"

resources:
  - name: sf-refresh-token-secret
    secret:
      scope: sf-opportunity-app    # 既存 scope を再利用
      key: sf-refresh-token
      permission: READ
  - name: sf-client-id-secret
    secret:
      scope: sf-opportunity-app
      key: sf-client-id
      permission: READ
  - name: sf-login-url-secret
    secret:
      scope: sf-opportunity-app
      key: sf-login-url
      permission: READ
  - name: serving-endpoint
    serving_endpoint: databricks-claude-sonnet-4
```

---

## 5. 実装ステップバイステップ

### Step 1: テンプレート選定 & プロジェクト初期化

```bash
# appkit-todo テンプレートをベースに作成
npx create-appkit-app sf-opportunity-app-v2 --template appkit-todo

# バックエンド用ディレクトリを追加
mkdir -p sf-opportunity-app-v2/backend
```

- `appkit-todo` のフロント構成を流用しつつ、バックエンドは FastAPI で独自構築
- 公式テンプレートの最新構成を確認の上、適宜調整

### Step 2: バックエンド API 構築（FastAPI + 現行コード流用）

1. 現行の `sf_client.py` と `llm_client.py` を `backend/` にコピー
2. `backend/main.py` に FastAPI ルートを定義（セクション 4 のコード例を参照）
3. SF 接続をアプリ起動時に初期化し、セッション切れ時のリトライロジックを実装
4. `backend/requirements.txt` を作成:
   ```
   fastapi>=0.100.0
   uvicorn>=0.20.0
   simple-salesforce>=1.12.0
   openai>=1.0.0
   databricks-sdk>=0.20.0
   pandas>=2.0.0
   ```

### Step 3: フロントエンド — 商談一覧画面

- `OpportunityList.tsx`: テーブル表示（ソート・ページネーション対応）
- `FilterPanel.tsx`: ステージ / 取引先 / 金額 / CloseDate のフィルタ UI
- `GET /api/opportunities` を呼び出し、クエリパラメータでサーバーサイドフィルタ
- 行選択で詳細画面へ遷移

### Step 4: フロントエンド — 活動履歴 & 登録

- `TaskHistory.tsx`: 商談に紐づく Task 一覧
- `TaskForm.tsx`: 新規 Task 登録フォーム
- `OpportunityDetail.tsx`: 編集フォーム + タブで活動履歴切替

### Step 5: フロントエンド — Ask AI チャット

- `AskAI.tsx`: チャット UI + SSE ストリーミング
- `EventSource` or `fetch` + `ReadableStream` で SSE を購読
- チャット履歴は React state で管理（最大 10 ターン）

### Step 6: ビルド & Databricks Apps デプロイ

```bash
# フロントエンドビルド
cd sf-opportunity-app-v2/frontend
npm run build

# ビルド成果物を backend/static/ に配置
cp -r dist/ ../backend/static/

# デプロイ
cd ..
databricks apps deploy sf-opportunity-app-v2
```

---

## 6. デプロイ手順

### 6.1 app.yaml 設定

セクション 4.3 の `app.yaml` テンプレートを使用。ポイント:

- **起動コマンド**: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
- **環境変数**: SF 認証情報は secrets から注入、`SERVING_ENDPOINT_NAME` は直接指定
- **リソース**: secrets + serving endpoint を宣言

### 6.2 ビルド → デプロイコマンド

```bash
# 1. フロントエンドビルド
cd sf-opportunity-app-v2/frontend && npm run build

# 2. ビルド成果物を配置
cp -r dist/ ../backend/static/

# 3. FastAPI で静的ファイルを配信する設定を確認
#    main.py: app.mount("/", StaticFiles(directory="static", html=True), name="static")

# 4. デプロイ
cd ..
databricks apps deploy sf-opportunity-app-v2
```

### 6.3 既存 secrets の再利用

現行アプリの secret scope `sf-opportunity-app` をそのまま再利用可能:

```bash
# 既存の secrets 確認
databricks secrets list-secrets --scope sf-opportunity-app

# 出力例:
# sf-refresh-token
# sf-client-id
# sf-login-url
```

新規アプリの `app.yaml` で同じ scope・key を参照するだけで、追加の secret 設定は不要。

---

## 7. 注意事項

### 7.1 データ同期遅延への対処

Lakeflow Connect で SF データを同期する場合、書き込み（SF REST API）→ 読み取り（SQL Warehouse）の間にタイムラグが発生する。

**対策: 楽観的 UI 更新（Optimistic UI Update）**

```typescript
// フロントエンド例
const updateOpportunity = async (id: string, fields: OpportunityUpdate) => {
  // 1. UI を即座に更新（楽観的更新）
  setOpportunities(prev =>
    prev.map(opp => opp.id === id ? { ...opp, ...fields } : opp)
  );

  // 2. API 呼び出し
  try {
    await fetch(`/api/opportunities/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(fields),
    });
  } catch (error) {
    // 3. 失敗時はロールバック
    refetchOpportunities();
  }
};
```

### 7.2 SF API レート制限

- Salesforce Developer Edition の API コール制限: **15,000 回/日**
- 読み取りを SQL Warehouse 経由に移行することで、SF API コールは書き込み操作のみに抑えられる
- フロントエンドのポーリング間隔は 60 秒以上を推奨

### 7.3 Lakeflow Connect パイプラインの同期モード

| モード | 説明 | 推奨 |
|--------|------|------|
| Triggered | 手動 or スケジュール実行 | **推奨** — コスト最適化、データ鮮度はスケジュール次第 |
| Continuous | リアルタイム同期 | 即時性が必要な場合のみ（コスト高） |

- 商談管理アプリでは Triggered モード（15〜30 分間隔）で十分なケースが多い
- `databricks pipelines start --pipeline-id <id>` で手動トリガーも可能
