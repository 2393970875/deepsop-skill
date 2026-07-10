#!/usr/bin/env python3
"""Browser automation helper for guarded social comment replies.

This script is intentionally conservative. It can search/open targets and fill
comment boxes, but sending requires explicit confirmation flags.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote


SUPPORTED_PLATFORMS = {"douyin", "wechat-channels"}
SUPPORTED_MODES = {"draft-only", "confirm-send", "manual-review-batch"}
MAX_SAFE_TARGETS = 3
RISK_PATTERN = re.compile(
    r"验证码|短信验证|实名|风险|异常|扫码验证|安全验证|captcha|verify",
    re.IGNORECASE,
)


def build_search_url(platform: str, keyword: str) -> str:
    encoded = quote(keyword.strip())
    if platform == "douyin":
        return f"https://www.douyin.com/search/{encoded}"
    if platform == "wechat-channels":
        return f"https://channels.weixin.qq.com/platform/search?query={encoded}"
    raise ValueError(f"Unsupported platform: {platform}")


def clamp_max_targets(value: int) -> int:
    if value < 1:
        return 1
    return min(value, MAX_SAFE_TARGETS)


def read_reply_text(reply_text: str | None, reply_file: str | None) -> str:
    if reply_text:
        return reply_text.strip()
    if reply_file:
        return Path(reply_file).read_text(encoding="utf-8").strip()
    return ""


def validate_plan(
    *,
    platform: str,
    keyword: str,
    reply_text: str,
    mode: str,
    confirm_send: bool,
    max_targets: int,
) -> list[str]:
    errors: list[str] = []
    if platform not in SUPPORTED_PLATFORMS:
        errors.append(f"unsupported platform: {platform}")
    if not keyword.strip():
        errors.append("keyword is required")
    if not reply_text.strip():
        errors.append("reply text is required; draft it first, then pass --reply-text or --reply-file")
    if mode == "auto-send":
        errors.append("auto-send mode is not supported")
    elif mode not in SUPPORTED_MODES:
        errors.append(f"unsupported mode: {mode}")
    if mode in {"confirm-send", "manual-review-batch"} and not confirm_send:
        errors.append("confirm-send requires --confirm-send")
    if max_targets > MAX_SAFE_TARGETS:
        errors.append(f"max targets is capped at {MAX_SAFE_TARGETS}; requested value will be reduced")
    return errors


def build_execution_log(platform: str, keyword: str, mode: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "platform": platform,
        "keyword": keyword,
        "mode": mode,
        "attemptedTargets": len(records),
        "draftedReplies": sum(1 for item in records if item.get("status") == "drafted"),
        "submittedReplies": sum(1 for item in records if item.get("status") == "submitted"),
        "skipped": [
            {"target": item.get("target"), "reason": item.get("reason", "skipped")}
            if item.get("target")
            else {"reason": item.get("reason", "skipped")}
            for item in records
            if item.get("status") == "skipped"
        ],
        "records": records,
    }


def fail_if_risky(page: Any) -> None:
    body_text = safe_inner_text(page.locator("body"), limit=2000)
    if RISK_PATTERN.search(body_text):
        raise RuntimeError("page may require login, verification, or risk handling; stop for manual review")


def check_or_pause_on_risk(page: Any, pause_on_risk: bool, pause_seconds: int = 0) -> None:
    try:
        fail_if_risky(page)
    except RuntimeError:
        if not pause_on_risk:
            raise
        if pause_seconds > 0:
            print(f"Handle login/verification in the browser within {pause_seconds} seconds...")
            time.sleep(pause_seconds)
        else:
            input("Handle login/verification in the browser, then press Enter to continue...")
        fail_if_risky(page)


def safe_inner_text(locator: Any, *, limit: int = 500) -> str:
    try:
        if locator.count() == 0:
            return ""
        text = locator.first.inner_text(timeout=2000)
        return " ".join(text.split())[:limit]
    except Exception:
        return ""


def collect_douyin_targets(page: Any, max_targets: int) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    locators = [
        page.locator("a[href*='/video/']"),
        page.locator("a[href*='douyin.com'][href*='note']"),
    ]
    for locator in locators:
        try:
            count = min(locator.count(), 30)
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                href = item.get_attribute("href", timeout=1000)
                if not href or href in seen:
                    continue
                seen.add(href)
                text = safe_inner_text(item, limit=160)
                targets.append({"url": href, "title": text or href, "reason": "keyword search result"})
                if len(targets) >= max_targets:
                    return targets
            except Exception:
                continue
    return targets


def collect_current_page_target(page: Any) -> dict[str, str]:
    title = ""
    try:
        title = page.title()
    except Exception:
        pass
    return {
        "url": page.url,
        "title": title or safe_inner_text(page.locator("body"), limit=120) or page.url,
        "reason": "current page or provided start URL",
    }


def collect_context(page: Any) -> dict[str, str]:
    return {
        "title": collect_current_page_target(page)["title"],
        "visibleText": safe_inner_text(page.locator("body"), limit=600),
        "selectedComment": "",
    }


def find_comment_box(page: Any) -> Any | None:
    candidates = [
        page.get_by_placeholder(re.compile("评论|回复|说点什么|留下|comment|reply", re.IGNORECASE)),
        page.locator("textarea"),
        page.locator("input[placeholder*='评论']"),
        page.locator("[contenteditable='true']"),
        page.locator("[role='textbox']"),
    ]
    for locator in candidates:
        try:
            count = min(locator.count(), 5)
        except Exception:
            continue
        for index in range(count):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=1000) and item.is_enabled(timeout=1000):
                    return item
            except Exception:
                continue
    return None


def fill_comment_box(page: Any, reply_text: str) -> None:
    box = find_comment_box(page)
    if box is None:
        raise RuntimeError("comment box not found")
    box.click(timeout=3000)
    try:
        box.fill(reply_text, timeout=3000)
    except Exception:
        page.keyboard.insert_text(reply_text)


def click_send_button(page: Any) -> None:
    candidates = [
        page.locator("button").filter(has_text=re.compile("发送|评论|回复|send|comment|reply", re.IGNORECASE)),
        page.locator("[role='button']").filter(has_text=re.compile("发送|评论|回复|send|comment|reply", re.IGNORECASE)),
        page.get_by_text(re.compile("^发送$|^评论$|^回复$|^Send$|^Reply$", re.IGNORECASE)),
    ]
    for locator in candidates:
        try:
            count = locator.count()
        except Exception:
            continue
        for index in range(count - 1, -1, -1):
            item = locator.nth(index)
            try:
                if item.is_visible(timeout=1000) and item.is_enabled(timeout=1000):
                    item.click(timeout=3000)
                    return
            except Exception:
                continue
    raise RuntimeError("send button not found")


def should_submit(args: argparse.Namespace, target: dict[str, str]) -> bool:
    if args.mode == "draft-only":
        return False
    if args.yes:
        return True
    answer = input(
        f"Type SEND to submit reply to {target.get('title') or target.get('url')}: "
    ).strip()
    return answer == "SEND"


def run_browser(args: argparse.Namespace, reply_text: str) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("playwright is not installed; install it before running browser automation") from exc

    max_targets = clamp_max_targets(args.max_targets)
    records: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        if args.user_data_dir:
            context = playwright.chromium.launch_persistent_context(
                args.user_data_dir,
                headless=args.headless,
                slow_mo=args.slow_mo,
            )
            page = context.pages[0] if context.pages else context.new_page()
            close_target = context
        else:
            browser = playwright.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
            context = browser.new_context()
            page = context.new_page()
            close_target = browser

        try:
            start_url = args.start_url or build_search_url(args.platform, args.keyword)
            page.goto(start_url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            page.wait_for_timeout(args.settle_ms)
            check_or_pause_on_risk(page, args.pause_on_risk, args.pause_on_risk_seconds)

            if args.start_url:
                targets = [collect_current_page_target(page)]
            elif args.platform == "douyin":
                targets = collect_douyin_targets(page, max_targets)
            else:
                targets = [collect_current_page_target(page)]

            if not targets:
                records.append({"status": "skipped", "reason": "no visible targets found"})
                return build_execution_log(args.platform, args.keyword, args.mode, records)

            for target in targets[:max_targets]:
                try:
                    if not args.start_url and target.get("url"):
                        page.goto(target["url"], wait_until="domcontentloaded", timeout=args.timeout_ms)
                        page.wait_for_timeout(args.settle_ms)
                        check_or_pause_on_risk(page, args.pause_on_risk, args.pause_on_risk_seconds)
                    context_info = collect_context(page)
                    record = {
                        "status": "drafted",
                        "target": target.get("url"),
                        "title": target.get("title"),
                        "replyDraft": reply_text,
                        "context": context_info,
                    }
                    if should_submit(args, target):
                        fill_comment_box(page, reply_text)
                        click_send_button(page)
                        page.wait_for_timeout(args.settle_ms)
                        record["status"] = "submitted"
                    records.append(record)
                except Exception as exc:
                    records.append(
                        {
                            "status": "skipped",
                            "target": target.get("url"),
                            "title": target.get("title"),
                            "reason": str(exc),
                        }
                    )
        finally:
            close_target.close()

    return build_execution_log(args.platform, args.keyword, args.mode, records)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guarded social comment reply automation")
    parser.add_argument("--platform", required=True, choices=sorted(SUPPORTED_PLATFORMS))
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--reply-text")
    parser.add_argument("--reply-file")
    parser.add_argument("--mode", default="draft-only")
    parser.add_argument("--confirm-send", action="store_true")
    parser.add_argument("--yes", action="store_true", help="skip per-target SEND prompt after --confirm-send")
    parser.add_argument("--max-targets", type=int, default=MAX_SAFE_TARGETS)
    parser.add_argument("--start-url", help="open a specific URL instead of platform search")
    parser.add_argument("--user-data-dir", help="Chromium persistent profile with logged-in session")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--settle-ms", type=int, default=2500)
    parser.add_argument("--timeout-ms", type=int, default=30000)
    parser.add_argument("--output-json", help="write execution log to a JSON file")
    parser.add_argument("--pause-on-risk", action="store_true", help="pause for manual login or verification handling")
    parser.add_argument("--pause-on-risk-seconds", type=int, default=0, help="wait this many seconds instead of reading stdin")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    reply_text = read_reply_text(args.reply_text, args.reply_file)
    errors = validate_plan(
        platform=args.platform,
        keyword=args.keyword,
        reply_text=reply_text,
        mode=args.mode,
        confirm_send=args.confirm_send,
        max_targets=args.max_targets,
    )
    hard_errors = [error for error in errors if not error.startswith("max targets is capped")]
    if hard_errors:
        print(json.dumps({"ok": False, "errors": hard_errors}, ensure_ascii=False, indent=2))
        return 2
    if errors:
        print(json.dumps({"ok": True, "warnings": errors}, ensure_ascii=False, indent=2))

    log = run_browser(args, reply_text)
    output = json.dumps(log, ensure_ascii=False, indent=2)
    print(output)
    if args.output_json:
        Path(args.output_json).write_text(output + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
