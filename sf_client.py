"""Salesforce client module for Opportunity CRUD operations."""

import os
from typing import Any

import pandas as pd
from simple_salesforce import Salesforce, SalesforceAuthenticationFailed


def get_connection() -> Salesforce:
    """Establish connection to Salesforce.

    Supports two auth modes:
    1. Access token + instance URL (SF_ACCESS_TOKEN, SF_INSTANCE_URL)
    2. Username + password + security token (SF_USERNAME, SF_PASSWORD, SF_SECURITY_TOKEN)
    """
    access_token = os.environ.get("SF_ACCESS_TOKEN", "")
    instance_url = os.environ.get("SF_INSTANCE_URL", "")

    if access_token and instance_url:
        return Salesforce(session_id=access_token, instance_url=instance_url)

    username = os.environ.get("SF_USERNAME", "")
    password = os.environ.get("SF_PASSWORD", "")
    security_token = os.environ.get("SF_SECURITY_TOKEN", "")
    domain = os.environ.get("SF_DOMAIN", "login")

    if not all([username, password, security_token]):
        raise ValueError(
            "SF_ACCESS_TOKEN+SF_INSTANCE_URL or SF_USERNAME+SF_PASSWORD+SF_SECURITY_TOKEN must be set"
        )

    return Salesforce(
        username=username,
        password=password,
        security_token=security_token,
        domain=domain,
    )


def get_opportunities(sf: Salesforce) -> pd.DataFrame:
    """Fetch all Opportunities with Account name."""
    query = """
        SELECT Id, Name, StageName, Amount, CloseDate,
               Account.Name, OwnerId, CreatedDate
        FROM Opportunity
        ORDER BY CloseDate DESC
    """
    records = sf.query_all(query)["records"]
    rows = []
    for r in records:
        rows.append({
            "Id": r["Id"],
            "商談名": r["Name"],
            "取引先": r["Account"]["Name"] if r["Account"] else "",
            "ステージ": r["StageName"],
            "金額": r.get("Amount"),
            "CloseDate": r["CloseDate"],
            "作成日": r["CreatedDate"][:10] if r.get("CreatedDate") else "",
        })
    return pd.DataFrame(rows)


def update_opportunity(
    sf: Salesforce, opp_id: str, fields: dict[str, Any]
) -> bool:
    """Update an Opportunity record. Returns True on success."""
    sf.Opportunity.update(opp_id, fields)
    return True


def get_tasks(sf: Salesforce, opp_id: str) -> pd.DataFrame:
    """Fetch Tasks linked to a specific Opportunity."""
    query = f"""
        SELECT Id, Subject, Description, Status, ActivityDate
        FROM Task
        WHERE WhatId = '{opp_id}'
        ORDER BY ActivityDate DESC
    """
    records = sf.query_all(query)["records"]
    rows = []
    for r in records:
        rows.append({
            "Id": r["Id"],
            "件名": r.get("Subject", ""),
            "説明": r.get("Description", ""),
            "ステータス": r.get("Status", ""),
            "活動日": r.get("ActivityDate", ""),
        })
    return pd.DataFrame(rows)


def create_task(
    sf: Salesforce,
    opp_id: str,
    subject: str,
    description: str,
    status: str,
    activity_date: str,
) -> str:
    """Create a new Task for an Opportunity. Returns the new Task Id."""
    result = sf.Task.create({
        "WhatId": opp_id,
        "Subject": subject,
        "Description": description,
        "Status": status,
        "ActivityDate": activity_date,
    })
    return result["id"]


def create_opportunity(
    sf: Salesforce,
    name: str,
    account_id: str,
    stage: str,
    amount: float,
    close_date: str,
) -> str:
    """Create a new Opportunity. Returns the new Opportunity Id."""
    result = sf.Opportunity.create({
        "Name": name,
        "AccountId": account_id,
        "StageName": stage,
        "Amount": amount,
        "CloseDate": close_date,
    })
    return result["id"]


def get_accounts_with_ids(sf: Salesforce) -> list[dict]:
    """Fetch Account names and Ids."""
    records = sf.query_all("SELECT Id, Name FROM Account ORDER BY Name")["records"]
    return [{"Id": r["Id"], "Name": r["Name"]} for r in records]


def get_accounts(sf: Salesforce) -> list[str]:
    """Fetch distinct Account names for filter options."""
    query = """
        SELECT Name FROM Account ORDER BY Name
    """
    records = sf.query_all(query)["records"]
    return [r["Name"] for r in records]


def get_stage_names(sf: Salesforce) -> list[str]:
    """Fetch available Opportunity stage names from metadata."""
    desc = sf.Opportunity.describe()
    for field in desc["fields"]:
        if field["name"] == "StageName":
            return [pv["value"] for pv in field["picklistValues"] if pv["active"]]
    return []
