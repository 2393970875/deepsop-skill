import importlib.util
from pathlib import Path
from urllib.parse import parse_qs, urlparse


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "search_instagram.py"


def load_module(monkeypatch):
    monkeypatch.setenv("DEEPSOP_API_KEY", "sk-test")
    monkeypatch.delenv("APIFY_TOKEN", raising=False)
    spec = importlib.util.spec_from_file_location("search_instagram", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_store_url_uses_deepsop_backend_with_pagination(monkeypatch):
    module = load_module(monkeypatch)

    url = module.build_store_url("web scraper", limit=10, offset=20)

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "ai.deepsop.com"
    assert parsed.path == "/prod-api/ai/apify/store"
    assert "search=web%20scraper" in parsed.query
    assert parse_qs(parsed.query) == {
        "search": ["web scraper"],
        "limit": ["10"],
        "offset": ["20"],
        "responseFormat": ["agent"],
    }


def test_get_headers_reads_deepsop_api_key(monkeypatch):
    module = load_module(monkeypatch)

    headers = module.get_headers()

    assert headers["X-Api-Key"] == "sk-test"
    assert headers["Content-Type"] == "application/json"
