"""LLM client module using Databricks Foundation Model API."""

import json
import os
import subprocess
from typing import Generator

from openai import OpenAI


def _get_databricks_auth() -> tuple[str, str]:
    """Get Databricks host and token.

    Auth priority:
    1. DATABRICKS_TOKEN env var (local dev with PAT)
    2. Databricks SDK unified auth (Apps runtime, CLI, OAuth)
    3. Databricks CLI fallback (local dev)
    """
    host = os.environ.get("DATABRICKS_HOST", "")
    token = os.environ.get("DATABRICKS_TOKEN", "")

    if host and token:
        return host, token

    # Try Databricks SDK (works in Apps runtime with service principal)
    try:
        from databricks.sdk.core import Config

        config = Config()
        host = config.host
        header_factory = config.authenticate
        headers = header_factory()
        token = headers["Authorization"].split(" ", 1)[1]
        return host, token
    except Exception:
        pass

    # Fallback: Databricks CLI
    if host:
        try:
            result = subprocess.run(
                ["databricks", "auth", "token", "--host", host],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                token = json.loads(result.stdout)["access_token"]
                return host, token
        except (FileNotFoundError, json.JSONDecodeError, KeyError, subprocess.TimeoutExpired):
            pass

    raise ValueError(
        "Databricks auth failed. Set DATABRICKS_HOST+DATABRICKS_TOKEN, "
        "or install databricks-sdk, or login via 'databricks auth login'."
    )


def get_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client for Databricks serving endpoint."""
    host, token = _get_databricks_auth()
    base_url = f"{host.rstrip('/')}/serving-endpoints"

    return OpenAI(
        api_key=token,
        base_url=base_url,
    )


def get_model_name() -> str:
    """Return the serving endpoint model name."""
    return os.environ.get("SERVING_ENDPOINT_NAME", "databricks-claude-sonnet-4")


def build_system_prompt(sf_data_json: str) -> str:
    """Build the system prompt with Salesforce data context."""
    return f"""あなたはSalesforceデータの分析アシスタントです。
以下のSalesforceの商談(Opportunity)と取引先(Account)のデータに基づいて、
ユーザーの質問に日本語で回答してください。

データに基づかない回答はしないでください。
金額は日本円として扱ってください。

## Salesforceデータ
{sf_data_json}
"""


def chat_stream(
    client: OpenAI,
    model: str,
    messages: list[dict],
) -> Generator[str, None, None]:
    """Stream chat completion responses."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        stream=True,
    )
    for chunk in response:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
