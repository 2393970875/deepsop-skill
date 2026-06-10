#!/usr/bin/env python3
"""
DeepSOP SocialHub Apify Store search script.

Calls the DeepSOP backend proxy endpoint instead of using Apify credentials
directly. The request must carry the shared DEEPSOP_API_KEY in X-Api-Key.
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

import requests


API_PREFIX = "https://ai.deepsop.com/prod-api"
STORE_PATH = "/ai/apify/store"


def _read_env_file_value(path, key):
    """Read KEY=value from a simple .env file without requiring python-dotenv."""
    try:
        if not path or not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                if name.strip() == key:
                    return value.strip().strip('"\'')
    except Exception:
        return None
    return None


def _read_openclaw_json_api_key(skill_name=None):
    """Read DEEPSOP_API_KEY from ~/.openclaw/openclaw.json."""
    try:
        config_path = Path.home() / ".openclaw" / "openclaw.json"
        if not config_path.is_file():
            return None
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        entries = data.get("skills", {}).get("entries", {})
        candidate_names = []
        if skill_name:
            candidate_names.append(skill_name)
        candidate_names.extend([name for name in entries if str(name).startswith("deepsop-")])

        seen = set()
        for name in candidate_names:
            if name in seen:
                continue
            seen.add(name)
            entry = entries.get(name)
            if not isinstance(entry, dict):
                continue
            for value in (
                entry.get("apiKey"),
                entry.get("env", {}).get("DEEPSOP_API_KEY") if isinstance(entry.get("env"), dict) else None,
            ):
                if isinstance(value, str) and value.strip():
                    return value.strip()
    except Exception:
        return None
    return None


def load_deepsop_api_key():
    """Load the shared DeepSOP API key from env or common .env locations."""
    key = os.environ.get("DEEPSOP_API_KEY", "").strip()
    if key:
        return key

    skill_dir = Path(__file__).resolve().parent.parent
    key = _read_openclaw_json_api_key(skill_dir.name)
    if key:
        os.environ["DEEPSOP_API_KEY"] = key
        return key

    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent.parent / ".env",
        Path.home() / ".openclaw" / ".env",
    ]
    for env_path in candidates:
        key = _read_env_file_value(str(env_path), "DEEPSOP_API_KEY")
        if key:
            os.environ["DEEPSOP_API_KEY"] = key
            return key
    return None


def get_headers():
    """Build request headers with the shared DeepSOP API key."""
    api_key = load_deepsop_api_key()
    return {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
    }


def check_api_key():
    if load_deepsop_api_key():
        return
    print("错误：未配置 DEEPSOP_API_KEY 环境变量", file=sys.stderr)
    print("请先在 OPClaw 项目设置中配置 DEEPSOP_API_KEY。", file=sys.stderr)
    print("非 OPClaw 运行时，请让用户授权后把 API Key 配置为共享环境变量或 ~/.openclaw/openclaw.json。", file=sys.stderr)
    sys.exit(1)


def build_store_url(search, limit=10, offset=0):
    query = urlencode(
        {
            "search": search,
            "limit": int(limit),
            "offset": int(offset),
            "responseFormat": "agent",
        },
        quote_via=quote,
    )
    return f"{API_PREFIX}{STORE_PATH}?{query}"


def search_store(search, limit=10, offset=0):
    """Search Apify Store through the DeepSOP backend."""
    check_api_key()
    url = build_store_url(search, limit, offset)
    response = requests.get(url, headers=get_headers(), timeout=60)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") not in (None, 200):
        raise RuntimeError(payload.get("msg") or "DeepSOP Apify Store search failed")
    return payload


def extract_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("rows", "list", "items", "records"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []


def item_value(item, *keys):
    if not isinstance(item, dict):
        return ""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def print_table(items, search, limit, offset):
    print(f"\n{'=' * 120}")
    print(f"  Apify Store Search: '{search}' (limit={limit}, offset={offset}, got={len(items)})")
    print(f"{'=' * 120}")
    print(f"  {'#':<3} {'Name':<34} {'User':<22} {'Pricing':<14} Description")
    print(f"  {'-' * 115}")

    for index, item in enumerate(items, offset + 1):
        name = str(item_value(item, "name", "title", "actorId", "id"))[:32] or "-"
        username = str(item_value(item, "username", "userName", "authorUsername", "ownerUsername"))[:20] or "-"
        pricing = str(item_value(item, "pricing", "pricingModel", "pricePerUnitUsd"))[:12] or "-"
        description = str(item_value(item, "description", "shortDescription", "summary"))[:55] or "-"
        print(f"  {index:<3} {name:<34} {username:<22} {pricing:<14} {description}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python search_instagram.py <search> [limit] [offset]", file=sys.stderr)
        sys.exit(1)

    search = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    offset = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    try:
        payload = search_store(search, limit=limit, offset=offset)
        items = extract_items(payload)

        with open("apify_store_output.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print_table(items, search, limit, offset)
        print("\n  Data saved to apify_store_output.json")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
