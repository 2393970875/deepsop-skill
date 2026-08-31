#!/usr/bin/env python3
"""
AI Image Generator - Async Image Generation Script

Calls the AI Artist API to generate images from text prompts.
Handles async task polling until completion.

Supports Feishu webhook callback for result notification.
Set FEISHU_WEBHOOK_URL environment variable to enable.

Supports local file upload for reference images/videos.
Local files are automatically uploaded to get public URLs before calling generation APIs.
"""

import requests
import json
import time
import sys
import argparse
import os
import base64
import getpass
import re
from fractions import Fraction
from pathlib import Path

# Configuration
API_PREFIX = "https://ai.deepsop.com/prod-api/"
BASE_URL = f"{API_PREFIX.rstrip('/')}/ai"
FILE_UPLOAD_URL = f"{API_PREFIX.rstrip('/')}/system/fileUpload/upload"
ESTIMATE_COST_URL = f"{BASE_URL}/estimate/cost"
MODEL_LIST_URL = f"{BASE_URL}/consumeSource/list?pageNum=1&pageSize=999"
RECHARGE_URL = "https://ai.deepsop.com/"
MODEL_SOURCE_TYPES = ["IMAGE_MODEL", "VIDEO_MODEL", "HUMAN_MODEL"]
MODEL_SOURCE_TYPE_TO_MEDIA = {
    "IMAGE_MODEL": "image",
    "VIDEO_MODEL": "video",
    "HUMAN_MODEL": "human",
}
MEDIA_TYPE_TO_MODEL_SOURCE_TYPE = {
    "image": "IMAGE_MODEL",
    "video": "VIDEO_MODEL",
    "human": "HUMAN_MODEL",
}

_MODEL_NAME_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_MODEL_DESC_SPLIT_RE = re.compile(r"[\s,，。；;、/|()（）\[\]【】]+")
_MODEL_MATCH_TERMS = (
    "数字人", "带货", "真人", "口型", "嘴型", "音频", "人像", "虚拟形象", "动漫角色",
    "视频", "图片", "参考", "音画同步", "竖屏", "讲解",
)

def _normalize_model_name(value):
    """Normalize API/local model names for loose matching without exposing them as rules."""
    if value is None:
        return ""
    return "".join(_MODEL_NAME_TOKEN_RE.findall(str(value).lower()))

def _model_name_matches(row, local_key):
    """Return True when a server row appears to be the same named model as local_key."""
    needle_values = [local_key]
    cfg = MODEL_CONFIGS.get(local_key, {}) if "MODEL_CONFIGS" in globals() else {}
    needle_values.extend([cfg.get("source_name"), cfg.get("description")])
    haystack_values = [row.get("sourceName"), row.get("sourceDescription"), row.get("sourceKey")]
    needles = [n for n in (_normalize_model_name(v) for v in needle_values) if n]
    haystack = " ".join(_normalize_model_name(v) for v in haystack_values if v)
    return any(n and n in haystack for n in needles)


def _score_prompt_model_match(prompt, entry):
    """Score how well a live model row matches the user's prompt."""
    if not prompt:
        return 0
    prompt_text = str(prompt).lower()
    metadata = " ".join(
        str(entry.get(key) or "")
        for key in ("sourceName", "description", "sourceDescription", "remark", "sourceKey", "key")
    ).lower()
    if not metadata:
        return 0

    score = 0
    for token in _MODEL_DESC_SPLIT_RE.split(metadata):
        token = token.strip()
        if len(token) >= 2 and token in prompt_text:
            score += len(token)

    for term in _MODEL_MATCH_TERMS:
        if term in prompt_text and term in metadata:
            score += len(term) * 2

    prompt_words = set(_MODEL_NAME_TOKEN_RE.findall(prompt_text))
    metadata_words = set(_MODEL_NAME_TOKEN_RE.findall(metadata))
    score += sum(len(word) for word in prompt_words & metadata_words if len(word) >= 2)
    return score


# In-process cache for the model list (TTL seconds). Models can be toggled
# on/off server-side at any time, so explicit availability checks bypass the
# disk cache and prefer a fresh API response. The disk cache is only a best-
# effort fallback for list/default-model discovery when the API is unreachable.
_MODEL_LIST_CACHE = {"rows": None, "expires_at": 0.0}
_MODEL_LIST_TTL = 300  # 5 minutes
_MODEL_LIST_DISK_TTL = 300  # 5 minutes; reject stale/future-skewed cache files
import tempfile as _tempfile
_MODEL_LIST_DISK_CACHE = os.path.join(_tempfile.gettempdir(), "deepsop_model_list.json")

# Optionally load a .env file from the project root (best-effort; no hard dep)
try:
    from dotenv import load_dotenv as _load_dotenv  # type: ignore
    _load_dotenv()
except Exception:
    pass

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


def _load_deepsop_api_key():
    """Load the shared DeepSOP API key.

    OPClaw stores skill API keys in ~/.openclaw/openclaw.json.
    For compatibility, also check DEEPSOP_API_KEY and common .env locations so
    a single configured key can be reused by sibling DeepSOP skills.
    """
    key = os.environ.get("DEEPSOP_API_KEY", "").strip()
    if key:
        return key

    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    key = _read_openclaw_json_api_key(skill_dir.name)
    if key:
        os.environ["DEEPSOP_API_KEY"] = key
        return key

    candidates = [
        Path.cwd() / ".env",
        script_dir / ".env",
        skill_dir / ".env",
        Path.home() / ".openclaw" / ".env",
    ]
    for env_path in candidates:
        key = _read_env_file_value(str(env_path), "DEEPSOP_API_KEY")
        if key:
            os.environ["DEEPSOP_API_KEY"] = key
            return key
    return None


# Get API key from OPClaw/project environment or shared .env fallback.
API_KEY = _load_deepsop_api_key()

# Feishu webhook configuration (optional)
FEISHU_WEBHOOK_URL = os.environ.get("FEISHU_WEBHOOK_URL")

# Dry-run toggle: when True, task creators print the payload and skip network
# submission. Set via the CLI `--dry-run` flag or programmatically.
DRY_RUN = False
_LAST_ESTIMATE_FAILURE_REASON = None
_LAST_ESTIMATED_COST = None


class GenerationTaskCreationError(Exception):
    """Raised when the selected model fails at task creation and must not fallback."""


def _creation_failure_message(model, reason, media_label="任务"):
    return (
        f"{media_label}创建失败：模型 {model} 被当前请求拦截或拒绝，原因：{reason or '未知错误'}。"
        "已停止生成；请调整生成参数后重试，或选择其他模型重新生成。"
    )


# Keep stdout reserved for machine-readable final output (URL / JSON) so
# orchestrators like openclaw can parse it reliably. Human progress logs go
# to stderr via _progress().
try:
    sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
except Exception:
    pass


def _progress(msg):
    """Write a human-facing progress line to stderr (flushed immediately)."""
    print(msg, file=sys.stderr, flush=True)


def _emit_cli_result(result, args, markdown_label=""):
    """Always emit a single terminal line on stdout for orchestrators.

    Behavior:
      - `--json-output` → one-line JSON `{"status","url","message","local_path"?}`
      - `--markdown-output` → `![label](url)` when SUCCESS
      - default → raw URL when SUCCESS, nothing on stdout when failed (errors on stderr)

    Failures always emit a clear stderr message so humans still see them.
    """
    status = (result or {}).get("status") or "FAILED"
    url = (result or {}).get("url")
    message = (result or {}).get("message") or "未知错误"

    if getattr(args, "json_output", False):
        payload = {
            "status": status,
            "url": url,
            "message": message,
        }
        if isinstance(result, dict) and result.get("urls"):
            payload["urls"] = result["urls"]
        if isinstance(result, dict) and result.get("local_path"):
            payload["local_path"] = result["local_path"]
        estimated_cost = (result or {}).get("estimatedCost") if isinstance(result, dict) else None
        if estimated_cost is None:
            estimated_cost = _LAST_ESTIMATED_COST
        if estimated_cost is not None:
            payload["estimatedCost"] = estimated_cost
            payload["costUnit"] = "算力"
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        return

    if status == "SUCCESS" and url:
        if getattr(args, "markdown_output", False):
            print(f"![{markdown_label}]({url})", flush=True)
        else:
            print(url, flush=True)
    else:
        # Failure: keep stdout empty, surface a clear human message on stderr
        print(f"任务未成功：status={status}，message={message}", file=sys.stderr, flush=True)


