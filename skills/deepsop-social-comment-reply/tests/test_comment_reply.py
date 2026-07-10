import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "comment_reply.py"


def load_module():
    spec = importlib.util.spec_from_file_location("comment_reply", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_search_url_encodes_douyin_keyword():
    module = load_module()

    url = module.build_search_url("douyin", "AI Agent 自动化")

    assert url == "https://www.douyin.com/search/AI%20Agent%20%E8%87%AA%E5%8A%A8%E5%8C%96"


def test_validate_plan_rejects_send_without_confirm_flag():
    module = load_module()

    errors = module.validate_plan(
        platform="douyin",
        keyword="AI Agent",
        reply_text="看完很有启发，流程拆得很清楚。",
        mode="confirm-send",
        confirm_send=False,
        max_targets=1,
    )

    assert "confirm-send requires --confirm-send" in errors


def test_validate_plan_rejects_auto_send_mode():
    module = load_module()

    errors = module.validate_plan(
        platform="douyin",
        keyword="AI Agent",
        reply_text="看完很有启发，流程拆得很清楚。",
        mode="auto-send",
        confirm_send=True,
        max_targets=1,
    )

    assert "auto-send mode is not supported" in errors


def test_clamp_max_targets_keeps_safe_default():
    module = load_module()

    assert module.clamp_max_targets(99) == 3
    assert module.clamp_max_targets(0) == 1


def test_execution_log_counts_statuses():
    module = load_module()
    records = [
        {"status": "drafted"},
        {"status": "submitted"},
        {"status": "skipped", "reason": "comment box not found"},
    ]

    log = module.build_execution_log("douyin", "AI Agent", "draft-only", records)

    assert log["attemptedTargets"] == 3
    assert log["draftedReplies"] == 1
    assert log["submittedReplies"] == 1
    assert log["skipped"] == [{"reason": "comment box not found"}]


def test_parse_args_supports_pause_on_risk():
    module = load_module()

    args = module.parse_args(
        [
            "--platform",
            "douyin",
            "--keyword",
            "AI",
            "--reply-text",
            "AI 很强大。",
            "--pause-on-risk",
            "--pause-on-risk-seconds",
            "30",
        ]
    )

    assert args.pause_on_risk is True
    assert args.pause_on_risk_seconds == 30


def test_generic_login_text_is_not_risky():
    module = load_module()

    assert module.RISK_PATTERN.search("登录 注册 首页 推荐") is None
    assert module.RISK_PATTERN.search("请完成安全验证") is not None
