"""Salesforce Opportunity Management App on Databricks Apps."""

import json
from datetime import date, datetime
from functools import wraps
from typing import Callable

import pandas as pd
import streamlit as st
from simple_salesforce import SalesforceAuthenticationFailed, SalesforceExpiredSession

import llm_client
import sf_client

st.set_page_config(
    page_title="商談管理",
    page_icon="💼",
    layout="wide",
)

# ── Salesforce connection ──────────────────────────────────────────

@st.cache_resource
def init_sf():
    """Initialize Salesforce connection (cached)."""
    try:
        sf = sf_client.get_connection()
        return sf, None
    except (ValueError, SalesforceAuthenticationFailed) as e:
        return None, str(e)


def reconnect_sf():
    """Clear SF connection cache and reconnect."""
    init_sf.clear()
    load_opportunities.clear()
    load_accounts.clear()
    load_stages.clear()
    return init_sf()


def with_sf_retry(func: Callable):
    """Decorator that retries on expired SF session by reconnecting."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        global sf, sf_error
        try:
            return func(*args, **kwargs)
        except SalesforceExpiredSession:
            sf, sf_error = reconnect_sf()
            if sf:
                return func(*args, **kwargs)
            raise
    return wrapper


sf, sf_error = init_sf()

# ── Sidebar ────────────────────────────────────────────────────────

with st.sidebar:
    st.title("商談管理アプリ")
    st.divider()

    if sf:
        st.success("Salesforce 接続済み")
    else:
        st.error(f"SF接続エラー: {sf_error}")

    page = st.radio("ページ", ["商談一覧", "Ask AI"], label_visibility="collapsed")

# ── Helpers ────────────────────────────────────────────────────────

@with_sf_retry
def _fetch_opportunities() -> pd.DataFrame:
    return sf_client.get_opportunities(sf)


@with_sf_retry
def _fetch_accounts() -> list[str]:
    return sf_client.get_accounts(sf)


@with_sf_retry
def _fetch_stages() -> list[str]:
    return sf_client.get_stage_names(sf)


@st.cache_data(ttl=60)
def load_opportunities() -> pd.DataFrame:
    return _fetch_opportunities()


@st.cache_data(ttl=300)
def load_accounts() -> list[str]:
    return _fetch_accounts()


@st.cache_data(ttl=300)
def load_stages() -> list[str]:
    return _fetch_stages()


def refresh_data():
    """Clear cached data to force reload."""
    load_opportunities.clear()


def _get_selected_opp(filtered: pd.DataFrame) -> dict | None:
    """Return the selected opportunity row as dict, or None."""
    opp_id = st.session_state.get("selected_opp_id")
    if not opp_id:
        return None
    match = filtered[filtered["Id"] == opp_id]
    if match.empty:
        # Also check full data in case filters changed
        df = load_opportunities()
        match = df[df["Id"] == opp_id]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


# ── Page: 商談一覧 ─────────────────────────────────────────────────

def page_opportunities():
    if not sf:
        st.warning("Salesforceに接続してください。")
        return

    st.header("商談一覧・管理")

    df = load_opportunities()
    accounts = load_accounts()
    stages = load_stages()

    if df.empty:
        st.info("商談データがありません。")
        return

    # ── Filters ──
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        selected_stage = st.selectbox("ステージ", ["すべて"] + stages)
    with col2:
        selected_accounts = st.multiselect("取引先", accounts)
    with col3:
        amounts = df["金額"].dropna()
        if not amounts.empty:
            min_amt, max_amt = int(amounts.min()), int(amounts.max())
            if min_amt < max_amt:
                amount_range = st.slider(
                    "金額範囲", min_amt, max_amt, (min_amt, max_amt),
                    format="¥%d",
                )
            else:
                amount_range = (min_amt, max_amt)
                st.text(f"金額: ¥{min_amt:,}")
        else:
            amount_range = None
    with col4:
        dates = pd.to_datetime(df["CloseDate"])
        date_range = st.date_input(
            "CloseDate範囲",
            value=(dates.min().date(), dates.max().date()),
        )

    # ── Apply filters ──
    filtered = df.copy()

    if selected_stage != "すべて":
        filtered = filtered[filtered["ステージ"] == selected_stage]
    if selected_accounts:
        filtered = filtered[filtered["取引先"].isin(selected_accounts)]
    if amount_range:
        filtered = filtered[
            filtered["金額"].fillna(0).between(amount_range[0], amount_range[1])
        ]
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        close_dates = pd.to_datetime(filtered["CloseDate"]).dt.date
        filtered = filtered[close_dates.between(start, end)]

    st.caption(f"{len(filtered)} 件表示中 / 全 {len(df)} 件")

    # ── Data table ──
    display_df = filtered[["商談名", "取引先", "ステージ", "金額", "CloseDate"]].copy()
    display_df["金額"] = display_df["金額"].apply(
        lambda x: f"¥{int(x):,}" if pd.notna(x) else ""
    )

    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # ── Track selection in session_state ──
    selected_rows = event.selection.rows if event.selection else []
    if selected_rows:
        idx = selected_rows[0]
        opp_id = filtered.iloc[idx]["Id"]
        st.session_state["selected_opp_id"] = opp_id

    # ── Detail / Edit ──
    row = _get_selected_opp(filtered)
    if not row:
        return

    opp_id = row["Id"]

    st.divider()
    st.subheader(f"商談詳細: {row['商談名']}")

    detail_tab, task_tab = st.tabs(["編集", "活動履歴"])

    # ── Edit form ──
    with detail_tab:
        with st.form("edit_form"):
            current_stage_idx = (
                stages.index(row["ステージ"]) if row["ステージ"] in stages else 0
            )
            new_stage = st.selectbox("ステージ", stages, index=current_stage_idx)

            current_amount = int(row["金額"]) if pd.notna(row["金額"]) else 0
            new_amount = st.number_input("金額 (¥)", value=current_amount, step=10000)

            current_close = datetime.strptime(row["CloseDate"], "%Y-%m-%d").date()
            new_close = st.date_input("CloseDate", value=current_close)

            submitted = st.form_submit_button("更新", type="primary")

        if submitted:
            updates: dict = {}
            if new_stage != row["ステージ"]:
                updates["StageName"] = new_stage
            if new_amount != current_amount:
                updates["Amount"] = new_amount
            if new_close != current_close:
                updates["CloseDate"] = new_close.isoformat()

            if not updates:
                st.info("変更はありません。")
            else:
                try:

                    @with_sf_retry
                    def _update():
                        sf_client.update_opportunity(sf, opp_id, updates)

                    _update()
                    refresh_data()
                    st.success("商談を更新しました。")
                except Exception as e:
                    st.error(f"更新エラー: {e}")

    # ── Task history ──
    with task_tab:
        try:

            @with_sf_retry
            def _load_tasks():
                return sf_client.get_tasks(sf, opp_id)

            tasks_df = _load_tasks()
        except Exception:
            tasks_df = pd.DataFrame()

        if not tasks_df.empty:
            st.dataframe(
                tasks_df[["件名", "ステータス", "活動日", "説明"]],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("活動履歴はありません。")

        st.subheader("新規活動登録")
        with st.form("new_task_form"):
            task_subject = st.text_input("件名")
            task_desc = st.text_area("説明")
            task_status = st.selectbox(
                "ステータス",
                ["Not Started", "In Progress", "Completed", "Waiting on someone else", "Deferred"],
            )
            task_date = st.date_input("活動日", value=date.today())
            task_submitted = st.form_submit_button("登録", type="primary")

        if task_submitted:
            if not task_subject:
                st.error("件名は必須です。")
            else:
                try:

                    @with_sf_retry
                    def _create():
                        sf_client.create_task(
                            sf, opp_id, task_subject, task_desc,
                            task_status, task_date.isoformat(),
                        )

                    _create()
                    st.success("活動を登録しました。")
                except Exception as e:
                    st.error(f"登録エラー: {e}")


# ── Page: Ask AI ───────────────────────────────────────────────────

def page_ask_ai():
    if not sf:
        st.warning("Salesforceに接続してください。")
        return

    st.header("Ask AI")
    st.caption("Salesforceの商談データについて質問できます")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display chat history
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    prompt = st.chat_input("質問を入力してください（例: 今月クローズ予定の商談は？）")
    if not prompt:
        return

    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Build context from SF data
    opp_df = load_opportunities()
    opp_json = opp_df.to_json(orient="records", force_ascii=False)

    try:
        client = llm_client.get_llm_client()
        model = llm_client.get_model_name()

        system_prompt = llm_client.build_system_prompt(opp_json)
        api_messages = [{"role": "system", "content": system_prompt}]
        # Include recent history (last 10 turns)
        for msg in st.session_state.messages[-10:]:
            api_messages.append({"role": msg["role"], "content": msg["content"]})

        with st.chat_message("assistant"):
            response = st.write_stream(
                llm_client.chat_stream(client, model, api_messages)
            )

        st.session_state.messages.append({"role": "assistant", "content": response})

    except Exception as e:
        st.error(f"AI応答エラー: {e}")


# ── Main router ────────────────────────────────────────────────────

if page == "商談一覧":
    page_opportunities()
else:
    page_ask_ai()