def check_api_key():
    """Check if user has set their API key."""
    api_key = _load_deepsop_api_key()
    if not api_key:
        print("错误：未配置 DEEPSOP_API_KEY 环境变量", file=sys.stderr)
        print("", file=sys.stderr)
        print("请先在 OPClaw 项目设置中配置 DEEPSOP_API_KEY。", file=sys.stderr)
        print("如果不是从 OPClaw 运行，请让用户授权后把 API Key 配置为系统/用户级环境变量，其他 DeepSOP 技能也会共用：", file=sys.stderr)
        print("  Windows PowerShell: [System.Environment]::SetEnvironmentVariable('DEEPSOP_API_KEY', 'sk-your_api_key_here', 'User')", file=sys.stderr)
        print("  Linux/macOS: echo 'export DEEPSOP_API_KEY=\"sk-your_api_key_here\"' >> ~/.bashrc", file=sys.stderr)
        print("  或写入 ~/.openclaw/openclaw.json: DEEPSOP_API_KEY=sk-your_api_key_here", file=sys.stderr)
        print("", file=sys.stderr)
        print("配置后重新打开终端或重启 OPClaw 再运行。", file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(1)
    return True


def ensure_api_key_for_network():
    """Ensure a shared API key exists before network operations.

    In OPClaw this is normally injected via project settings. Outside OPClaw,
    allow an interactive user to paste the key once and persist it to
    ~/.openclaw/openclaw.json so sibling DeepSOP skills can reuse it. OPClaw's primary shared config is ~/.openclaw/openclaw.json.
    """
    api_key = _load_deepsop_api_key()
    if api_key:
        return api_key

    if sys.stdin.isatty():
        print("未检测到 DEEPSOP_API_KEY。请输入已授权的 DeepSOP API Key（输入将隐藏）：", file=sys.stderr)
        entered = getpass.getpass("DEEPSOP_API_KEY: ").strip()
        if entered:
            env_dir = Path.home() / ".openclaw"
            env_dir.mkdir(parents=True, exist_ok=True)
            env_file = env_dir / ".env"
            existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
            lines = [line for line in existing.splitlines() if not line.strip().startswith("DEEPSOP_API_KEY=")]
            lines.append(f"DEEPSOP_API_KEY={entered}")
            env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            os.environ["DEEPSOP_API_KEY"] = entered
            print(f"已保存到 {env_file}，其他 DeepSOP 技能也会共用。", file=sys.stderr)
            return entered

    check_api_key()
    return None


def get_headers():
    """Build request headers with API key."""
    api_key = _load_deepsop_api_key()
    return {
        "Content-Type": "application/json",
        "X-Api-Key": api_key
    }


def estimate_generation_cost(payload):
    global _LAST_ESTIMATE_FAILURE_REASON, _LAST_ESTIMATED_COST
    _LAST_ESTIMATE_FAILURE_REASON = None
    _LAST_ESTIMATED_COST = None
    try:
        response = requests.post(ESTIMATE_COST_URL, json=payload, headers=get_headers(), timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("code") != 200:
            _LAST_ESTIMATE_FAILURE_REASON = result.get('msg', '未知错误')
            print(f"费用预估失败：{_LAST_ESTIMATE_FAILURE_REASON}", file=sys.stderr)
            return False

        data = result.get("data") or {}
        estimated_cost = data.get("estimatedCost")
        sufficient_balance = data.get("sufficientBalance")

        if estimated_cost is not None:
            _LAST_ESTIMATED_COST = estimated_cost
            _progress(f"预估费用：{estimated_cost} 算力")

        if sufficient_balance is True:
            _progress("余额充足，正在创建任务")
            return True

        if sufficient_balance is False:
            _LAST_ESTIMATE_FAILURE_REASON = f"余额不足，无法提交创建任务。请前往 {RECHARGE_URL} 充值 算力后重试。"
            print(_LAST_ESTIMATE_FAILURE_REASON, file=sys.stderr)
            return False

        _LAST_ESTIMATE_FAILURE_REASON = "费用预估返回结果不完整"
        print(_LAST_ESTIMATE_FAILURE_REASON, file=sys.stderr)
        return False

    except requests.exceptions.HTTPError as e:
        _LAST_ESTIMATE_FAILURE_REASON = _explain_http_error(e, context="费用预估")
        print(_LAST_ESTIMATE_FAILURE_REASON, file=sys.stderr)
        return False
    except requests.exceptions.RequestException as e:
        _LAST_ESTIMATE_FAILURE_REASON = f"费用预估网络错误：{e}"
        print(_LAST_ESTIMATE_FAILURE_REASON, file=sys.stderr)
        return False
    except ValueError as e:
        _LAST_ESTIMATE_FAILURE_REASON = f"费用预估响应解析失败：{e}"
        print(_LAST_ESTIMATE_FAILURE_REASON, file=sys.stderr)
        return False


def _load_disk_cache():
    """Load the disk cache file if present and still fresh; return rows or None."""
    import time
    try:
        if not os.path.exists(_MODEL_LIST_DISK_CACHE):
            return None
        with open(_MODEL_LIST_DISK_CACHE, "r", encoding="utf-8") as f:
            blob = json.load(f)
        if not isinstance(blob, dict) or "rows" not in blob:
            return None
        now = time.time()
        expires_at = float(blob.get("expires_at", 0) or 0)
        # Guard against stale files and accidental far-future expiry values.
        if expires_at < now or expires_at > now + _MODEL_LIST_DISK_TTL:
            return None
        return blob["rows"]
    except Exception:
        return None


def _save_disk_cache(rows, expires_at):
    try:
        with open(_MODEL_LIST_DISK_CACHE, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "expires_at": expires_at}, f, ensure_ascii=False)
    except Exception:
        pass  # best-effort


def fetch_model_list(force_refresh=False):
    """Fetch the full model list from consumeSource/list with TTL caching.

    Caching layers (fastest first):
      1. process-local `_MODEL_LIST_CACHE`
      2. disk cache at `_MODEL_LIST_DISK_CACHE` (survives across CLI runs)
      3. network call to `consumeSource/list`

    Returns a list of dicts (possibly empty on total failure).
    """
    import time
    now = time.time()

    # (1) in-process cache
    if (not force_refresh
            and _MODEL_LIST_CACHE["rows"] is not None
            and _MODEL_LIST_CACHE["expires_at"] > now):
        return _MODEL_LIST_CACHE["rows"]

    # (2) disk cache seed
    if not force_refresh and _MODEL_LIST_CACHE["rows"] is None:
        disk_rows = _load_disk_cache()
        if disk_rows is not None:
            _MODEL_LIST_CACHE["rows"] = disk_rows
            _MODEL_LIST_CACHE["expires_at"] = now + _MODEL_LIST_TTL
            return disk_rows

    # (3) network
    try:
        response = requests.post(
            MODEL_LIST_URL,
            json={"sourceTypeList": MODEL_SOURCE_TYPES},
            headers=get_headers(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            print(f"模型列表查询失败：{payload.get('msg', '未知错误')}", file=sys.stderr)
            return _MODEL_LIST_CACHE["rows"] or []
        rows = payload.get("rows") or []
        expires_at = now + _MODEL_LIST_TTL
        _MODEL_LIST_CACHE["rows"] = rows
        _MODEL_LIST_CACHE["expires_at"] = expires_at
        _save_disk_cache(rows, expires_at)
        return rows
    except requests.exceptions.HTTPError as e:
        print(_explain_http_error(e, context="模型列表查询"), file=sys.stderr)
        if _MODEL_LIST_CACHE["rows"] is not None:
            return _MODEL_LIST_CACHE["rows"]
        return [] if force_refresh else (_load_disk_cache() or [])
    except Exception as e:
        print(f"[warn] 模型列表查询异常，使用上次缓存：{e}", file=sys.stderr)
        if _MODEL_LIST_CACHE["rows"] is not None:
            return _MODEL_LIST_CACHE["rows"]
        return [] if force_refresh else (_load_disk_cache() or [])


def check_model_available(model_key):
    """Verify the given model is currently active (hiddenState == '0').

    Returns True if usable, False if disabled or not found. On total network
    failure (no cache + request error) we return True so the user isn't blocked.
    """
    if model_key not in MODEL_CONFIGS:
        print(f"未知模型：{model_key}", file=sys.stderr)
        return False
    config = MODEL_CONFIGS[model_key]
    want_type = MEDIA_TYPE_TO_MODEL_SOURCE_TYPE.get(config["media_type"])
    want_value = str(config["methodType"])

    # Explicit model checks must not rely on disk cache: stale hiddenState data
    # can incorrectly report an enabled model such as V3.1FB as disabled.
    rows = fetch_model_list(force_refresh=True)
    if not rows:
        print(f"[warn] 无法实时确认 {model_key} 启用状态（模型列表为空），跳过停用校验", file=sys.stderr)
        return True

    matching_value_rows = [
        row for row in rows
        if row.get("sourceType") == want_type and str(row.get("sourceValue")) == want_value
    ]
    named_rows = [row for row in matching_value_rows if _model_name_matches(row, model_key)]
    rows_to_check = named_rows or matching_value_rows

    for row in rows_to_check:
        hidden = str(row.get("hiddenState"))
        if hidden == "1":
            print(
                f"API row {row.get('sourceName')} (sourceType={want_type}, "
                f"sourceValue={want_value}) has hiddenState=1; refusing to submit. "
                f"Refresh the model list before retrying.",
                file=sys.stderr,
            )
            return False
        if not named_rows and matching_value_rows:
            print(
                f"[warn] sourceValue={want_value} in {want_type} matched API row "
                f"{row.get('sourceName')} with a different local name; continuing by "
                f"API sourceValue and not by local alias status.",
                file=sys.stderr,
            )
        return True

    print(
        f"API {want_type} list does not contain sourceValue={want_value}; "
        f"do not infer disabled status from a local model in another media type. "
        f"Submission stopped.",
        file=sys.stderr,
    )
    return False


_VIDEO_KEYWORDS = (
    "视频", "动画", "短片", "片段", "动起来", "动图",
    "镜头", "运镜", "画面动", "跳动", "挥手", "旋转", "奔跑",
    "video", "clip", "motion", "animation", "animate", "mp4",
)
_IMAGE_KEYWORDS = (
    "图片", "图像", "画一", "插画", "海报", "壁纸", "封面",
    "肖像", "写真", "头像", "logo",
    "image", "picture", "poster", "wallpaper", "illustration",
)


def _infer_media_type(prompt):
    """Infer 'video' or 'image' from prompt text. Defaults to 'image' when ambiguous."""
    if not prompt:
        return "image"
    p = str(prompt).lower()
    has_video = any(k.lower() in p for k in _VIDEO_KEYWORDS)
    has_image = any(k.lower() in p for k in _IMAGE_KEYWORDS)
    # Prefer video only if it's the dominant cue: a "video" keyword is present
    # AND no image-specific keyword is competing with it.
    if has_video and not has_image:
        return "video"
    return "image"


def _get_default_model(media_type, prompt=None):
    """Pick the first active non-'auto' model of the given media_type from the
    API, mirroring the frontend behavior:

        this.form.methodType = this.videoModelOptions && this.videoModelOptions[0]?.sourceValue

    No hardcoded fallback: if the API is unreachable or returns no usable rows,
    returns None and lets the caller surface a clear error. This guarantees the
    default is always sourced from the live `consumeSource/list` response.
    """
    try:
        active = list_active_models().get(media_type, [])
    except Exception as e:
        print(f"[warn] 获取默认模型失败：{e}", file=sys.stderr)
        return None

    candidates = []
    for entry in active:
        # Same filter as frontend: !['auto'].includes(sourceValue) && hiddenState === '0'
        sval = str(entry.get("sourceValue") or "")
        if sval.lower() == "auto":
            continue
        # Prefer entries the script knows how to dispatch
        if entry.get("key"):
            candidates.append((entry, entry["key"]))
            continue
        # Otherwise translate sourceValue → friendly key (in case caller passes raw mt)
        resolved = _resolve_model_key(sval, media_type=media_type)
        if resolved:
            candidates.append((entry, resolved))

    best = None
    best_score = 0
    for entry, key in candidates:
        score = _score_prompt_model_match(prompt, entry)
        if score > best_score:
            best = key
            best_score = score
    if best:
        return best

    if candidates:
        return candidates[0][1]

    print(f"[warn] 服务端未返回可用的{media_type}模型（请查看 --list-models）", file=sys.stderr)
    return None


def recommend_model_for_prompt(prompt, media_type=None):
    """Return the best live model metadata match for an informational prompt."""
    inferred = media_type or "all"
    active_models = list_active_models()
    active = active_models.get(inferred, []) if inferred != "all" else active_models.get("all", [])
    best = None
    best_score = 0
    for entry in active:
        if str(entry.get("sourceValue") or "").lower() == "auto":
            continue
        score = _score_prompt_model_match(prompt, entry)
        if score > best_score:
            best = dict(entry)
            best_score = score
    if not best:
        return None
    best["matchScore"] = best_score
    return best


def _resolve_model_key(value, media_type=None):
    """Accept either a friendly key (e.g. 'HappyHorse') or a methodType
    string/int (e.g. '19', 19) and return the friendly key used internally.

    The friendly-name registry remains MODEL_CONFIGS (single source of truth).
    Existence and hiddenState are validated separately via the API.
    When a numeric methodType is reused by image and video models, `media_type`
    disambiguates it (for example image methodType=3 vs video V3.1FB=3).
    Returns None if the value cannot be resolved.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    alias = MODEL_ALIASES.get(s.lower())
    if alias:
        return alias
    # Direct friendly-key hit (case-insensitive)
    for key in MODEL_CONFIGS:
        if key.lower() == s.lower() and (media_type is None or MODEL_CONFIGS[key]["media_type"] == media_type):
            return key
    # methodType lookup (numeric or numeric-string)
    if s.isdigit():
        for key, cfg in MODEL_CONFIGS.items():
            if str(cfg["methodType"]) == s and (media_type is None or cfg["media_type"] == media_type):
                return key
    return None


def _validate_local_against_api():
    """Compare local MODEL_CONFIGS with the live consumeSource/list result and
    log drift warnings to stderr. Non-fatal: only informational.

    Detects:
      - server-side models the script does not know how to dispatch
      - locally registered models the server no longer exposes
      - sourceName / hiddenState changes worth noting
    """
    rows = fetch_model_list()
    if not rows:
        return  # network failure already logged by fetch_model_list

    seen_remote = set()  # set of (sourceType, sourceValue)
    for row in rows:
        stype = row.get("sourceType")
        if stype not in MODEL_SOURCE_TYPE_TO_MEDIA:
            continue
        sval = str(row.get("sourceValue"))
        seen_remote.add((stype, sval))
        if str(row.get("hiddenState")) != "0":
            continue
        # Find local key
        media = MODEL_SOURCE_TYPE_TO_MEDIA[stype]
        match = next(
            (k for k, cfg in MODEL_CONFIGS.items()
             if cfg["media_type"] == media and str(cfg["methodType"]) == sval),
            None,
        )
        if match is None:
            print(
                f"[drift] 服务端激活模型 {row.get('sourceName')} "
                f"(sourceType={stype}, sourceValue={sval}) 在脚本中未注册，"
                f"无法通过 --model 调用。请补充到 MODEL_CONFIGS。",
                file=sys.stderr,
            )

    # Reverse drift: local models the server no longer exposes
    for key, cfg in MODEL_CONFIGS.items():
        stype = MEDIA_TYPE_TO_MODEL_SOURCE_TYPE.get(cfg["media_type"])
        if (stype, str(cfg["methodType"])) not in seen_remote:
            print(
                f"[drift] 本地模型 {key} (sourceType={stype}, "
                f"methodType={cfg['methodType']}) 在服务端模型列表中不存在，"
                f"可能已下线。",
                file=sys.stderr,
            )


def list_active_models():
    """Return active (hiddenState == '0') models grouped by media type.

    Cross-references the server's consumeSource/list with local MODEL_CONFIGS
    for image/video/human dispatch keys.
    """
    rows = fetch_model_list()
    active_by_media = {"image": [], "video": [], "human": [], "all": []}
    for row in rows:
        if str(row.get("hiddenState")) != "0":
            continue
        stype = row.get("sourceType")
        media = MODEL_SOURCE_TYPE_TO_MEDIA.get(stype)
        if media is None:
            continue
        value = str(row.get("sourceValue"))
        # match back to a MODEL_CONFIGS key
        local_key = next(
            (k for k, cfg in MODEL_CONFIGS.items()
             if str(cfg["methodType"]) == value
             and cfg["media_type"] == media),
            None,
        )
        entry = {
            "key": local_key,
            "sourceName": row.get("sourceName"),
            "sourceValue": value,
            "sourceType": stype,
            "mediaType": media,
            "description": row.get("sourceDescription") or "",
            "remark": row.get("remark") or "",
            "sourceKey": row.get("sourceKey") or "",
        }
        active_by_media[media].append(entry)
        active_by_media["all"].append(entry)
    return active_by_media


def print_active_models():
    """Human-readable dump of currently active models."""
    data = list_active_models()
    print("=== 当前可用的图片模型 (hiddenState=0) ===")
    for m in data["image"]:
        key_hint = f"  key={m['key']}" if m["key"] else "  (脚本未注册)"
        print(f"- {m['sourceName']} [sourceValue={m['sourceValue']}]{key_hint}")
        if m["description"]:
            print(f"    {m['description']}")
    print("\n=== 当前可用的视频模型 (hiddenState=0) ===")
    for m in data["video"]:
        key_hint = f"  key={m['key']}" if m["key"] else "  (脚本未注册)"
        print(f"- {m['sourceName']} [sourceValue={m['sourceValue']}]{key_hint}")
        if m["description"]:
            print(f"    {m['description']}")
    print("\n=== 当前可用的数字人模型 (hiddenState=0) ===")
    for m in data["human"]:
        key_hint = f"  key={m['key']}" if m["key"] else "  (脚本未注册)"
        print(f"- {m['sourceName']} [sourceValue={m['sourceValue']}]{key_hint}")
        if m["description"]:
            print(f"    {m['description']}")
    print("\n默认模型来自接口的第一个非 auto 可用模型（无本地硬编码兜底）。")


_UPLOAD_SOFT_LIMIT_MB = 100  # generous cap; specific per-model caps are checked separately


def _explain_http_error(exc, context=""):
    """Produce a user-friendly message for common HTTP failure modes."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    prefix = f"{context} " if context else ""
    if status == 401:
        return (f"{prefix}认证失败 (401)。请确认环境变量 DEEPSOP_API_KEY 已设置且未过期，"
                f"并在 {RECHARGE_URL} 重新生成 API Key。")
    if status == 403:
        return f"{prefix}权限不足 (403)。当前 API Key 可能未授权该模型或功能。"
    if status == 429:
        return f"{prefix}请求过于频繁 (429)。请稍候 10-30 秒再重试，或降低并发。"
    if status and 500 <= status < 600:
        return f"{prefix}服务端错误 ({status})。请稍后重试；若持续发生请联系管理员。"
    return f"{prefix}网络/请求错误：{exc}"


def upload_file(file_path):
    """Upload a local file to the file server and get a public URL.

    Pre-checks file existence and size (soft cap 100MB) before uploading to
    avoid wasting bandwidth. Returns the public URL or None on failure.
    """
    if not os.path.exists(file_path):
        print(f"文件不存在：{file_path}", file=sys.stderr)
        return None

    try:
        file_size = os.path.getsize(file_path)
    except OSError as e:
        print(f"无法读取文件大小：{e}", file=sys.stderr)
        return None

    size_mb = file_size / (1024 * 1024)
    if size_mb > _UPLOAD_SOFT_LIMIT_MB:
        print(
            f"文件过大 ({size_mb:.1f} MB > {_UPLOAD_SOFT_LIMIT_MB} MB)，拒绝上传。"
            f"请压缩或分段后重试。",
            file=sys.stderr,
        )
        return None

    _progress(f"[upload] 开始上传 {os.path.basename(file_path)} ({size_mb:.2f} MB)…")
    try:
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f)}
            headers = {'X-Api-Key': API_KEY}
            response = requests.post(FILE_UPLOAD_URL, headers=headers, files=files, timeout=120)
            response.raise_for_status()
            result = response.json()

            if result.get("code") == 200:
                url = result.get("url")
                _progress(f"[upload] ✓ 上传完成：{url}")
                return url
            print(f"文件上传失败：{result.get('msg', '未知错误')}", file=sys.stderr)
            return None
    except requests.exceptions.HTTPError as e:
        print(_explain_http_error(e, context="文件上传"), file=sys.stderr)
        return None
    except Exception as e:
        print(f"文件上传错误：{e}", file=sys.stderr)
        return None


def download_image(url, output_path=None):
    """
    Download image from URL.
    
    Args:
        url: Image URL
        output_path: Optional path to save the image
    
    Returns:
        bytes: Image data, or None if failed
    """
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        image_data = response.content
        
        # Save to file if path provided
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(image_data)
            _progress(f"图片已保存：{output_path}")
        
        return image_data
        
    except Exception as e:
        print(f"下载图片失败：{e}", file=sys.stderr)
        return None


def image_to_data_uri(image_data, mime_type="image/png"):
    """
    Convert image bytes to data URI.
    
    Args:
        image_data: Raw image bytes
        mime_type: MIME type of the image
    
    Returns:
        str: Data URI string
    """
    base64_data = base64.b64encode(image_data).decode('utf-8')
    return f"data:{mime_type};base64,{base64_data}"


def send_feishu_message(prompt, result, media_type="image"):
    """Send generation result to Feishu chat (supports image or video)."""
    if not FEISHU_WEBHOOK_URL:
        return False

    label = "图片" if media_type == "image" else "视频"
    open_btn = "打开" + label
    try:
        if result and result["status"] == "SUCCESS":
            content = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"{label}生成成功"},
                        "template": "green"
                    },
                    "elements": [
                        {
                            "tag": "div",
                            "text": {
                                "tag": "lark_md",
                                "content": f"**提示词**: {prompt}\n\n**{label}链接**: [点击查看]({result['url']})"
                            }
                        },
                        {
                            "tag": "action",
                            "actions": [{
                                "tag": "button",
                                "text": {"tag": "plain_text", "content": open_btn},
                                "url": result["url"],
                                "type": "default"
                            }]
                        }
                    ]
                }
            }
        else:
            error_msg = result.get("message", "未知错误") if result else "未知错误"
            content = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": f"{label}生成失败"},
                        "template": "red"
                    },
                    "elements": [{
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": f"**提示词**: {prompt}\n\n**错误**: {error_msg}"
                        }
                    }]
                }
            }
        
        response = requests.post(
            FEISHU_WEBHOOK_URL,
            json=content,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        return True
        
    except Exception as e:
        print(f"[Feishu] 发送通知失败：{e}", file=sys.stderr)
        return False


# Model configurations
# media_type: "image" or "video" — determines task creation and output handling
# Keys follow API sourceName (DeepSop·X). Only hiddenState=0 (active) models are included.
# source_name / description mirror the API metadata for traceability.

# Note: per-model extra_params intentionally carry ONLY the fields each model
# actually accepts (cross-referenced with methodType field support).
# Target constraints (targetMaxSize / targetMinLength / targetMaxLength) are
# populated by `_apply_restriction()` at runtime and should NOT be duplicated here.

# ---------------------------------------------------------------------------
# Field → supported-models whitelist (mirrors frontend `handleParameterVisibility`).
# After the payload is built, fields not in the active model's whitelist are
# stripped so we don't send parameters the model does not understand.
# ---------------------------------------------------------------------------
# Image-side parameter whitelist (mirrors frontend `handleImgParameterVisibility`).
#   webSearch       → S5.0L (mt=4) + 3.1Nano2-Evo (mt=8)
#   imageSearch     → 3.1Nano2-Evo (mt=8)
#   ratiocination   → Image2 (mt=10)
#   n               → Image2 (mt=10)  [图片生成数量 1-10]
IMAGE_FIELD_SUPPORT_BY_MT = {
    "webSearch":     {"4", "8"},
    "imageSearch":   {"8"},
    "ratiocination": {"10"},
    "n":             {"10"},
    # Image2 Beta-Evo (mt=11) does NOT submit `quality` (frontend noField.quality=['11']).
    # Models listed here may submit `quality`; others are stripped before POST.
    "quality": {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"},
}

# Video-side: each key = optional field; value = set of methodType values that accept it.
# Fields NOT listed here (methodType, text, size, duration, generationType,
# imageUrlList, firstImageUrl, targetMax*) are considered universal/contextual
# and pass through unfiltered.
VIDEO_FIELD_SUPPORT_BY_MT = {
    # Negative prompt: V3.1 Fast/Pro + Wan series (mt 5,6,7,8,9,14,15,16)
    "negativePrompt": {"5", "6", "7", "8", "9", "14", "15", "16"},
    # Audio toggle: S1.5Pro, V3.1 Fast/Pro, klingV3Omni, Seedance2.0 family
    "generateAudio": {"2", "5", "6", "10", "17", "18", "20", "21", "22"},
    # English enhancement: V3.1 series (mt 3,4,5,6)
    "enhancePrompt": {"3", "4", "5", "6"},
    # Smart rewrite: Wan series (mt 7,8,9,14,15,16)
    "promptExtend": {"7", "8", "9", "14", "15", "16"},
    # Generation count / people / resize: V3.1 Fast/Pro (mt 5,6)
    "n": {"5", "6"},
    "personGeneration": {"5", "6"},
    "resizeMode": {"5", "6"},
    # Shot mode: Wan2.6 + klingV3Omni  (mt 7,8,9,10)
    "shotType": {"7", "8", "9", "10"},
    # Duration switch (manual/intelligent): S1.5Pro, Seedance2.0 family
    "durationSwitch": {"2", "17", "18", "20", "21", "22"},
    # Web search toggle: Seedance2.0 family
    "webSearch": {"17", "18", "20", "21", "22"},
    # klingV3Omni exclusives (mt 10)
    "mode": {"10"},
    "multiShot": {"10"},
    "multiPrompt": {"10"},
    "keepOriginalSound": {"10"},
    "elementList": {"10"},
    "videoList": {"10"},
    # Continuation / reference clip: klingV3Omni + W2.7i + HappyHorse  (mt 10,14,19)
    "firstClipUrl": {"10", "14", "19"},
    # Audio control mode (auto / origin): HappyHorse only, EDIT generationType  (mt 19)
    "audioSetting": {"19"},
    # Reference-video list: W2.6r / W2.7r / Seedance2.0 family
    "videoUrlList": {"9", "16", "17", "18", "20", "21", "22"},
    # Audio URL (single): Wan text/image/W2.7 series  (mt 7,8,14,15,16).
    # NOTE: Seedance2.0 family uses audioUrlList instead.
    "audioUrl": {"7", "8", "14", "15", "16"},
    # Audio URL list (multi): Seedance2.0 family
    "audioUrlList": {"17", "18", "20", "21", "22"},
}


VIDEO_FIELD_BLOCK_BY_MT = {
    # Sora2 BetaMax/Sora2/Sora2 Pro, Wan i2v, HappyHorse do not accept tail frame.
    "lastImageUrl": {"auto", "1", "8", "11", "12", "19"},
    # Wan i2v derives ratio from first frame.
    "ratio": {"8", "14"},
}


def _filter_by_whitelist(parameter, key, support_matrix):
    """Drop keys from `parameter` that the whitelist says this key doesn't accept."""
    key = str(key)
    for field, allowed_keys in support_matrix.items():
        if field in parameter and key not in allowed_keys:
            parameter.pop(field, None)
    return parameter


def _filter_video_fields(parameter, method_type):
    """Mirror frontend handleVideoParameterVisibility using methodType."""
    mt = str(method_type)
    _filter_by_whitelist(parameter, mt, VIDEO_FIELD_SUPPORT_BY_MT)
    for field, blocked_mts in VIDEO_FIELD_BLOCK_BY_MT.items():
        if field in parameter and mt in blocked_mts:
            parameter.pop(field, None)
    return parameter


# ---------------------------------------------------------------------------
# Allowed-value tables per model (mirrors frontend match* option builders).
# Values not listed will be auto-replaced with a safe fallback + warning.
# ---------------------------------------------------------------------------

# generationType whitelist by methodType (frontend matchGenerationTypeOptions).
VIDEO_GENERATION_TYPES_BY_MT = {
    "1": ["TEXT", "FIRST&LAST"],
    "2": ["TEXT", "FIRST&LAST"],
    "3": ["TEXT", "FIRST&LAST", "REFERENCE"],
    "4": ["TEXT", "FIRST&LAST"],
    "5": ["TEXT", "FIRST&LAST"],
    "6": ["TEXT", "FIRST&LAST"],
    "7": ["TEXT"],
    "8": ["FIRST&LAST"],
    "9": ["REFERENCE"],
    "10": ["TEXT", "FIRST&LAST", "REFERENCE", "EDIT", "FEATURE"],
    "11": ["TEXT", "FIRST&LAST"],
    "12": ["TEXT", "FIRST&LAST"],
    "13": ["TEXT", "FIRST&LAST", "REFERENCE"],
    "14": ["FIRST&LAST", "CONTINUATION"],
    "15": ["TEXT"],
    "16": ["REFERENCE"],
    "19": ["TEXT", "FIRST&LAST", "REFERENCE", "EDIT"],
}
VIDEO_GENERATION_TYPES_DEFAULT = ["TEXT", "FIRST&LAST", "REFERENCE"]

# ratio whitelist by methodType (frontend matchVideoRatioOptions).
VIDEO_RATIOS_BY_MT = {
    "auto": ["1:1", "4:3", "3:4", "7:4", "4:7", "16:9", "9:16", "21:9"],
    "1": ["16:9", "9:16"],
    "2": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
    "3": ["adaptive", "16:9", "9:16"],
    "4": ["adaptive", "16:9", "9:16"],
    "5": ["adaptive", "16:9", "9:16"],
    "6": ["adaptive", "16:9", "9:16"],
    "7": ["1:1", "4:3", "3:4", "16:9", "9:16"],
    "9": ["1:1", "4:3", "3:4", "16:9", "9:16"],
    "10": ["1:1", "16:9", "9:16"],
    "12": ["16:9", "9:16", "7:4", "4:7"],
    "15": ["1:1", "4:3", "3:4", "16:9", "9:16"],
    "16": ["1:1", "4:3", "3:4", "16:9", "9:16"],
    "17": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
    "18": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
    "19": ["1:1", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "21:9", "9:21"],
    "20": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
    "21": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
    "22": ["adaptive", "1:1", "4:3", "3:4", "16:9", "9:16", "21:9"],
}
VIDEO_RATIOS_DEFAULT = ["adaptive", "1:1", "4:3", "3:4", "7:4", "4:7", "16:9", "9:16", "21:9"]

# resolution whitelist by methodType (frontend matchVideoQualityOptions + latest rule update).
VIDEO_RESOLUTIONS_BY_MT = {
    "1": ["720p"],
    "2": ["480p", "720p", "1080p"],
    "3": ["720p"],
    "4": ["720p"],
    "5": ["720p", "1080p", "4K"],
    "6": ["720p", "1080p", "4K"],
    "7": ["720p", "1080p"],
    "8": ["720p", "1080p"],
    "9": ["720p", "1080p"],
    "10": ["720p", "1080p"],
    "11": ["720p"],
    "12": ["720p", "2K"],
    "14": ["720p", "1080p"],
    "15": ["720p", "1080p"],
    "16": ["720p", "1080p"],
    "17": ["480p", "720p", "1080p", "4K"],
    "18": ["480p", "720p"],
    "19": ["720p", "1080p"],
    "20": ["480p", "720p", "1080p", "4K"],
    "21": ["480p", "720p"],
    "22": ["480p", "720p"],
}
VIDEO_RESOLUTIONS_DEFAULT = ["480p", "720p", "1080p", "2K", "4K"]

# Image quality whitelist by methodType (matchImageQualityOptions).
# `Image2-Beta-Evo` (mt=11) intentionally absent: the frontend hides quality for it
# and the field is stripped via IMAGE_FIELD_SUPPORT_BY_MT["quality"] before POST.
IMAGE_QUALITIES_BY_MT = {
    "0": ["2K", "4K"],
    "1": ["1K"],
    "2": ["1K", "2K", "4K"],
    "3": ["1K", "2K", "4K"],
    "4": ["2K", "3K"],
    "5": ["1K", "2K", "4K"],
    "6": ["1K", "2K"],
    "7": ["1K", "2K"],
    "8": ["1K", "2K", "4K"],
    "9": ["1K", "2K", "4K"],
    "10": ["1K", "2K", "4K"],
    "11": ["1K", "2K", "4K"],
}
IMAGE_QUALITIES_DEFAULT = ["1K", "2K", "3K", "4K"]

# Image ratio/size exclusions (matchImageRatioOptions excludedRatios).
# Values listed are NOT allowed; empty set means any ratio allowed.
# Note: only relevant when the user passes a ratio-style size (e.g. "16:9");
# pixel-size strings like "2048x2048" / "2048*2048" pass through unchecked.
IMAGE_SIZE_EXCLUDED_BY_MT = {
    "auto": ["auto"],
    "0": ["auto"],
    "1": ["1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:8", "8:1", "4:5", "5:4", "9:21", "21:9"],
    "2": ["1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:8", "8:1", "9:21"],
    "3": ["auto", "1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:8", "8:1", "9:21"],
    "4": ["auto"],
    "5": ["auto", "1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:8", "8:1", "9:21"],
    "6": ["auto", "9:21", "21:9"],
    "7": ["auto", "9:21", "21:9"],
    "8": ["1:2", "2:1", "1:3", "3:1", "9:21"],
    "9": ["1:2", "2:1", "1:3", "3:1", "9:21"],
    "10": ["1:4", "4:1", "1:8", "8:1"],
    "11": ["1:4", "4:1", "1:8", "8:1", "4:5", "5:4"],
}


def _coerce_value(current, allowed, fallback, label, model):
    """If current not in allowed, warn and return fallback; else return current."""
    if current is None:
        return current
    if current in allowed:
        return current
    print(
        f"{model} 不支持 {label}={current!r}（可选：{allowed}），自动调整为 {fallback!r}",
        file=sys.stderr,
    )
    return fallback


# ---------------------------------------------------------------------------
# Per-methodType restrictions (sourced from frontend `Restrictions` mixin).
# - textLength / negativeTextLength → prompt length caps (chars)
# - targetMaxSize / targetMinLength / targetMaxLength → reference-image
#   constraints that MUST be forwarded to the API via the `targetMax*` fields.
# ---------------------------------------------------------------------------
VIDEO_RESTRICTIONS_BY_MT = {
    "1": {"textLength": 2500, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "2": {"textLength": 500, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
    "3": {"textLength": 1000, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "4": {"textLength": 1000, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "5": {"textLength": 1000, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "6": {"textLength": 1000, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "7": {"textLength": 750, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 360, "targetMaxLength": 2000},
    "8": {"textLength": 750, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 360, "targetMaxLength": 2000},
    "9": {"textLength": 750, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 240, "targetMaxLength": 5000},
    "10": {"textLength": 1250, "targetMaxSize": 10, "targetMinLength": 300},
    "11": {"textLength": 2500, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "12": {"textLength": 2500, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "13": {"textLength": 2500, "targetMaxSize": 10, "targetMinLength": 300, "targetMaxLength": 6000},
    "14": {"textLength": 2500, "negativeTextLength": 250, "targetMaxSize": 20, "targetMinLength": 240, "targetMaxLength": 8000},
    "15": {"textLength": 2500, "negativeTextLength": 250, "targetMaxSize": 20, "targetMinLength": 240, "targetMaxLength": 8000},
    "16": {"textLength": 2500, "negativeTextLength": 250, "targetMaxSize": 10, "targetMinLength": 240, "targetMaxLength": 5000},
    "17": {"textLength": 1000, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
    "18": {"textLength": 1000, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
    "19": {"textLength": 2500, "targetMaxSize": 20, "targetMinLength": 400, "targetMaxLength": 6000},
    "20": {"textLength": 1000, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
    "21": {"textLength": 1000, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
    "22": {"textLength": 1000, "targetMaxSize": 30, "targetMinLength": 300, "targetMaxLength": 6000},
}

IMAGE_RESTRICTIONS_BY_MT = {
    "0":  {"textLength": 300,   "targetMaxSize": 10, "targetMaxLength": 6000},
    "1":  {"textLength": 1000,  "targetMaxSize": 10, "targetMaxLength": 6000},
    "2":  {"textLength": 1000,  "targetMaxSize": 10, "targetMaxLength": 6000},
    "3":  {"textLength": 1000,  "targetMaxSize": 10, "targetMaxLength": 6000},
    "4":  {"textLength": 300,   "targetMaxSize": 10, "targetMaxLength": 6000},
    "5":  {"textLength": 1000,  "targetMaxSize": 10, "targetMaxLength": 6000},
    "6":  {"textLength": 2500,  "targetMaxSize": 20, "targetMaxLength": 8000, "targetMinLength": 240},
    "7":  {"textLength": 2500,  "targetMaxSize": 20, "targetMaxLength": 8000, "targetMinLength": 240},
    "8":  {"textLength": 1000,  "targetMaxSize": 20, "targetMaxLength": 6000},
    "9":  {"textLength": 1000,  "targetMaxSize": 10, "targetMaxLength": 6000},
    # GPT Image2 series: large prompt window, no max/min length constraint on refs.
    "10": {"textLength": 16000, "targetMaxSize": 50},
    "11": {"textLength": 16000, "targetMaxSize": 50},
}

# Render-quality (ratiocination) whitelist for Image2 (imageRenderQualityList).
IMAGE_RATIOCINATION_OPTIONS = ["low", "medium", "high"]


def _apply_restriction(parameter, restriction):
    """Overwrite targetMaxSize / targetMinLength / targetMaxLength per restriction."""
    for key in ("targetMaxSize", "targetMinLength", "targetMaxLength"):
        if key in restriction:
            parameter[key] = restriction[key]
        else:
            parameter.pop(key, None)


def _check_text_length(text, limit, label, model):
    """Warn (but don't block) when text exceeds the model's limit."""
    if text and limit and len(str(text)) > limit:
        print(
            f"⚠️  {model} {label} 长度 {len(text)} 超过限制 {limit}，已截断末尾 {len(text) - limit} 字符后提交",
            file=sys.stderr,
        )
        return str(text)[:limit]
    return text


# ---------------------------------------------------------------------------
# Base defaults (mirror frontend `defaultParameter` for moduleKey '9' video and
# '10' image). All per-model defaults are now derived from BASE_DEFAULTS plus
# methodType-driven overrides (mirroring frontend `handleMethodTypeChange` and
# the `case 'methodType'` reset block). Per-model overrides are kept ONLY for
# fields that cannot be inferred from methodType (e.g. S1.5Pro restrictions).
# ---------------------------------------------------------------------------
VIDEO_BASE_DEFAULTS = {
    "multiShot": False,
    "generationType": "",
    "text": "",
    "multiPrompt": [],
    "negativePrompt": "",
    "imageUrlList": [],
    "firstImageUrl": None,
    "lastImageUrl": None,
    "firstClipUrl": None,
    "elementList": [],
    "videoUrlList": [],
    "audioUrl": None,
    "audioUrlList": [],
    "keepOriginalSound": "yes",
    "durationList": [],
    "mode": "pro",
    "resolution": "720p",
    "ratio": "16:9",
    "generateAudio": True,
    "audioSetting": "auto",
    "enhancePrompt": False,
    "n": 1,
    "personGeneration": "allow_adult",
    "resizeMode": "pad",
    "promptExtend": False,
    "shotType": "single",
    "webSearch": False,
    "durationSwitch": "1",
    "duration": 10,
}

IMAGE_BASE_DEFAULTS = {
    "prompt": "",
    "image": [],
    "quality": "2K",
    "size": "1:1",
    "webSearch": False,
    "imageSearch": True,
    "ratiocination": "low",
    "n": 1,
}

HUMAN_BASE_DEFAULTS = {
    "req_key": "jimeng_realman_avatar_picture_omni_v15",
    "methodType": None,
    "prompt": "",
    "image_url": None,
    "video_url": None,
    "audio_url": None,
    "duration": None,
    "output_resolution": "720",
    "pe_fast_mode": True,
}

HUMAN_RESTRICTIONS_BY_MT = {
    "0": {"textLength": 300, "targetMaxSize": 5, "targetMaxLength": 4096},
    "1": {},
}

# Frontend `case 'methodType'` (moduleKey '9') sets generationType based on the
# new model's methodType:
#   ['7', '15']                      → 'TEXT'
#   ['1', '4', '5', '6', '8', '14']  → 'FIRST&LAST'
#   else                             → 'REFERENCE'
_VIDEO_GEN_TYPE_TEXT = {"7", "15"}
_VIDEO_GEN_TYPE_FIRST_LAST = {"1", "4", "5", "6", "8", "14"}


def _generation_type_for_method(method_type):
    """Mirror frontend default generationType selection on model switch."""
    mt = str(method_type)
    if mt in _VIDEO_GEN_TYPE_TEXT:
        return "TEXT"
    if mt in _VIDEO_GEN_TYPE_FIRST_LAST:
        return "FIRST&LAST"
    return "REFERENCE"


# Frontend `handleMethodTypeChange` for moduleKey '9' (video):
#   shotType: methodType === '10' ? 'multi' : 'single'
#   duration: ['auto', '3', '4', '5', '6', '11', '12'].includes(mt) ? 8 : 10
_VIDEO_SHORT_DURATION_MTS = {"auto", "3", "4", "5", "6", "11", "12"}


def _video_method_type_overrides(method_type):
    """Return field overrides derived from methodType (frontend handleMethodTypeChange)."""
    mt = str(method_type)
    return {
        "shotType": "multi" if mt == "10" else "single",
        "duration": 8 if mt in _VIDEO_SHORT_DURATION_MTS else 10,
    }


# Frontend `handleMethodTypeChange` for moduleKey '10' (image):
#   quality:   ['1', '10', '11'].includes(mt) ? '1K' : '2K'
#   size:      ['2', '8', '9', '10', '11'].includes(mt) ? 'auto' : '1:1'
#   webSearch: ['4', '8'].includes(mt)
_IMAGE_QUALITY_1K_MTS = {"1", "10", "11"}
_IMAGE_SIZE_AUTO_MTS = {"2", "8", "9", "10", "11"}
_IMAGE_WEB_SEARCH_MTS = {"4", "8"}


def _image_method_type_overrides(method_type):
    """Return field overrides derived from methodType (frontend handleMethodTypeChange)."""
    mt = str(method_type)
    return {
        "quality": "1K" if mt in _IMAGE_QUALITY_1K_MTS else "2K",
        "size": "auto" if mt in _IMAGE_SIZE_AUTO_MTS else "1:1",
        "webSearch": mt in _IMAGE_WEB_SEARCH_MTS,
    }


def _build_video_defaults(method_type):
    """Compose VIDEO_BASE_DEFAULTS + methodType-driven overrides + generationType rule."""
    params = dict(VIDEO_BASE_DEFAULTS)
    params.update(_video_method_type_overrides(method_type))
    params["generationType"] = _generation_type_for_method(method_type)
    return params


def _build_image_defaults(method_type):
    """Compose IMAGE_BASE_DEFAULTS + methodType-driven overrides."""
    params = dict(IMAGE_BASE_DEFAULTS)
    params.update(_image_method_type_overrides(method_type))
    return params


# Exact quality/ratio dimensions from frontend `getImageResolution`.
_IMAGE_RESOLUTION_BY_QUALITY = {
    "1K": {
        "1:1": (1024, 1024), "16:9": (1920, 1080), "9:16": (1080, 1920),
        "3:4": (768, 1024), "4:3": (1024, 768), "2:3": (682, 1024),
        "3:2": (1024, 682), "4:5": (1024, 1280), "5:4": (1280, 1024),
        "1:4": (512, 2048), "4:1": (2048, 512), "1:8": (362, 2896),
        "8:1": (2896, 362), "21:9": (2560, 1080),
    },
    "2K": {
        "1:1": (2048, 2048), "16:9": (2560, 1440), "9:16": (1440, 2560),
        "3:4": (1728, 2304), "4:3": (2304, 1728), "2:3": (1664, 2496),
        "3:2": (2496, 1664), "4:5": (1843, 2304), "5:4": (2304, 1843),
        "1:4": (1024, 4096), "4:1": (4096, 1024), "1:8": (724, 5792),
        "8:1": (5792, 724), "21:9": (3584, 1536),
    },
    "3K": {
        "1:1": (3072, 3072), "16:9": (4096, 2304), "9:16": (2304, 4096),
        "3:4": (2592, 3456), "4:3": (3456, 2592), "2:3": (2496, 3744),
        "3:2": (3744, 2496), "4:5": (2884, 3605), "5:4": (3605, 2884),
        "1:4": (1536, 6144), "4:1": (6144, 1536), "1:8": (1088, 8704),
        "8:1": (8704, 1088), "21:9": (4704, 2016),
    },
    "4K": {
        "1:1": (4096, 4096), "16:9": (3840, 2160), "9:16": (2160, 3840),
        "3:4": (3072, 4096), "4:3": (4096, 3072), "2:3": (2730, 4096),
        "3:2": (4096, 2730), "4:5": (3277, 4096), "5:4": (4096, 3277),
        "1:4": (2048, 8192), "4:1": (8192, 2048), "1:8": (1448, 11584),
        "8:1": (11584, 1448), "21:9": (5040, 2160),
    },
}

_IMAGE_RATIO_ONLY_METHOD_TYPES = {"1", "2", "3", "5", "8", "9"}
_IMAGE_RATIO_VALUES = {
    "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9",
    "21:9", "9:21", "1:2", "2:1", "1:3", "3:1", "1:4", "4:1", "1:8", "8:1",
}
_SEEDREAM5_METHOD_TYPES = {"4"}
_SEEDREAM5_MIN_PIXELS = 3_686_400
_IMAGE_PIXEL_SIZE_RE = re.compile(r"^\s*(\d+)\s*([x*])\s*(\d+)\s*$", re.IGNORECASE)


def _image_size_to_pixels(quality, ratio, sep):
    """Convert a ratio (e.g. '1:1', '16:9') + quality preset to a pixel string.

    Mirrors frontend `buildImageParams` which submits e.g. '2048x2048' for
    methodType ∈ {'0','4'} (sep='x') and '2048*2048' for {'6','7'} (sep='*').
    Falls back to `ratio` unchanged if it cannot be parsed.
    """
    if not ratio or ":" not in str(ratio):
        return ratio
    dimensions = _IMAGE_RESOLUTION_BY_QUALITY.get(quality, {}).get(str(ratio))
    if dimensions:
        return f"{dimensions[0]}{sep}{dimensions[1]}"
    try:
        a, b = [int(x) for x in str(ratio).split(":", 1)]
    except (ValueError, TypeError):
        return ratio
    if a <= 0 or b <= 0:
        return ratio
    long_side = {"1K": 1024, "2K": 2048, "3K": 3072, "4K": 4096}.get(quality, 2048)
    if a >= b:
        w, h = long_side, round(long_side * b / a)
    else:
        w, h = round(long_side * a / b), long_side
    return f"{w}{sep}{h}"


# methodType → pixel-size separator for image models that submit pixel form.
_IMAGE_PIXEL_SEP_BY_MT = {"0": "x", "4": "x", "6": "*", "7": "*"}
_IMAGE2_METHOD_TYPES = {"10", "11"}
_IMAGE2_SUPPORTED_SIZES = {
    "auto", "1:1", "1:2", "2:1", "1:3", "3:1", "2:3", "3:2",
    "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "9:21",
}


def _image_ratio_from_pixels(width, height, method_type, model, original_size):
    """Convert an exact supported pixel ratio back to the frontend ratio value."""
    ratio = Fraction(width, height)
    excluded = set(IMAGE_SIZE_EXCLUDED_BY_MT.get(str(method_type), []))
    for candidate in _IMAGE_RATIO_VALUES:
        if candidate in excluded:
            continue
        numerator, denominator = (int(part) for part in candidate.split(":", 1))
        if ratio == Fraction(numerator, denominator):
            return candidate
    raise GenerationTaskCreationError(
        f"{model} 不支持像素尺寸 size={original_size!r}，只能提交前端支持的比例"
    )


def _validate_seedream5_pixels(width, height, model, original_size):
    if width <= 0 or height <= 0:
        raise GenerationTaskCreationError(
            f"{model} 的 size={original_size!r} 非法，宽高必须为正整数"
        )
    if width * height < _SEEDREAM5_MIN_PIXELS:
        raise GenerationTaskCreationError(
            f"{model} 的 size={original_size!r} 非法，至少需要 {_SEEDREAM5_MIN_PIXELS} 像素"
        )


def _normalize_image_size(size, method_type, quality, model):
    """Normalize image size to the separator and value format expected by the model."""
    method_type = str(method_type)
    size_text = str(size).strip()
    pixel_match = _IMAGE_PIXEL_SIZE_RE.fullmatch(size_text)

    if pixel_match:
        width, separator, height = pixel_match.groups()
        width = int(width)
        height = int(height)

        if method_type in _IMAGE2_METHOD_TYPES:
            if width <= 0 or height <= 0:
                raise GenerationTaskCreationError(
                    f"{model} 的 size={size!r} 非法，宽高必须为正整数"
                )
            area = width * height
            aspect_ratio = max(width, height) / min(width, height)
            if width % 16 or height % 16:
                raise GenerationTaskCreationError(
                    f"{model} 的 size={size!r} 非法，宽高必须能被 16 整除"
                )
            if area < 640_000 or area > 8_290_000:
                raise GenerationTaskCreationError(
                    f"{model} 的 size={size!r} 非法，像素数必须在 0.64MP 到 8.29MP 之间"
                )
            if max(width, height) > 3840 or aspect_ratio > 3:
                raise GenerationTaskCreationError(
                    f"{model} 的 size={size!r} 非法，最长边不得超过 3840，宽高比不得超过 3:1"
                )
            if separator == "*":
                print(
                    f"{model} 兼容旧尺寸格式 size={size!r}，已规范化为 {width}x{height!s}",
                    file=sys.stderr,
                )
            return f"{width}x{height}"

        if method_type in _SEEDREAM5_METHOD_TYPES:
            _validate_seedream5_pixels(width, height, model, size)

        if method_type in _IMAGE_RATIO_ONLY_METHOD_TYPES:
            return _image_ratio_from_pixels(width, height, method_type, model, size)

        expected_separator = _IMAGE_PIXEL_SEP_BY_MT.get(method_type)
        if expected_separator:
            return f"{width}{expected_separator}{height}"
        return size_text

    if method_type in _IMAGE2_METHOD_TYPES:
        if size_text not in _IMAGE2_SUPPORTED_SIZES:
            raise GenerationTaskCreationError(
                f"{model} 不支持 size={size!r}，请使用 auto、支持的比例或 WxH 像素尺寸"
            )
        excluded = IMAGE_SIZE_EXCLUDED_BY_MT.get(method_type, [])
        if size_text in excluded:
            raise GenerationTaskCreationError(
                f"{model} 不支持 size={size!r}，请使用 auto、支持的比例或 WxH 像素尺寸"
            )
        return size_text

    excluded = IMAGE_SIZE_EXCLUDED_BY_MT.get(method_type, [])
    if size_text in excluded:
        raise GenerationTaskCreationError(
            f"{model} 不支持 size={size!r}，请使用前端允许的尺寸或比例"
        )

    return size_text

# Backward-compatible aliases accepted by --model. Canonical keys should match
# current sourceName/sourceValue semantics where possible.
MODEL_ALIASES = {
    "fb": "V3.1FB",
    "fbvideo": "V3.1FB",
    "fb-video": "V3.1FB",
    "fb视频": "V3.1FB",
    "v3.1 fb": "V3.1FB",
    "v3.1-fb": "V3.1FB",
    "v3.1fb": "V3.1FB",
    "v31fb": "V3.1FB",
    "n2-147": "Nano1Pro-147",
    "n2pro-147": "Nano2-147",
    "nano1-pro-147": "Nano1Pro-147",
    "nano1pro-147": "Nano1Pro-147",
    "nano2-147": "Nano2-147",
    "s2.0evo": "S2.0Evo",
    "s2.0-evo": "S2.0Evo",
    "s2.0fastevo": "S2.0FastEvo",
    "s2.0fast-evo": "S2.0FastEvo",
    "s2.0-fast-evo": "S2.0FastEvo",
}


MODEL_CONFIGS = {
    # ===== Image models (type=10) =====
    "N2": {
        "media_type": "image",
        "type": "10",
        "methodType": "2",
        "source_name": "DeepSop·Nano1 Pro",
        "description": "N2 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },
    "S5.0L": {
        "media_type": "image",
        "type": "10",
        "methodType": "4",
        "source_name": "DeepSop·S5.0L",
        "description": "生成快、风格全、易用，支持联网，适合快速出图",
        "extra_params": {"duration": 10}
    },
    "W2.7": {
        "media_type": "image",
        "type": "10",
        "methodType": "6",
        "source_name": "DeepSop.W2.7",
        "description": "W2.7 支持文生图、图生图多模态输入，画质清晰，细节丰富",
        "extra_params": {}
    },
    "W2.7Pro": {
        "media_type": "image",
        "type": "10",
        "methodType": "7",
        "source_name": "DeepSop.W2.7Pro",
        "description": "W2.7Pro 精准控图与风格迁移，角色一致性更优，画质细节更优",
        "extra_params": {}
    },
    "3.1Nano2-Evo": {
        "media_type": "image",
        "type": "10",
        "methodType": "8",
        "source_name": "DeepSop·Nano2",
        "description": "N2 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },
    "Nano2-Beta-Evo": {
        "media_type": "image",
        "type": "10",
        "methodType": "9",
        "source_name": "DeepSop·Nano2 Beta-Evo",
        "description": "N2 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },
    "Image2": {
        "media_type": "image",
        "type": "10",
        "methodType": "10",
        "source_name": "DeepSop·Image2",
        "description": "Image2 支持多模态图像生成 精准控图 细节丰富 角色一致性更优（GPTimage-2）",
        # ratiocination/imageSearch/n 均为 Image2 专属；默认不开启 imageSearch
        "extra_params": {"n": 1},
    },
    "Image2-Beta-Evo": {
        "media_type": "image",
        "type": "10",
        "methodType": "11",
        "source_name": "DeepSop·Image2 Beta-Evo",
        "description": "Image2 Beta（是否启用以服务端 consumeSource/list 为准）",
        # mt=11 不提交 quality 字段，但保留 default 以防调用者误传
        "extra_params": {},
    },
    # ----- Additional image models retained because frontend rules cover them -----
    "S4.5": {
        "media_type": "image",
        "type": "10",
        "methodType": "0",
        "source_name": "DeepSop·S4.5",
        "description": "S4.5 支持电影级画质4K 角色一致性",
        "extra_params": {}
    },
    "N1": {
        "media_type": "image",
        "type": "10",
        "methodType": "1",
        "source_name": "DeepSop·N1",
        "description": "N1 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },
    "Nano1Pro-147": {
        "media_type": "image",
        "type": "10",
        "methodType": "3",
        "source_name": "DeepSop-Nano1 Pro-147",
        "description": "N1 Pro 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },
    "Nano2-147": {
        "media_type": "image",
        "type": "10",
        "methodType": "5",
        "source_name": "DeepSop·Nano2-147",
        "description": "N2 支持多模态输入 精细参数调节 卓越的文字渲染和角色一致性",
        "extra_params": {}
    },

    # ===== Video models (type=9) =====
    "S1.5Pro": {
        "media_type": "video",
        "type": "9",
        "methodType": "2",
        "source_name": "DeepSop·S1.5Pro",
        "description": "S1.5Pro 影视级连贯叙事视频 音画同步与精准口型对齐",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "firstImageUrl": None,
            "lastImageUrl": None,
            "durationList": [],
            "enhancePrompt": False,
            "generateAudio": True,
            "n": 1,
            "personGeneration": "allow_adult",
            "resizeMode": "pad",
            "promptExtend": False,
            "shotType": "single",
            "durationSwitch": "1",
            "targetMaxSize": 30,
            "targetMinLength": 300,
            "targetMaxLength": 6000
        }
    },
    "V3.1FB": {
        "media_type": "video",
        "type": "9",
        "methodType": "3",
        "source_name": "DeepSop·V3.1FB",
        "description": "V3.1FB 快速生成 基础流畅",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "enhancePrompt": False,
            "durationList": [],
        }
    },
    "V3.1PB": {
        "media_type": "video",
        "type": "9",
        "methodType": "4",
        "source_name": "DeepSop·V3.1PB",
        "description": "V3.1Pro 多图参考 角色一致性",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "enhancePrompt": False,
            "durationList": [],
        }
    },
    "V3.1Fast": {
        "media_type": "video",
        "type": "9",
        "methodType": "5",
        "source_name": "DeepSop·V3.1Fast",
        "description": "V3.1Fast 快速生成 音画同步 竖屏适配",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "enhancePrompt": False,
            "generateAudio": True,
            "n": 1,
            "personGeneration": "allow_adult",
            "resizeMode": "pad",
            "durationList": [],
        }
    },
    "W2.6t": {
        "media_type": "video",
        "type": "9",
        "methodType": "7",
        "source_name": "DeepSop·W2.6t",
        "description": "W2.6t 文生视频 智能多镜头叙事 15秒 1080P高清",
        "extra_params": {
            "generationType": "TEXT",
            "negativePrompt": "",
            "promptExtend": False,
            "shotType": "single",
            "durationList": [],
        }
    },
    "W2.6i": {
        "media_type": "video",
        "type": "9",
        "methodType": "8",
        "source_name": "DeepSop·W2.6i",
        "description": "W2.6i 适合让插画或照片\"活起来\" 动作延展与场景叙事",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "promptExtend": False,
            "shotType": "single",
            "durationList": [],
        }
    },
    "W2.6r": {
        "media_type": "video",
        "type": "9",
        "methodType": "9",
        "source_name": "DeepSop·W2.6r",
        "description": "W2.6r 参考视频生成视频 保留角色和音色 可跨场景迁移与互动",
        "extra_params": {
            "generationType": "REFERENCE",
            "negativePrompt": "",
            "promptExtend": False,
            "shotType": "single",
            "durationList": [],
        }
    },
    "klingV3Omni": {
        "media_type": "video",
        "type": "9",
        "methodType": "10",
        "source_name": "DeepSop.klingV3Omni",
        "description": "支持多模态融合输入，画面细节丰富，角色与场景一致性更优（按张计费）",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "firstClipUrl": None,
            "elementList": [],
            "durationList": [],
            "mode": "pro",
            "multiShot": False,
            "keepOriginalSound": "yes",
            "generateAudio": True,
            "shotType": "single",
            "targetMaxSize": 10,
            "targetMinLength": 300,
            "targetMaxLength": 6000,
        }
    },
    "W2.7i": {
        "media_type": "video",
        "type": "9",
        "methodType": "14",
        "source_name": "DeepSop·W2.7i",
        "description": "W2.7i 图生视频 首尾帧平滑过渡 动作延展与视频续写 更流畅自然",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "promptExtend": False,
            "durationList": [],
        }
    },
    "W2.7t": {
        "media_type": "video",
        "type": "9",
        "methodType": "15",
        "source_name": "DeepSop.W2.7t",
        "description": "W2.7t 文生视频 智能多镜头剪辑 自动配音 2K高清 成片更高效",
        "extra_params": {
            "generationType": "TEXT",
            "negativePrompt": "",
            "promptExtend": False,
            "durationList": [],
        }
    },
    "W2.7r": {
        "media_type": "video",
        "type": "9",
        "methodType": "16",
        "source_name": "DeepSop.W2.7r",
        "description": "W2.7r 参考视频生成 保留角色音色 多模态融合编辑 跨场景迁移",
        "extra_params": {
            "generationType": "REFERENCE",
            "negativePrompt": "",
            "promptExtend": False,
            "durationList": [],
        }
    },
    "S2.0": {
        "media_type": "video",
        "type": "9",
        "methodType": "17",
        "source_name": "DeepSop·S2.0",
        "description": "Seedance2.0 物理一致性更优 多模态融合（图像/视频/音频参考）支持联网搜索",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "videoUrlList": [],
            "audioUrlList": [],
            "durationList": [],
            "generateAudio": True,
            "webSearch": False,
            "durationSwitch": "1",
        }
    },
    "S2.0Fast": {
        "media_type": "video",
        "type": "9",
        "methodType": "18",
        "source_name": "DeepSop·S2.0Fast",
        "description": "Seedance2.0 Fast 快速版 多模态融合（图像/视频/音频参考）支持联网搜索 最高 720P",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "videoUrlList": [],
            "audioUrlList": [],
            "durationList": [],
            "generateAudio": True,
            "webSearch": False,
            "durationSwitch": "1",
        }
    },
    "S2.0Evo": {
        "media_type": "video",
        "type": "9",
        "methodType": "20",
        "source_name": "DeepSop.S2.0  Evo",
        "description": "Seedance2.0 Evo 影视级视频生成 音画同步与精准口型对齐 支持多镜头叙事 4K高清",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "videoUrlList": [],
            "audioUrlList": [],
            "durationList": [],
            "generateAudio": True,
            "webSearch": False,
            "durationSwitch": "1",
        }
    },
    "S2.0FastEvo": {
        "media_type": "video",
        "type": "9",
        "methodType": "21",
        "source_name": "DeepSop.S2.0 Fast Evo",
        "description": "可快速制作真人视频，数字人带货视频，输出画面基础流畅，音画同步效果出色，兼容15秒竖屏视频规格",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "videoUrlList": [],
            "audioUrlList": [],
            "durationList": [],
            "generateAudio": True,
            "webSearch": False,
            "durationSwitch": "1",
        }
    },
    "S2.0Mini": {
        "media_type": "video",
        "type": "9",
        "methodType": "22",
        "source_name": "DeepSop.S2.0 Mini",
        "description": "Seedance2.0 Mini 视频生成模型",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "lastImageUrl": None,
            "videoUrlList": [],
            "audioUrlList": [],
            "durationList": [],
            "generateAudio": True,
            "webSearch": False,
            "durationSwitch": "1",
        }
    },
    "HappyHorse": {
        "media_type": "video",
        "type": "9",
        "methodType": "19",
        "source_name": "DeepSop.HappyHorse",
        "description": "HappyHorse 高效生成高质量短视频，适用于社交、广告等场景",
        "extra_params": {
            "generationType": "TEXT",
            "imageUrlList": None,
            "firstImageUrl": None,
            "firstClipUrl": None,
            "audioSetting": "auto",
        }
    },
    # ----- Additional video models exposed by consumeSource/list; availability is runtime-checked. -----
    "Sora2-BetaMax": {
        "media_type": "video",
        "type": "9",
        "methodType": "1",
        "source_name": "DeepSop·Sora2 Beta Max Evolink",
        "description": "Sora 2 Beta Max Evolink",
        "extra_params": {}
    },
    "V3.1Pro": {
        "media_type": "video",
        "type": "9",
        "methodType": "6",
        "source_name": "DeepSop·V3.1Pro",
        "description": "专业版模型 4K超清 多图参考角色跨场景一致性 商业级",
        "extra_params": {
            "generationType": "FIRST&LAST",
            "negativePrompt": "",
            "enhancePrompt": False,
            "generateAudio": True,
            "n": 1,
            "personGeneration": "allow_adult",
            "resizeMode": "pad",
            "durationList": [],
        }
    },
    "Sora2-147": {
        "media_type": "video",
        "type": "9",
        "methodType": "11",
        "source_name": "DeepSop·Sora2.147",
        "description": "物理真实、叙事连贯、音画同步，电影级质感",
        "extra_params": {}
    },
    "Sora2Pro-147": {
        "media_type": "video",
        "type": "9",
        "methodType": "12",
        "source_name": "DeepSop·Sora2 Pro.147",
        "description": "物理真实、时长更长、音画同步、画质专业、影视级可控性强",
        "extra_params": {}
    },
    "Sora2Pro-Evolink": {
        "media_type": "video",
        "type": "9",
        "methodType": "13",
        "source_name": "DeepSop·Sora2 Pro Evolink",
        "description": "原生视频生成，具备帧级动态控制、音画同步等视频专属能力",
        "extra_params": {}
    },

    # ===== Human models (type=12) =====
    "ImageDigitalHuman": {
        "media_type": "human",
        "type": "12",
        "methodType": "0",
        "source_name": "DeepSop.Image-digital human",
        "description": "上传人像图片和参考音频生成数字人视频",
        "extra_params": {}
    },
    "VideoDigitalHuman": {
        "media_type": "human",
        "type": "12",
        "methodType": "1",
        "source_name": "DeepSop.Video-digital human",
        "description": "上传人像视频和参考音频生成数字人视频",
        "extra_params": {}
    }
}


def create_video_task(prompt, model=None, ratio=None, resolution=None,
                      duration=None, first_image_url=None, last_image_url=None,
                      generate_audio=None, scale_factor=None, generation_type=None,
                      enhance_prompt=None, prompt_extend=None, audio_url=None,
                      image_url_list=None, video_url_list=None,
                      mode=None, keep_original_sound=None, shot_type=None,
                      element_list=None, first_clip_url=None, multi_shot=None,
                      n=None, person_generation=None, resize_mode=None,
                      negative_prompt=None, duration_switch=None,
                      multi_prompt=None, audio_url_list=None, web_search=None,
                      audio_setting=None):
    """Create a video generation task.

    Args:
        prompt: Text description of the video
        model: Video model key (e.g. S1.5Pro, V3.1FB, V3.1PB, V3.1Fast,
               W2.6t, W2.6i, W2.6r, klingV3Omni, W2.7i, W2.7t, W2.7r)
        ratio: Aspect ratio, e.g. '16:9', '9:16', '1:1'
        resolution: Video resolution, e.g. '720p', '1080p'
        duration: Video duration in seconds
        first_image_url: URL of the first frame image (FIRST&LAST mode)
        last_image_url: URL of the last frame image (FIRST&LAST mode)
        generate_audio: Whether to generate audio (True/False)
        scale_factor: Optional scaleFactor override
        generation_type: Generation type override, e.g. 'FIRST&LAST', 'TEXT', 'REFERENCE'
        enhance_prompt: Whether to enhance the prompt
        prompt_extend: Whether to extend the prompt
        audio_url: URL of audio file (WAN series)
        image_url_list: List of image URLs for reference (WAN *r / multimodal)
        video_url_list: List of video URLs for reference (WAN *r)
    """
    url = f"{BASE_URL}/AiArtistRecord"

    # API-driven default: when caller omits `model`, pick the first active
    # non-'auto' video model from consumeSource/list (no hardcoded fallback).
    if model is None:
        model = _get_default_model("video", prompt=prompt)
        if model is None:
            print(
                "无法从接口获取可用的视频模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None
        print(f"[auto] 使用接口返回的第一个可用视频模型 {model}", file=sys.stderr)

    # Accept friendly key or methodType (e.g. 'HappyHorse' or '19')
    resolved = _resolve_model_key(model, media_type="video")
    if resolved is None or MODEL_CONFIGS.get(resolved, {}).get("media_type") != "video":
        print(f"不支持的视频模型：{model}", file=sys.stderr)
        return None
    model = resolved
    config = MODEL_CONFIGS[model]
    method_type = str(config["methodType"])
    config = MODEL_CONFIGS[model]
    method_type = str(config["methodType"])

    # Prompt requirement (mirrors frontend handleVerifyParams):
    # - W2.6i / W2.7i (image-to-video) can omit prompt
    # - klingV3Omni with shotType='customize' uses per-shot prompts, not top-level
    # - all other video models require a non-empty prompt
    _image_to_video = method_type in {"8", "14"}
    _kling_customize = (method_type == "10" and shot_type == "customize")
    if not _image_to_video and not _kling_customize:
        if not prompt or not str(prompt).strip():
            print(f"模型 {model} 必须提供非空的生成提示词 (prompt)", file=sys.stderr)
            return None

    # Runtime availability check: consumeSource/list 可能随时将模型切成 hiddenState=1.
    # Skip in dry-run so payload debugging works without API credentials/network.
    if not DRY_RUN and not check_model_available(model):
        return None

    # Apply per-methodType length caps (truncate with warning, match frontend maxlength)
    restriction = VIDEO_RESTRICTIONS_BY_MT.get(method_type, {})
    prompt = _check_text_length(prompt, restriction.get("textLength"), "prompt", model)
    if negative_prompt is not None:
        negative_prompt = _check_text_length(
            negative_prompt, restriction.get("negativeTextLength"),
            "negativePrompt", model,
        )

    # Defaults follow the frontend pattern: BASE_DEFAULTS + handleMethodTypeChange
    # + 'methodType' switch reset block. No model-specific default_ratio /
    # default_resolution / default_duration overrides.
    base_params = _build_video_defaults(method_type)
    base_ratio = base_params["ratio"]
    base_resolution = base_params["resolution"]
    base_duration = base_params["duration"]

    effective_ratio = ratio or base_ratio
    effective_resolution = resolution or base_resolution
    effective_duration = duration or base_duration

    # Validate ratio / resolution / generationType against methodType whitelists.
    allowed_ratios = VIDEO_RATIOS_BY_MT.get(method_type, VIDEO_RATIOS_DEFAULT)
    allowed_resolutions = VIDEO_RESOLUTIONS_BY_MT.get(method_type, VIDEO_RESOLUTIONS_DEFAULT)
    allowed_generation_types = VIDEO_GENERATION_TYPES_BY_MT.get(method_type, VIDEO_GENERATION_TYPES_DEFAULT)
    effective_ratio = _coerce_value(effective_ratio, allowed_ratios, base_ratio, "ratio", model)
    effective_resolution = _coerce_value(
        effective_resolution, allowed_resolutions, base_resolution, "resolution", model,
    )
    if generation_type is not None:
        generation_type = _coerce_value(
            generation_type, allowed_generation_types,
            allowed_generation_types[0], "generationType", model,
        )

    # Start from frontend-equivalent base defaults, then layer any model-level
    # extra_params (kept only for fields that are NOT covered by BASE_DEFAULTS,
    # e.g. legacy targetMax* hints that are normalized later).
    parameter = base_params
    for key, value in config.get("extra_params", {}).items():
        if key not in VIDEO_BASE_DEFAULTS:
            parameter[key] = value

    # Resolve pixel size from ratio + resolution
    resolution_size_map = {
        ("16:9", "720p"): "1280x720",
        ("16:9", "1080p"): "1920x1080",
        ("9:16", "720p"): "720x1280",
        ("9:16", "1080p"): "1080x1920",
        ("1:1", "720p"): "720x720",
        ("1:1", "1080p"): "1080x1080",
        ("3:4", "720p"): "720x960",
        ("3:4", "1080p"): "1080x1440",
        ("4:3", "720p"): "960x720",
        ("4:3", "1080p"): "1440x1080",
    }
    pixel_size = resolution_size_map.get((effective_ratio, effective_resolution), effective_ratio)

    parameter.update({
        "methodType": config["methodType"],
        "text": prompt,
        "resolution": effective_resolution,
        "ratio": effective_ratio,
        "size": pixel_size,
        "duration": effective_duration,
    })

    # --- Duration rules (aligned with frontend `matchVideoDurationInfo`) ---
    # V3.1 Lite (mt=3/4): fixed 8 seconds
    if method_type in {"3", "4"}:
        if method_type == "3" and parameter.get("resolution") != "720p":
            print(
                f"{model} 固定只支持 720p，当前 {parameter.get('resolution')}，自动调整为 720p",
                file=sys.stderr,
            )
            parameter["resolution"] = "720p"
            if "quality" in parameter:
                parameter["quality"] = "720p"
        if effective_duration != 8:
            print(f"{model} 时长固定为 8 秒，当前 {effective_duration} 秒，自动调整为 8 秒")
            effective_duration = 8
            parameter["duration"] = effective_duration
        parameter["size"] = effective_ratio

    # V3.1 Fast/Pro (mt=5/6): 4 or 8 seconds
    if method_type in {"5", "6"}:
        if effective_duration not in [4, 8]:
            print(f"{model} 时长必须是 4 或 8 秒，当前 {effective_duration} 秒，自动调整为 8 秒")
            effective_duration = 8
            parameter["duration"] = effective_duration
        parameter["size"] = effective_ratio

    # WAN / kling / Seedance family groupings by methodType.
    wan_image_mts = {"8", "14"}
    wan_ref_mts = {"9", "16"}
    wan_mts = {"7", "8", "9", "14", "15", "16"}
    pixel_size_mts = {"7", "9"}  # only Wan2.6 t2v/r2v use '1280*720' form
    seedance2_mts = {"17", "18", "20", "21", "22"}

    # S1.5Pro (mt=2): duration 4-12s (frontend matchVideoDurationInfo)
    if method_type == "2":
        if effective_duration < 4 or effective_duration > 12:
            print(f"{model} 时长必须是 4-12 秒，当前 {effective_duration} 秒，自动调整为 10 秒",
                  file=sys.stderr)
            effective_duration = 10
            parameter["duration"] = effective_duration

    if method_type == "1":
        if effective_duration < 10 or effective_duration > 15:
            print(f"{model} 时长必须是 10-15 秒，当前 {effective_duration} 秒，自动调整为 10 秒",
                  file=sys.stderr)
            effective_duration = 10
            parameter["duration"] = effective_duration

    if method_type in {"11", "12", "13"}:
        if effective_duration < 4 or effective_duration > 12:
            print(f"{model} 时长必须是 4-12 秒，当前 {effective_duration} 秒，自动调整为 8 秒",
                  file=sys.stderr)
            effective_duration = 8
            parameter["duration"] = effective_duration

    if method_type == "19":
        # HappyHorse: duration 3-15s; EDIT mode derives duration from edit clip,
        # but we still keep a sane default in payload.
        if effective_duration < 3 or effective_duration > 15:
            print(f"{model} 时长必须是 3-15 秒，当前 {effective_duration} 秒，自动调整为 10 秒",
                  file=sys.stderr)
            effective_duration = 10
            parameter["duration"] = effective_duration
        # Submit ratio string as size (no pixel form)
        parameter["size"] = effective_ratio

    if method_type in seedance2_mts:
        # Seedance2.0 family: duration 4-15s (frontend matchVideoDurationInfo)
        if effective_duration < 4 or effective_duration > 15:
            print(f"{model} 时长必须是 4-15 秒，当前 {effective_duration} 秒，自动调整为 10 秒",
                  file=sys.stderr)
            effective_duration = 10
            parameter["duration"] = effective_duration
        # Size as ratio string (not pixel-serialized)
        parameter["size"] = effective_ratio

    if method_type in wan_mts or method_type == "10":
        # Duration range
        if method_type == "9":
            min_d, max_d, default_d = 3, 10, 10
        elif method_type == "16" and video_url_list:
            # W2.7r with reference video(s): 3-10s (frontend videoUrlList?.length)
            min_d, max_d, default_d = 3, 10, 10
        else:
            # W2.6t/W2.6i, W2.7t/W2.7i, klingV3Omni, W2.7r (no ref video) → 3-15s
            min_d, max_d, default_d = 3, 15, 10
        if effective_duration < min_d or effective_duration > max_d:
            print(f"{model} 时长必须是 {min_d}-{max_d} 秒，当前 {effective_duration} 秒，自动调整为 {default_d} 秒")
            effective_duration = default_d
            parameter["duration"] = effective_duration

        # Size serialization
        if method_type in pixel_size_mts:
            parameter["size"] = pixel_size.replace("x", "*")  # e.g., "1280*720"
        else:
            parameter["size"] = effective_ratio  # e.g., "16:9"

    # Image-to-video: auto-switch generationType based on first_image_url
    if method_type in wan_image_mts and generation_type is None:
        parameter["generationType"] = "FIRST&LAST"

    # Reference-to-video: force REFERENCE generationType (W2.6r / W2.7r)
    if method_type in wan_ref_mts:
        parameter["generationType"] = "REFERENCE"

    # Apply optional overrides
    if first_image_url is not None:
        parameter["firstImageUrl"] = first_image_url
    if last_image_url is not None:
        parameter["lastImageUrl"] = last_image_url
    if generate_audio is not None:
        parameter["generateAudio"] = generate_audio
    if scale_factor is not None:
        parameter["scaleFactor"] = scale_factor
    if generation_type is not None:
        parameter["generationType"] = generation_type
    if enhance_prompt is not None:
        parameter["enhancePrompt"] = enhance_prompt
    if prompt_extend is not None:
        parameter["promptExtend"] = prompt_extend
    # WAN series: audio_url, image_url_list, video_url_list
    if audio_url is not None:
        parameter["audioUrl"] = audio_url
    if image_url_list is not None:
        parameter["imageUrlList"] = image_url_list
    if video_url_list is not None:
        parameter["videoUrlList"] = video_url_list

    # Model-specific exclusives
    if mode is not None:
        parameter["mode"] = mode
    if keep_original_sound is not None:
        parameter["keepOriginalSound"] = keep_original_sound
    if shot_type is not None:
        parameter["shotType"] = shot_type
    if element_list is not None:
        parameter["elementList"] = element_list
    if first_clip_url is not None:
        parameter["firstClipUrl"] = first_clip_url
    if multi_shot is not None:
        parameter["multiShot"] = multi_shot
    if n is not None:
        if method_type in VIDEO_FIELD_SUPPORT_BY_MT.get("n", set()):
            parameter["n"] = n
    if person_generation is not None:
        parameter["personGeneration"] = person_generation
    if resize_mode is not None:
        parameter["resizeMode"] = resize_mode
    if negative_prompt is not None:
        parameter["negativePrompt"] = negative_prompt
    if duration_switch is not None:
        parameter["durationSwitch"] = duration_switch
    if multi_prompt is not None:
        parameter["multiPrompt"] = multi_prompt
    if audio_url_list is not None:
        parameter["audioUrlList"] = audio_url_list
    if web_search is not None:
        parameter["webSearch"] = bool(web_search)
    if audio_setting is not None:
        parameter["audioSetting"] = audio_setting

    # klingV3Omni customize shotType requires multiPrompt
    if method_type == "10" and parameter.get("shotType") == "customize" \
            and not parameter.get("multiPrompt"):
        print(
            "klingV3Omni shotType='customize' 需要传入 multi_prompt（分镜列表），"
            "当前为空，可能会被 API 拒绝",
            file=sys.stderr,
        )

    # klingV3Omni-specific serialization (mirrors frontend `buildNewParams`):
    #   - shotType 'multi' must be emitted as 'intelligence'
    #   - firstClipUrl + keep_original_sound are packed into a `videoList` array
    #     whose `refer_type` depends on generationType (base for EDIT, feature
    #     for FEATURE). generateAudio is disabled when a reference clip is given.
    if method_type == "10":
        if parameter.get("shotType") == "multi":
            parameter["shotType"] = "intelligence"

        clip_url = parameter.pop("firstClipUrl", None)
        if clip_url:
            gen_type = parameter.get("generationType")
            refer_type = "base" if gen_type == "EDIT" else "feature"
            parameter["videoList"] = [{
                "video_url": clip_url,
                "refer_type": refer_type,
                "keep_original_sound": parameter.get("keepOriginalSound", "yes"),
            }]
            # When a reference clip is supplied, mute generated audio (frontend rule)
            parameter["generateAudio"] = False

    # Reapply the text length-capped prompt / negativePrompt
    parameter["text"] = prompt
    if negative_prompt is not None:
        parameter["negativePrompt"] = negative_prompt

    # Overwrite targetMaxSize / targetMinLength / targetMaxLength per model
    _apply_restriction(parameter, restriction)

    # Strip fields this model does not accept (mirrors frontend visibility rules)
    _filter_video_fields(parameter, method_type)

    # HappyHorse generationType-conditional visibility (frontend handleMatchVisibility):
    #   - audioSetting: only visible when generationType === 'EDIT'
    #   - firstClipUrl: only visible when generationType in ('CONTINUATION','EDIT','FEATURE')
    #     (HappyHorse only supports EDIT among these)
    #   - ratio / duration: hidden in EDIT mode (derived from edit clip)
    if method_type == "19":
        gen_type = parameter.get("generationType")
        if gen_type != "EDIT":
            parameter.pop("audioSetting", None)
            parameter.pop("firstClipUrl", None)
        else:
            # EDIT mode: ratio + duration come from the edit clip; do not submit them
            parameter.pop("ratio", None)
            parameter.pop("duration", None)
            parameter.pop("size", None)

    # Frontend-equivalent preflight validation after all field normalization.
    gen_type = parameter.get("generationType")
    image_count = len(parameter.get("imageUrlList") or [])
    element_count = len(parameter.get("elementList") or [])
    video_count = len(parameter.get("videoUrlList") or [])
    audio_list_count = len(parameter.get("audioUrlList") or [])

    if parameter.get("lastImageUrl") and not parameter.get("firstImageUrl"):
        raise GenerationTaskCreationError(_creation_failure_message(model, "已传尾帧图片时必须同时提供首帧图片", "视频任务"))
    if method_type in {"8", "14", "19"} and gen_type == "FIRST&LAST" and not parameter.get("firstImageUrl"):
        raise GenerationTaskCreationError(_creation_failure_message(model, "FIRST&LAST 模式必须提供首帧图片", "视频任务"))
    if method_type == "14" and gen_type == "CONTINUATION" and not parameter.get("firstClipUrl"):
        raise GenerationTaskCreationError(_creation_failure_message(model, "CONTINUATION 模式必须提供续写视频 firstClipUrl", "视频任务"))
    if method_type == "10":
        if gen_type == "FIRST&LAST" and not parameter.get("firstImageUrl") and element_count == 0:
            raise GenerationTaskCreationError(_creation_failure_message(model, "FIRST&LAST 模式必须提供首帧图片或参考主体", "视频任务"))
        if gen_type == "REFERENCE" and image_count + element_count == 0:
            raise GenerationTaskCreationError(_creation_failure_message(model, "REFERENCE 模式必须至少提供一张参考图片或一个参考主体", "视频任务"))
        if gen_type in {"EDIT", "FEATURE"} and not parameter.get("videoList"):
            raise GenerationTaskCreationError(_creation_failure_message(model, "EDIT/FEATURE 模式必须提供编辑视频或参考视频", "视频任务"))
        if parameter.get("shotType") == "customize":
            bad_shot = any(not item.get("duration") or not item.get("prompt") for item in (parameter.get("multiPrompt") or []))
            if bad_shot:
                raise GenerationTaskCreationError(_creation_failure_message(model, "自定义分镜必须填写每个镜头的描述和非零时长", "视频任务"))
    if method_type in {"9", "16"} and (image_count + video_count == 0 or image_count + video_count > 5):
        raise GenerationTaskCreationError(_creation_failure_message(model, "参考图片+参考视频总数必须为 1-5", "视频任务"))
    if method_type in {"3", "4", "5", "6", "19"} and gen_type == "REFERENCE" and image_count == 0:
        raise GenerationTaskCreationError(_creation_failure_message(model, "REFERENCE 模式必须至少提供一张参考图片", "视频任务"))
    if method_type == "19" and gen_type == "EDIT" and not parameter.get("firstClipUrl"):
        raise GenerationTaskCreationError(_creation_failure_message(model, "EDIT 模式必须提供编辑视频 firstClipUrl", "视频任务"))
    if method_type in seedance2_mts and audio_list_count > 0 and image_count + video_count == 0:
        raise GenerationTaskCreationError(_creation_failure_message(model, "使用参考音频时必须至少提供一张参考图片或一个参考视频", "视频任务"))

    payload = {
        "type": config["type"],
        "methodType": config["methodType"],
        "parameter": json.dumps(parameter),
        "saveToDatabase": True,
    }

    if DRY_RUN:
        _progress("[dry-run] 视频任务 payload（未提交）:")
        _progress(json.dumps(payload, ensure_ascii=False, indent=2))
        return "DRY_RUN_TASK_ID"

    if not estimate_generation_cost(payload):
        message = _creation_failure_message(
            model, _LAST_ESTIMATE_FAILURE_REASON or "费用预估未通过", "视频任务"
        )
        raise GenerationTaskCreationError(message)

    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 200 and result.get("data"):
            return result["data"][0]
        else:
            reason = result.get('msg', '未知错误')
            message = _creation_failure_message(model, reason, "视频任务")
            print(message, file=sys.stderr)
            raise GenerationTaskCreationError(message)

    except requests.exceptions.HTTPError as e:
        message = _creation_failure_message(model, _explain_http_error(e, context="创建视频任务"), "视频任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e
    except requests.exceptions.RequestException as e:
        message = _creation_failure_message(model, f"网络错误：{e}", "视频任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e


def create_human_task(model=None, prompt="", image_url=None, video_url=None,
                      audio_url=None, duration=None, output_resolution=None,
                      pe_fast_mode=None):
    """Create a digital-human generation task matching frontend type=12 payload."""
    url = f"{BASE_URL}/AiArtistRecord"

    if model is None:
        model = _get_default_model("human", prompt=prompt)
        if model is None:
            print(
                "无法从接口获取可用的数字人模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None

    resolved = _resolve_model_key(model, media_type="human")
    if resolved is None or MODEL_CONFIGS.get(resolved, {}).get("media_type") != "human":
        print(f"不支持的数字人模型：{model}", file=sys.stderr)
        return None

    model = resolved
    config = MODEL_CONFIGS[model]
    method_type = str(config["methodType"])

    if not DRY_RUN and not check_model_available(model):
        return None

    if method_type == "0" and not image_url:
        raise GenerationTaskCreationError(_creation_failure_message(model, "methodType=0 必须上传人像图片 image_url", "数字人任务"))
    if method_type == "1" and not video_url:
        raise GenerationTaskCreationError(_creation_failure_message(model, "methodType=1 必须上传人像视频 video_url", "数字人任务"))
    if not audio_url:
        raise GenerationTaskCreationError(_creation_failure_message(model, "必须上传参考音频 audio_url", "数字人任务"))

    restriction = HUMAN_RESTRICTIONS_BY_MT.get(method_type, {})
    prompt = _check_text_length(prompt or "", restriction.get("textLength"), "prompt", model)
    effective_output_resolution = str(output_resolution or HUMAN_BASE_DEFAULTS["output_resolution"])
    if effective_output_resolution not in {"720", "1080"}:
        effective_output_resolution = "720"
    effective_pe_fast_mode = (
        effective_output_resolution == "720"
        if pe_fast_mode is None
        else bool(pe_fast_mode)
    )

    parameter = dict(HUMAN_BASE_DEFAULTS)
    parameter.update({
        "methodType": method_type,
        "prompt": prompt or "",
        "image_url": image_url,
        "video_url": video_url,
        "audio_url": audio_url,
        "duration": duration,
        "output_resolution": effective_output_resolution,
        "pe_fast_mode": effective_pe_fast_mode,
    })
    _apply_restriction(parameter, restriction)

    payload = {
        "type": config["type"],
        "methodType": config["methodType"],
        "parameter": json.dumps(parameter),
        "saveToDatabase": True,
    }

    if DRY_RUN:
        _progress("[dry-run] 数字人任务 payload（未提交）:")
        _progress(json.dumps(payload, ensure_ascii=False, indent=2))
        return "DRY_RUN_TASK_ID"

    if not estimate_generation_cost(payload):
        message = _creation_failure_message(
            model, _LAST_ESTIMATE_FAILURE_REASON or "费用预估未通过", "数字人任务"
        )
        raise GenerationTaskCreationError(message)

    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        response.raise_for_status()
        result = response.json()

        if result.get("code") == 200 and result.get("data"):
            return result["data"][0]

        reason = result.get("msg", "未知错误")
        message = _creation_failure_message(model, reason, "数字人任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message)

    except requests.exceptions.HTTPError as e:
        message = _creation_failure_message(model, _explain_http_error(e, context="创建数字人任务"), "数字人任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e
    except requests.exceptions.RequestException as e:
        message = _creation_failure_message(model, f"网络错误：{e}", "数字人任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e


def generate_human(prompt="", model=None, image_url=None, video_url=None,
                   audio_url=None, image_path=None, video_path=None,
                   audio_path=None, duration=None, output_resolution=None,
                   pe_fast_mode=None, poll_interval=5, max_wait=1200,
                   submit_only=False):
    """Generate a digital-human video from image/video + reference audio."""
    if image_path and not image_url:
        image_url = upload_file(image_path)
    if video_path and not video_url:
        video_url = upload_file(video_path)
    if audio_path and not audio_url:
        audio_url = upload_file(audio_path)

    display_model = model
    if display_model is None:
        display_model = _get_default_model("human", prompt=prompt)
        if display_model is None:
            print(
                "无法从接口获取可用的数字人模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None
        print(f"[auto] 使用接口返回的第一个可用数字人模型 {display_model}", file=sys.stderr)

    resolved_model = _resolve_model_key(display_model, media_type="human")
    _progress(f"正在生成数字人视频：{prompt or ''}")
    _progress(f"   模型：{resolved_model or display_model}")

    try:
        task_id = create_human_task(
            model=resolved_model or display_model,
            prompt=prompt or "",
            image_url=image_url,
            video_url=video_url,
            audio_url=audio_url,
            duration=duration,
            output_resolution=output_resolution,
            pe_fast_mode=pe_fast_mode,
        )
    except GenerationTaskCreationError as e:
        return {"status": "FAILED", "url": None, "message": str(e), "model": resolved_model or display_model}
    if not task_id:
        return None

    _progress(f"   任务 ID: {task_id}")

    if submit_only:
        return {"status": "SUBMITTED", "task_id": task_id, "url": None, "message": "任务已提交，使用 --poll 轮询结果"}

    _progress(f"   开始轮询任务结果（间隔 {poll_interval}s，最长等待 {max_wait}s）…")
    result = poll_task_status(task_id, interval=poll_interval, max_wait=max_wait)

    if result and result["status"] == "SUCCESS":
        _progress(f"数字人视频生成成功！链接：{result['url']}")
    else:
        print(f"数字人视频生成失败：{result.get('message', '未知错误')}", file=sys.stderr)

    return result


def generate_video(prompt, model=None, ratio=None, resolution=None,
                   duration=None, poll_interval=5, first_image_url=None,
                   last_image_url=None, generate_audio=None, scale_factor=None,
                   generation_type=None, enhance_prompt=None, prompt_extend=None,
                   first_image_path=None, last_image_path=None, audio_url=None,
                   image_url_list=None, video_url_list=None, audio_path=None,
                   image_path_list=None, video_path_list=None, first_clip_path=None,
                   mode=None, keep_original_sound=None, shot_type=None,
                   element_list=None, first_clip_url=None, multi_shot=None,
                   n=None, person_generation=None, resize_mode=None,
                   negative_prompt=None, duration_switch=None,
                   multi_prompt=None, audio_url_list=None, audio_path_list=None,
                   web_search=None, audio_setting=None, max_wait=1200,
                   submit_only=False):
    """Generate a video from a text prompt.

    Args:
        prompt: Text description of the video
        model: Video model key (e.g. S1.5Pro, V3.1FB, V3.1PB, V3.1Fast,
               W2.6t, W2.6i, W2.6r, klingV3Omni, W2.7i, W2.7t, W2.7r)
        ratio: Aspect ratio (e.g. '16:9')
        resolution: Video resolution (e.g. '720p')
        duration: Video duration in seconds
        poll_interval: Polling interval in seconds
        first_image_url: URL of the first frame image (FIRST&LAST mode)
        last_image_url: URL of the last frame image (FIRST&LAST mode)
        generate_audio: Whether to generate audio
        scale_factor: Optional scaleFactor override
        generation_type: Generation type override
        enhance_prompt: Whether to enhance the prompt
        prompt_extend: Whether to extend the prompt
        first_image_path: Local path to first frame image (auto-uploaded)
        last_image_path: Local path to last frame image (auto-uploaded)
        audio_url: URL of audio file (WAN series)
        audio_path: Local path to audio file (auto-uploaded, WAN series)
        image_url_list: List of image URLs for reference (WAN *r / multimodal)
        image_path_list: List of local image paths, uploaded into image_url_list
        video_url_list: List of video URLs for reference (WAN *r)
        video_path_list: List of local video paths, uploaded into video_url_list
        first_clip_path: Local video path, uploaded into first_clip_url

    Returns:
        dict with 'status', 'url', 'message'
    """
    # Upload local files to get URLs if provided
    if first_image_path and not first_image_url:
        first_image_url = upload_file(first_image_path)
    if last_image_path and not last_image_url:
        last_image_url = upload_file(last_image_path)
    if audio_path and not audio_url:
        audio_url = upload_file(audio_path)
    # Multi audio upload for Seedance2.0 series
    if audio_path_list:
        uploaded = []
        for p in audio_path_list:
            u = upload_file(p)
            if u:
                uploaded.append(u)
        if uploaded:
            audio_url_list = (audio_url_list or []) + uploaded
    if image_path_list:
        uploaded = []
        for p in image_path_list:
            u = upload_file(p)
            if u:
                uploaded.append(u)
        if uploaded:
            image_url_list = (image_url_list or []) + uploaded
    if video_path_list:
        uploaded = []
        for p in video_path_list:
            u = upload_file(p)
            if u:
                uploaded.append(u)
        if uploaded:
            video_url_list = (video_url_list or []) + uploaded
    if first_clip_path and not first_clip_url:
        first_clip_url = upload_file(first_clip_path)
    
    display_model = model
    if display_model is None:
        display_model = _get_default_model("video", prompt=prompt)
        if display_model is None:
            print(
                "无法从接口获取可用的视频模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None
        print(f"[auto] 使用接口返回的第一个可用视频模型 {display_model}", file=sys.stderr)

    resolved_model = _resolve_model_key(display_model, media_type="video")
    config = MODEL_CONFIGS.get(resolved_model, {})
    defaults = _build_video_defaults(config["methodType"]) if config else VIDEO_BASE_DEFAULTS
    effective_ratio = ratio or defaults["ratio"]
    effective_resolution = resolution or defaults["resolution"]
    effective_duration = duration or defaults["duration"]

    _progress(f"正在生成视频：{prompt}")
    _progress(f"   模型：{resolved_model or display_model} | 分辨率：{effective_resolution} | 比例：{effective_ratio} | 时长：{effective_duration}s")
    if first_image_url:
        _progress(f"   首帧图片：{first_image_url}")
    if last_image_url:
        _progress(f"   尾帧图片：{last_image_url}")
    if audio_url:
        _progress(f"   音频：{audio_url}")
    if image_url_list:
        _progress(f"   参考图片：{image_url_list}")
    if video_url_list:
        _progress(f"   参考视频：{video_url_list}")

    try:
        task_id = create_video_task(
            prompt, resolved_model or display_model, ratio, resolution, duration,
            first_image_url=first_image_url,
            last_image_url=last_image_url,
            generate_audio=generate_audio,
            scale_factor=scale_factor,
            generation_type=generation_type,
            enhance_prompt=enhance_prompt,
            prompt_extend=prompt_extend,
            audio_url=audio_url,
            image_url_list=image_url_list,
            video_url_list=video_url_list,
            mode=mode,
            keep_original_sound=keep_original_sound,
            shot_type=shot_type,
            element_list=element_list,
            first_clip_url=first_clip_url,
            audio_setting=audio_setting,
            multi_shot=multi_shot,
            n=n,
            person_generation=person_generation,
            resize_mode=resize_mode,
            negative_prompt=negative_prompt,
            duration_switch=duration_switch,
            multi_prompt=multi_prompt,
            audio_url_list=audio_url_list,
            web_search=web_search,
        )
    except GenerationTaskCreationError as e:
        return {"status": "FAILED", "url": None, "message": str(e), "model": resolved_model or display_model}
    if not task_id:
        return None

    _progress(f"   任务 ID: {task_id}")

    if submit_only:
        return {"status": "SUBMITTED", "task_id": task_id, "url": None, "message": "任务已提交，使用 --poll 轮询结果"}

    _progress(f"   开始轮询任务结果（间隔 {poll_interval}s，最长等待 {max_wait}s）…")

    result = poll_task_status(task_id, interval=poll_interval, max_wait=max_wait)

    if result and result["status"] == "SUCCESS":
        _progress(f"视频生成成功！链接：{result['url']}")
    else:
        print(f"视频生成失败：{result.get('message', '未知错误')}", file=sys.stderr)

    return result


def create_generation_task(prompt, quality=None, size=None, model=None,
                           reference_image_url=None, web_search=None,
                           image_search=None, ratiocination=None, n=None):
    """Create an image generation task.

    Args:
        prompt: Text description of the image
        quality: Image quality (2K/4K)
        size: Image dimensions. S5.0L / W2.7 / W2.7Pro use e.g. '2048x2048';
              N2 / 3.1Nano2-Evo / Nano2-Beta-Evo use e.g. '1:1';
              Image2 / Image2-Beta-Evo use 'auto' or a ratio string (e.g. '1:1').
        model: Image model key (N2, S5.0L, W2.7, W2.7Pro, 3.1Nano2-Evo,
               Nano2-Beta-Evo, Image2, Image2-Beta-Evo)
        reference_image_url: Optional reference image URL for image-to-image generation
        web_search: Toggle webSearch (S5.0L / 3.1Nano2-Evo)
        image_search: Toggle imageSearch (3.1Nano2-Evo only)
        ratiocination: Render-quality preset for Image2 (low/medium/high)
        n: Image count for Image2 (1-10)
    """
    url = f"{BASE_URL}/AiArtistRecord"

    # API-driven default: when caller omits `model`, pick the first active
    # non-'auto' image model from consumeSource/list (no hardcoded fallback).
    if model is None:
        model = _get_default_model("image", prompt=prompt)
        if model is None:
            print(
                "无法从接口获取可用的图片模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None
        print(f"[auto] 使用接口返回的第一个可用图片模型 {model}", file=sys.stderr)

    # Accept friendly key or methodType (e.g. '3.1Nano2-Evo' or '8')
    resolved = _resolve_model_key(model, media_type="image")
    if resolved is None:
        print(f"不支持的模型：{model}，可用模型：{list(MODEL_CONFIGS.keys())}", file=sys.stderr)
        return None
    model = resolved
    config = MODEL_CONFIGS[model]
    method_type = str(config["methodType"])

    # Image generation always requires a non-empty prompt (frontend: required rule)
    if not prompt or not str(prompt).strip():
        print(f"模型 {model} 必须提供非空的生成提示词 (prompt)", file=sys.stderr)
        return None

    # Runtime availability check: consumeSource/list 可能随时将模型切成 hiddenState=1.
    # Skip in dry-run so payload debugging works without API credentials/network.
    if not DRY_RUN and not check_model_available(model):
        return None

    # Preserve the user's image prompt verbatim; reject instead of truncating.
    image_restriction = IMAGE_RESTRICTIONS_BY_MT.get(method_type, {})
    prompt_limit = image_restriction.get("textLength")
    if prompt_limit and len(str(prompt)) > prompt_limit:
        raise GenerationTaskCreationError(
            f"{model} 提示词长度 {len(str(prompt))} 超过限制 {prompt_limit}，未提交生成任务"
        )

    # Defaults follow the frontend pattern: BASE_DEFAULTS + handleMethodTypeChange.
    # No model-specific default_quality / default_size overrides.
    base_params = _build_image_defaults(method_type)
    base_quality = base_params["quality"]
    base_size = base_params["size"]

    if quality is None:
        quality = base_quality
    if size is None:
        size = base_size

    # Validate quality against methodType whitelist (matchImageQualityOptions)
    quality = _coerce_value(
        quality, IMAGE_QUALITIES_BY_MT.get(method_type, IMAGE_QUALITIES_DEFAULT),
        base_quality, "quality", model,
    )

    # Normalize model-specific size syntax before building the payload. Image2
    # accepts auto/ratios/WxH; legacy W*H is converted to WxH and validated.
    size = _normalize_image_size(size, method_type, quality, model)
    is_pixel_size = bool(_IMAGE_PIXEL_SIZE_RE.fullmatch(str(size)))

    # Pixel-size models (mt 0,4 → 'x'; mt 6,7 → '*'): if caller passed a ratio
    # like '1:1', convert to a pixel string matching frontend buildImageParams.
    pixel_sep = _IMAGE_PIXEL_SEP_BY_MT.get(str(method_type))
    if pixel_sep and not is_pixel_size:
        size = _image_size_to_pixels(quality, size, pixel_sep)
        size = _normalize_image_size(size, method_type, quality, model)

    # Build image array - support reference image for image-to-image
    image_array = []
    if reference_image_url:
        image_array = [reference_image_url]

    # Start from frontend-equivalent base defaults
    parameter = base_params
    parameter.update({
        "methodType": method_type,
        "prompt": prompt,
        "image": image_array,
        "quality": quality,
        "size": size,
        "targetMaxSize": 10,
        "targetMaxLength": 6000,
    })
    if web_search is not None:
        parameter["webSearch"] = bool(web_search)
    for key, value in config.get("extra_params", {}).items():
        if key not in IMAGE_BASE_DEFAULTS:
            parameter[key] = value

    # ----- Image2 / Nano2 explicit overrides from caller -----
    if image_search is not None:
        parameter["imageSearch"] = bool(image_search)
    if ratiocination is not None:
        ratiocination = _coerce_value(
            ratiocination, IMAGE_RATIOCINATION_OPTIONS,
            "medium", "ratiocination", model,
        )
        parameter["ratiocination"] = ratiocination
    if n is not None:
        try:
            n_int = int(n)
        except (TypeError, ValueError):
            print(f"{model} 参数 n={n!r} 非法，已忽略", file=sys.stderr)
            n_int = None
        if n_int is not None:
            if n_int < 1 or n_int > 10:
                print(
                    f"{model} n={n_int} 超出范围 [1,10]，已截断到合法区间",
                    file=sys.stderr,
                )
                n_int = max(1, min(10, n_int))
            if method_type in IMAGE_FIELD_SUPPORT_BY_MT.get("n", set()):
                parameter["n"] = n_int

    # Overwrite targetMaxSize / targetMinLength / targetMaxLength per methodType
    _apply_restriction(parameter, image_restriction)

    # Strip image fields this methodType does not accept (mirrors frontend rules)
    _filter_by_whitelist(parameter, method_type, IMAGE_FIELD_SUPPORT_BY_MT)

    payload = {
        "type": config["type"],
        "methodType": config["methodType"],
        "parameter": json.dumps(parameter),
        "saveToDatabase": True,
    }

    if DRY_RUN:
        _progress("[dry-run] 图片任务 payload（未提交）:")
        _progress(json.dumps(payload, ensure_ascii=False, indent=2))
        return "DRY_RUN_TASK_ID"

    if not estimate_generation_cost(payload):
        message = _creation_failure_message(
            model, _LAST_ESTIMATE_FAILURE_REASON or "费用预估未通过", "图片任务"
        )
        raise GenerationTaskCreationError(message)

    try:
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        response.raise_for_status()
        result = response.json()
        
        if result.get("code") == 200 and result.get("data"):
            return result["data"][0]
        else:
            reason = result.get('msg', '未知错误')
            message = _creation_failure_message(model, reason, "图片任务")
            print(message, file=sys.stderr)
            raise GenerationTaskCreationError(message)

    except requests.exceptions.HTTPError as e:
        message = _creation_failure_message(model, _explain_http_error(e, context="创建图片任务"), "图片任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e
    except requests.exceptions.RequestException as e:
        message = _creation_failure_message(model, f"网络错误：{e}", "图片任务")
        print(message, file=sys.stderr)
        raise GenerationTaskCreationError(message) from e


def poll_task_status(task_id, interval=5, max_wait=1200):
    """Poll the task status until completion or failure."""
    if task_id == "DRY_RUN_TASK_ID":
        return {"status": "SUCCESS", "url": None,
                "message": "dry-run 模式，未提交真实任务"}
    url = f"{BASE_URL}/AiArtistImage/getInfoByArtistId/{task_id}"
    
    elapsed = 0
    last_status = None
    
    while elapsed < max_wait:
        try:
            response = requests.get(url, headers=get_headers(), timeout=30)
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 200:
                time.sleep(interval)
                elapsed += interval
                continue
            
            data = result.get("data", {})
            status = data.get("status", "")
            
            # Only print status when it changes
            if status != last_status:
                _progress(f"{status} - {data.get('message', '')}")
                last_status = status
            
            if status == "SUCCESS":
                urls = data.get("urls") or []
                single_url = data.get("url")
                return {
                    "status": "SUCCESS",
                    "url": urls[0] if urls else single_url,
                    "urls": urls if urls else ([single_url] if single_url else []),
                    "message": data.get("message", "生成成功")
                }
            elif status == "FAILED":
                return {
                    "status": "FAILED",
                    "url": None,
                    "message": data.get("message", "生成失败")
                }
            else:
                time.sleep(interval)
                elapsed += interval
                
        except requests.exceptions.RequestException as e:
            print(f"查询状态出错：{e}", file=sys.stderr)
            time.sleep(interval)
            elapsed += interval
    
    return {
        "status": "TIMEOUT",
        "url": None,
        "message": f"超时（{max_wait}秒）"
    }


def generate_image(prompt, quality=None, size=None, poll_interval=5,
                   download=False, output_dir=None, model=None,
                   reference_image_path=None, reference_image_url=None,
                   web_search=None, image_search=None, ratiocination=None,
                   n=None, max_wait=1200, submit_only=False):
    """
    Main function to generate an image from a prompt.
    
    Args:
        prompt: Text description of the image
        quality: Image quality (2K/4K)
        size: Image dimensions. Defaults to model's default size if not specified.
              S5.0L / W2.7 / W2.7Pro: e.g. '2048x2048'
              N2 / 3.1Nano2-Evo / Nano2-Beta-Evo: e.g. '1:1'
        poll_interval: Polling interval in seconds
        download: Whether to download the image
        output_dir: Directory to save the image (default: workspace/images)
        model: Image model key (N2, S5.0L, W2.7, W2.7Pro, 3.1Nano2-Evo, Nano2-Beta-Evo)
        reference_image_path: Local path to reference image (auto-uploaded)
        reference_image_url: URL of reference image (if already uploaded)
    
    Returns:
        dict with generation result including 'url', 'local_path', 'data_uri' if successful
    """
    display_model = model
    if display_model is None:
        display_model = _get_default_model("image", prompt=prompt)
        if display_model is None:
            print(
                "无法从接口获取可用的图片模型，请显式通过 model 参数指定，或检查服务端状态。",
                file=sys.stderr,
            )
            return None
        print(f"[auto] 使用接口返回的第一个可用图片模型 {display_model}", file=sys.stderr)

    resolved_model = _resolve_model_key(display_model, media_type="image")
    config = MODEL_CONFIGS.get(resolved_model, {})
    defaults = _build_image_defaults(config["methodType"]) if config else IMAGE_BASE_DEFAULTS
    effective_quality = quality or defaults["quality"]
    effective_size = size or defaults["size"]
    if config:
        try:
            effective_size = _normalize_image_size(
                effective_size,
                config["methodType"],
                effective_quality,
                resolved_model or display_model,
            )
        except GenerationTaskCreationError as e:
            return {
                "status": "FAILED",
                "url": None,
                "message": str(e),
                "model": resolved_model or display_model,
            }
        is_pixel_size = bool(_IMAGE_PIXEL_SIZE_RE.fullmatch(str(effective_size)))
        pixel_sep = _IMAGE_PIXEL_SEP_BY_MT.get(str(config["methodType"]))
        if pixel_sep and not is_pixel_size:
            effective_size = _image_size_to_pixels(effective_quality, effective_size, pixel_sep)
            effective_size = _normalize_image_size(
                effective_size,
                config["methodType"],
                effective_quality,
                resolved_model or display_model,
            )

    # Upload reference image if local path provided
    if reference_image_path:
        reference_image_url = upload_file(reference_image_path)
        if not reference_image_url:
            return {
                "status": "FAILED",
                "url": None,
                "message": "参考图上传失败，未提交生成任务",
                "model": resolved_model or display_model,
            }

    _progress(f"正在生成：{prompt}")
    _progress(f"   模型：{resolved_model or display_model} | 质量：{effective_quality} | 尺寸：{effective_size}")
    if reference_image_url:
        _progress(f"   参考图：{reference_image_url}")

    # Step 1: Create task
    try:
        task_id = create_generation_task(
            prompt, quality, size, resolved_model or display_model, reference_image_url,
            web_search=web_search,
            image_search=image_search,
            ratiocination=ratiocination,
            n=n,
        )
    except GenerationTaskCreationError as e:
        return {"status": "FAILED", "url": None, "message": str(e), "model": resolved_model or display_model}
    if not task_id:
        return None

    _progress(f"   任务 ID: {task_id}")

    if submit_only:
        return {"status": "SUBMITTED", "task_id": task_id, "url": None, "message": "任务已提交，使用 --poll 轮询结果"}

    _progress(f"   开始轮询任务结果（间隔 {poll_interval}s，最长等待 {max_wait}s）…")

    # Step 2: Poll until complete
    result = poll_task_status(task_id, interval=poll_interval, max_wait=max_wait)

    if result and result["status"] == "SUCCESS":
        _progress(f"生成成功！链接：{result['url']}")
        
        # Download image if requested
        if download and result.get("url"):
            if not output_dir:
                output_dir = os.path.join(os.path.expanduser("~"), ".openclaw", "workspace", "images")
            
            # Generate filename from prompt
            safe_prompt = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in prompt)
            safe_prompt = safe_prompt[:50].strip().replace(' ', '_')
            filename = f"{safe_prompt}_{int(time.time())}.png"
            output_path = os.path.join(output_dir, filename)
            
            image_data = download_image(result["url"], output_path)
            if image_data:
                result["local_path"] = output_path
                result["data_uri"] = image_to_data_uri(image_data)
                result["image_data"] = image_data  # Raw bytes for programmatic use
        
        return result
    else:
        print(f"生成失败：{result.get('message', '未知错误')}", file=sys.stderr)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI 图片/视频生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", nargs="?", default=None,
                        help="生成提示词（使用 --list-models 时可省略）")
    parser.add_argument("--list-models", action="store_true",
                        help="列出当前服务端激活的可用模型 (hiddenState=0) 后退出")
    parser.add_argument("--recommend-model", action="store_true",
                        help="仅根据 prompt 和服务端模型描述推荐模型，不创建生成任务")
    parser.add_argument("--model", default=None,
                        metavar="MODEL",
                        help="生成模型。推荐传接口 sourceValue/methodType（如 19）；旧友好别名仅用于兼容。"
                             "未指定时根据 prompt 自动推断媒介，并使用接口返回的第一个可用模型。"
                             "查看可用模型：--list-models")
    parser.add_argument("--media-type", choices=["image", "video", "human"], default=None,
                        help="显式指定媒介类型，用于 disambiguate 数字 methodType（如 human 的 methodType=1）")
    # 图片专属参数
    parser.add_argument("--quality", default=None, help="[图片] 图片质量，不传则按 methodType 默认值")
    parser.add_argument("--size", default=None, help="[图片] 图片尺寸，不传则使用模型默认值")
    parser.add_argument("--download", action="store_true", help="[图片] 下载图片到本地")
    parser.add_argument("--output-dir", help="[图片] 图片保存目录")
    parser.add_argument("--markdown-output", action="store_true", help="以 Markdown 格式输出图片链接")
    parser.add_argument("--reference-image", default=None, help="[图片] 参考图本地路径，自动上传后作为 image-to-image 参考")
    parser.add_argument("--reference-image-url", default=None, help="[图片] 已上传的参考图 URL")
    parser.add_argument("--web-search", dest="web_search", action="store_true", default=None,
                        help="[图片] 启用联网搜索 (仅 methodType 4/8)")
    parser.add_argument("--no-web-search", dest="web_search", action="store_false",
                        help="[图片] 关闭联网搜索")
    parser.add_argument("--image-search", dest="image_search", action="store_true", default=None,
                        help="[图片] 启用图像搜索 (仅 methodType 8)")
    parser.add_argument("--no-image-search", dest="image_search", action="store_false",
                        help="[图片] 关闭图像搜索")
    parser.add_argument("--ratiocination", default=None,
                        choices=["low", "medium", "high"],
                        help="[图片] 渲染质量预设 (仅 methodType 10)：low=最快 / medium=平衡 / high=质量")
    # 视频专属参数
    parser.add_argument("--ratio", default=None, help="[视频] 画面比例，如 16:9、9:16、1:1，不传则按 methodType 默认值")
    parser.add_argument("--resolution", default=None, help="[视频] 分辨率，如 720p、1080p，不传则按 methodType 默认值")
    parser.add_argument("--duration", type=int, default=None, help="[视频] 视频时长 (秒)，不传则按 methodType 默认值")
    # 视频通用参数（首尾帧 / 音频 / 生成模式）
    parser.add_argument("--first-image-url", default=None, help="[视频] 首帧图片 URL（FIRST&LAST 模式）")
    parser.add_argument("--last-image-url", default=None, help="[视频] 尾帧图片 URL（FIRST&LAST 模式）")
    parser.add_argument("--first-image", default=None, help="[视频] 首帧图片本地路径，自动上传")
    parser.add_argument("--last-image", default=None, help="[视频] 尾帧图片本地路径，自动上传")
    parser.add_argument("--generate-audio", action="store_true", default=None, help="[视频] 生成音频")
    parser.add_argument("--no-audio", action="store_true", help="[视频] 不生成音频")
    parser.add_argument("--scale-factor", type=float, default=None, help="[视频] 可选 scaleFactor 覆盖值")
    parser.add_argument("--generation-type", default=None, help="[视频] 生成类型，如 FIRST&LAST、TEXT、REFERENCE、CONTINUATION、EDIT、FEATURE")
    parser.add_argument("--negative-prompt", default=None, help="[视频] 反向提示词 (methodType 3/4/5/6/7/8/9/14/15/16 等)")
    parser.add_argument("--enhance-prompt", action="store_true", default=None, help="[视频] 翻译成英文 (methodType 3/4/5/6 等)")
    parser.add_argument("--prompt-extend", action="store_true", default=None, help="[视频] 智能改写 (methodType 7/8/9/14/15/16 等)")
    parser.add_argument("--shot-type", default=None, help="[视频] 镜头模式：single/multi/customize (methodType 7/10 等)")
    parser.add_argument("--mode", default=None, help="[视频] 生成模式：std/pro (仅 methodType 10)")
    parser.add_argument("--keep-original-sound", default=None, help="[视频] yes/no (仅 methodType 10)")
    parser.add_argument("--multi-shot", action="store_true", default=None, help="[视频] 多镜头模式 (仅 methodType 10)")
    parser.add_argument("--n", type=int, default=None,
                        help="[视频] 生成数量 1-4 (methodType 5) | [图片] 生成数量 1-10 (methodType 10)")
    parser.add_argument("--person-generation", default=None, help="[视频] allow_adult/dont_allow (methodType 5/6)")
    parser.add_argument("--resize-mode", default=None, help="[视频] pad/crop (methodType 5/6)")
    parser.add_argument("--duration-switch", default=None, help="[视频] 1=手选秒数, 2=智能时长 (methodType 2/17/18/20/21/22)")
    parser.add_argument("--audio-url", default=None,
                        help="[video] single reference audio URL; submit as audioUrl")
    parser.add_argument("--audio", default=None,
                        help="[video] local reference audio path; upload and write to audioUrl")
    parser.add_argument("--audio-url-list", default=None,
                        help="[视频] 多音频参考 URL，逗号分隔 (methodType 17/18/20/21/22)")
    parser.add_argument("--audio-path-list", default=None,
                        help="[视频] 多音频本地路径，逗号分隔，自动上传 (methodType 17/18/20/21/22)")
    parser.add_argument("--image-url-list", default=None,
                        help="[视频] 多参考图片 URL，逗号分隔，直接提交为 imageUrlList")
    parser.add_argument("--image-path-list", default=None,
                        help="[video] local image paths, comma-separated; upload and append to imageUrlList")
    parser.add_argument("--video-url-list", default=None,
                        help="[视频] 多参考视频 URL，逗号分隔，直接提交为 videoUrlList")
    parser.add_argument("--video-path-list", default=None,
                        help="[video] local video paths, comma-separated; upload and append to videoUrlList")
    parser.add_argument("--first-clip-url", default=None,
                        help="[视频] 续写/编辑/参考视频 URL (methodType 10/14/19 等)")
    parser.add_argument("--first-clip", default=None,
                        help="[video] local first clip path; upload and write to firstClipUrl")
    parser.add_argument("--audio-setting", default=None, choices=["auto", "origin"],
                        help="[视频] 声音控制：auto=由模型控制 / origin=保留原声 (仅 methodType 19 EDIT)")
    # 数字人专属参数
    parser.add_argument("--human-image-url", default=None, help="[数字人] 人像图片 URL (methodType 0)")
    parser.add_argument("--human-video-url", default=None, help="[数字人] 人像视频 URL (methodType 1)")
    parser.add_argument("--human-audio-url", default=None, help="[数字人] 参考音频 URL")
    parser.add_argument("--human-image", default=None, help="[数字人] 人像图片本地路径，自动上传")
    parser.add_argument("--human-video", default=None, help="[数字人] 人像视频本地路径，自动上传")
    parser.add_argument("--human-audio", default=None, help="[数字人] 参考音频本地路径，自动上传")
    parser.add_argument("--human-duration", type=float, default=None,
                        help="[数字人] 参考音频时长，允许小数秒")
    parser.add_argument("--output-resolution", default=None, choices=["720", "1080"],
                        help="[数字人] 渲染质量，前端值为 720 或 1080")
    # 通用参数
    parser.add_argument("--interval", type=int, default=5, help="轮询间隔秒数")
    parser.add_argument("--max-wait", type=int, default=1200, help="任务轮询最长等待秒数 (默认 1200)")
    parser.add_argument("--dry-run", action="store_true",
                        help="仅构建并打印最终 payload，不实际调用 API（用于调试）")
    parser.add_argument("--json-output", action="store_true",
                        help="以单行 JSON 向 stdout 输出最终结果 {status,url,message}，便于外部编排解析")
    parser.add_argument("--submit-only", action="store_true",
                        help="只提交任务，立即将 task_id 输出到 stdout，不轮询结果（配合 --poll 使用）")
    parser.add_argument("--poll", default=None, metavar="TASK_ID",
                        help="只轮询已存在的任务，不重新提交（用于 --submit-only 提交后的独立轮询）")

    args = parser.parse_args()

    # --poll short-circuit: only poll an existing task, no submission
    if args.poll:
        ensure_api_key_for_network()
        result = poll_task_status(args.poll, interval=args.interval, max_wait=args.max_wait)
        if args.json_output:
            import json
            print(json.dumps(result, ensure_ascii=False))
        elif result.get("status") == "SUCCESS":
            print(result.get("url", ""))
        else:
            print(result.get("message", ""), file=sys.stderr)
        sys.exit(0 if result.get("status") == "SUCCESS" else 1)

    # --list-models short-circuit (also runs drift detection)
    if args.list_models:
        ensure_api_key_for_network()
        _validate_local_against_api()
        print_active_models()
        sys.exit(0)

    if not args.prompt and args.media_type != "human":
        parser.error("prompt 为必填参数（查看可用模型请加 --list-models）")

    if args.recommend_model:
        ensure_api_key_for_network()
        recommendation = recommend_model_for_prompt(args.prompt)
        if not recommendation:
            message = "未从当前服务端可用模型描述中匹配到合适模型"
            if args.json_output:
                print(json.dumps({"status": "NOT_FOUND", "message": message}, ensure_ascii=False), flush=True)
            else:
                print(message, file=sys.stderr)
            sys.exit(1)
        if args.json_output:
            print(json.dumps({"status": "SUCCESS", "model": recommendation}, ensure_ascii=False), flush=True)
        else:
            print(
                f"{recommendation.get('sourceName')} "
                f"[sourceValue={recommendation.get('sourceValue')}, key={recommendation.get('key')}]"
            )
            if recommendation.get("description"):
                print(recommendation["description"])
        sys.exit(0)

    # Toggle dry-run globally so all downstream task creators honor it
    if args.dry_run:
        DRY_RUN = True

    # Auto-select default model when the user did NOT pass --model explicitly.
    # Mirrors frontend: pick the first active (hiddenState=0, sourceValue!='auto')
    # model returned by consumeSource/list for the inferred media_type. No
    # hardcoded fallback — if the API is unreachable or returns nothing, abort
    # with a clear error rather than silently submitting to a stale model.
    if args.model is None:
        ensure_api_key_for_network()
        inferred = args.media_type or _infer_media_type(args.prompt)
        args.model = _get_default_model(inferred, prompt=args.prompt)
        if args.model is None:
            parser.error(
                f"无法从接口获取可用的{inferred}模型，请运行 --list-models 检查服务端状态，"
                f"或显式通过 --model 指定模型"
            )
        print(
            f"[auto] 根据提示词推断媒介 → {inferred}，使用接口返回的第一个可用模型 {args.model}",
            file=sys.stderr,
        )
    else:
        # Resolve friendly-name | methodType to the canonical friendly key.
        # Numeric methodTypes are ambiguous across image/video, so infer the
        # requested media from the prompt before resolving.
        inferred = args.media_type or _infer_media_type(args.prompt)
        resolved = _resolve_model_key(args.model, media_type=inferred)
        if resolved is None:
            parser.error(f"未知模型：{args.model}（可运行 --list-models 查看可用模型）")
        if resolved != args.model:
            print(f"[resolve] --model {args.model} → {resolved} "
                  f"(methodType={MODEL_CONFIGS[resolved]['methodType']})",
                  file=sys.stderr)
        args.model = resolved

    media_type = MODEL_CONFIGS[args.model]["media_type"]

    if not args.dry_run:
        ensure_api_key_for_network()

    if media_type == "human":
        result = generate_human(
            prompt=args.prompt or "",
            model=args.model,
            image_url=args.human_image_url,
            video_url=args.human_video_url,
            audio_url=args.human_audio_url,
            image_path=args.human_image,
            video_path=args.human_video,
            audio_path=args.human_audio,
            duration=args.human_duration if args.human_duration is not None else args.duration,
            output_resolution=args.output_resolution,
            poll_interval=args.interval,
            max_wait=args.max_wait,
            submit_only=args.submit_only,
        )
        if FEISHU_WEBHOOK_URL and result and result.get("status") != "SUBMITTED":
            send_feishu_message(args.prompt or "数字人视频", result, media_type="video")
        _emit_cli_result(result, args, markdown_label=args.prompt or "数字人视频")
        sys.exit(0 if (result and result.get("status") in ("SUCCESS", "SUBMITTED")) else 1)

    if media_type == "video":
        # Resolve audio flag
        gen_audio = None
        if args.no_audio:
            gen_audio = False
        elif args.generate_audio:
            gen_audio = True

        result = generate_video(
            prompt=args.prompt,
            model=args.model,
            ratio=args.ratio,
            resolution=args.resolution,
            duration=args.duration,
            poll_interval=args.interval,
            first_image_url=args.first_image_url,
            last_image_url=args.last_image_url,
            first_image_path=args.first_image,
            last_image_path=args.last_image,
            generate_audio=gen_audio,
            scale_factor=args.scale_factor,
            generation_type=args.generation_type,
            negative_prompt=args.negative_prompt,
            enhance_prompt=args.enhance_prompt,
            prompt_extend=args.prompt_extend,
            shot_type=args.shot_type,
            mode=args.mode,
            keep_original_sound=args.keep_original_sound,
            multi_shot=args.multi_shot,
            n=args.n,
            person_generation=args.person_generation,
            resize_mode=args.resize_mode,
            duration_switch=args.duration_switch,
            audio_url=args.audio_url,
            audio_path=args.audio,
            audio_url_list=[u.strip() for u in args.audio_url_list.split(",") if u.strip()] if args.audio_url_list else None,
            audio_path_list=[p.strip() for p in args.audio_path_list.split(",") if p.strip()] if args.audio_path_list else None,
            image_url_list=[u.strip() for u in args.image_url_list.split(",") if u.strip()] if args.image_url_list else None,
            image_path_list=[p.strip() for p in args.image_path_list.split(",") if p.strip()] if args.image_path_list else None,
            video_url_list=[u.strip() for u in args.video_url_list.split(",") if u.strip()] if args.video_url_list else None,
            video_path_list=[p.strip() for p in args.video_path_list.split(",") if p.strip()] if args.video_path_list else None,
            web_search=args.web_search,
            first_clip_url=args.first_clip_url,
            first_clip_path=args.first_clip,
            audio_setting=args.audio_setting,
            max_wait=args.max_wait,
            submit_only=args.submit_only,
        )
        # Send result to Feishu if webhook is configured
        if FEISHU_WEBHOOK_URL and result and result.get("status") != "SUBMITTED":
            send_feishu_message(args.prompt, result, media_type="video")
        _emit_cli_result(result, args, markdown_label=args.prompt)
        sys.exit(0 if (result and result.get("status") in ("SUCCESS", "SUBMITTED")) else 1)
    else:
        result = generate_image(
            prompt=args.prompt,
            quality=args.quality,
            size=args.size,
            poll_interval=args.interval,
            download=args.download,
            output_dir=args.output_dir,
            model=args.model,
            reference_image_path=args.reference_image,
            reference_image_url=args.reference_image_url,
            web_search=args.web_search,
            image_search=args.image_search,
            ratiocination=args.ratiocination,
            n=args.n,
            max_wait=args.max_wait,
            submit_only=args.submit_only,
        )

        # Send result to Feishu if webhook is configured
        if FEISHU_WEBHOOK_URL and result and result.get("status") != "SUBMITTED":
            send_feishu_message(args.prompt, result, media_type="image")
        _emit_cli_result(result, args, markdown_label=args.prompt)
        sys.exit(0 if (result and result.get("status") in ("SUCCESS", "SUBMITTED")) else 1)
