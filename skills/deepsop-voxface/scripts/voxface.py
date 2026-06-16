#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DeepSOP VoxFace

数字人生成与参考音频脚本。

支持：
- 查询数字人模型
- 费用预估
- 提交数字人任务
- 只提交 / 只轮询
- 查询预设音色 / 克隆音色
- 预设音色 + 文字合成音频
- 克隆音色 + 文字合成音频
- 创建 / 修改 / 删除克隆音色
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

import requests


API_PREFIX = "https://ai.deepsop.com/prod-api"
BASE_URL = f"{API_PREFIX.rstrip('/')}/ai"
FILE_UPLOAD_URL = f"{API_PREFIX.rstrip('/')}/system/fileUpload/upload"
ESTIMATE_COST_URL = f"{BASE_URL}/estimate/cost"
MODEL_LIST_URL = f"{BASE_URL}/consumeSource/list?pageNum=1&pageSize=999"
AI_ARTIST_RECORD_URL = f"{BASE_URL}/AiArtistRecord"
AI_ARTIST_RESULT_URL = f"{BASE_URL}/AiArtistImage/getInfoByArtistId"
VOICE_FEATURE_LIST_URL = f"{BASE_URL}/model/pageByFeatureAndLanguage"
VOICE_CLONE_LIST_URL = f"{BASE_URL}/voice/clone/list"
VOICE_CLONE_CREATE_URL = f"{BASE_URL}/voice/clone/sync/create"
VOICE_CLONE_UPDATE_URL = f"{BASE_URL}/voice/clone/update"

API_KEY_ENV = "DEEPSOP_API_KEY"


def _read_env_file_value(path: str, key: str):
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


def _read_openclaw_json_api_key(skill_name: str | None = None):
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


def get_api_key():
    api_key = os.environ.get(API_KEY_ENV, "").strip()
    if api_key:
        return api_key

    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    api_key = _read_openclaw_json_api_key(skill_dir.name)
    if api_key:
        os.environ[API_KEY_ENV] = api_key
        return api_key

    candidates = [
        Path.cwd() / ".env",
        script_dir / ".env",
        skill_dir / ".env",
        Path.home() / ".openclaw" / ".env",
    ]
    for env_path in candidates:
        api_key = _read_env_file_value(str(env_path), API_KEY_ENV)
        if api_key:
            os.environ[API_KEY_ENV] = api_key
            return api_key
    return None


def check_api_key():
    api_key = get_api_key()
    if not api_key:
        print(f"[ERROR] 未配置 {API_KEY_ENV} 环境变量", file=sys.stderr)
        print("请先登录 OPClaw；如果不是在 OPClaw 中运行，请手动配置 DEEPSOP_API_KEY。", file=sys.stderr)
        print(f"\n请设置 API Key:")
        print(f"  Windows PowerShell: $env:{API_KEY_ENV}=\"sk-your_api_key_here\"")
        print(f"  Linux/macOS: export {API_KEY_ENV}=\"sk-your_api_key_here\"")
        return None
    return api_key


def get_headers():
    return {"x-api-key": get_api_key(), "Content-Type": "application/json"}


def request_json(method: str, url: str, *, params=None, json_body=None, files=None, timeout=30):
    response = requests.request(
        method=method,
        url=url,
        headers=get_headers() if files is None else {"x-api-key": get_api_key()},
        params=params,
        json=json_body,
        files=files,
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def read_json_arg(value: str):
    if value is None:
        return None
    if os.path.exists(value):
        with open(value, "r", encoding="utf-8") as f:
            return json.load(f)
    return json.loads(value)


def print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def fetch_human_models():
    payload = {"sourceTypeList": ["IMAGE_PROCESS", "IMAGE_MODEL", "VIDEO_MODEL", "HUMAN_MODEL"]}
    result = request_json("post", MODEL_LIST_URL, json_body=payload, timeout=30)
    if result.get("code") != 200:
        print(f"[ERROR] ???????{result.get('msg', '????')}", file=sys.stderr)
        return None

    rows = result.get("rows", [])
    return [item for item in rows if item.get("sourceType") == "HUMAN_MODEL"]


def list_models(include_disabled: bool = False):
    human_rows = fetch_human_models()
    if human_rows is None:
        return None

    human = [
        item for item in human_rows
        if include_disabled or str(item.get("hiddenState")) == "0"
    ]
    for item in human:
        status = "ON" if str(item.get("hiddenState")) == "0" else f"OFF(hiddenState={item.get('hiddenState')})"
        print(f"[{item.get('sourceValue')}] {status} {item.get('sourceName')} - {item.get('sourceDescription', '')}")
    return human


def check_human_model_available(method_type: str):
    """Validate selected HUMAN_MODEL sourceValue against the live API response."""
    human_rows = fetch_human_models()
    if human_rows is None:
        return False

    method_type = str(method_type)
    for item in human_rows:
        if str(item.get("sourceValue")) != method_type:
            continue
        hidden_state = str(item.get("hiddenState"))
        if hidden_state != "0":
            print(
                f"[ERROR] HUMAN_MODEL sourceValue={method_type} ({item.get('sourceName')}) "
                f"is disabled (hiddenState={hidden_state}); refusing to estimate or submit.",
                file=sys.stderr,
            )
            return False
        return True

    print(
        f"[ERROR] HUMAN_MODEL sourceValue={method_type} was not found in the live model list; "
        f"refusing to estimate or submit.",
        file=sys.stderr,
    )
    return False

def estimate_cost(task_type: str, method_type: str, parameter: dict):
    payload = {"type": task_type, "methodType": method_type, "parameter": json.dumps(parameter, ensure_ascii=False)}
    result = request_json("post", ESTIMATE_COST_URL, json_body=payload, timeout=30)
    if result.get("code") != 200:
        print(f"[ERROR] 费用预估失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    data = result.get("data") or {}
    print_json(data)
    return data


def submit_artist_task(task_type: str, method_type: str, parameter: dict):
    payload = {"type": task_type, "methodType": method_type, "parameter": json.dumps(parameter, ensure_ascii=False)}
    result = request_json("post", AI_ARTIST_RECORD_URL, json_body=payload, timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 提交任务失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result.get("data") or []


def poll_artist_result(task_id: str, interval: int = 5, max_wait: int = 1200):
    elapsed = 0
    last_status = None
    while elapsed < max_wait:
        result = request_json("get", f"{AI_ARTIST_RESULT_URL}/{task_id}", timeout=30)
        if result.get("code") != 200:
            elapsed += interval
            continue
        data = result.get("data") or {}
        status = data.get("status", "")
        if status != last_status:
            print(f"[INFO] {status} - {data.get('message', '')}", file=sys.stderr)
            last_status = status
        if status == "SUCCESS":
            url = data.get("url")
            urls = data.get("urls") or []
            return {"status": "SUCCESS", "url": urls[0] if urls else url, "urls": urls, "message": data.get("message", "生成成功")}
        if status == "FAILED":
            return {"status": "FAILED", "url": None, "message": data.get("message", "生成失败")}
        import time

        time.sleep(interval)
        elapsed += interval
    return {"status": "TIMEOUT", "url": None, "message": f"超时（{max_wait}秒）"}


def upload_file(file_path: str):
    if not os.path.exists(file_path):
        print(f"[ERROR] 文件不存在：{file_path}", file=sys.stderr)
        return None
    with open(file_path, "rb") as f:
        files = {"file": (os.path.basename(file_path), f)}
        result = request_json("post", FILE_UPLOAD_URL, files=files, timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 文件上传失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result.get("url")


def list_preset_voices():
    result = request_json("get", VOICE_FEATURE_LIST_URL, params={"pageNum": 1, "pageSize": 999}, timeout=30)
    if result.get("code") != 200:
        print(f"[ERROR] 查询预设音色失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    rows = result.get("rows", [])
    for item in rows:
        print(f"[{item.get('id')}] {item.get('feature')}·{item.get('language')} - {item.get('model')}")
    return rows


def list_clone_voices():
    result = request_json("get", VOICE_CLONE_LIST_URL, params={"pageNum": 1, "pageSize": 999}, timeout=30)
    if result.get("code") != 200:
        print(f"[ERROR] 查询克隆音色失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    rows = result.get("rows", [])
    for item in rows:
        print(f"[{item.get('id')}] {item.get('name')} - {item.get('status')} - {item.get('targetModel', '')}")
    return rows


def synthesize_preset_voice(text: str, voice_id: int, volume: int = 50, rate: float = 1.0, pitch: float = 1.0):
    payload = {"model": voice_id, "texts": [text], "volume": volume, "rate": rate, "pitch": pitch}
    result = request_json("post", f"{BASE_URL}/voiceGenerate/newcreate", json_body=payload, timeout=60)
    if not result or not result[0]:
        print("[ERROR] AI 生成配音失败，请选择内容对应的语言生成！", file=sys.stderr)
        return None
    oss_url_list = result[1] or []
    srt_url_list = result[2] or []
    save_res = request_json("post", f"{BASE_URL}/voiceGenerate/save", json_body={"ossUrlList": oss_url_list, "srtUrlList": srt_url_list}, timeout=60)
    if save_res.get("code") != 200:
        print(f"[ERROR] 保存配音失败：{save_res.get('msg', '未知错误')}", file=sys.stderr)
        return None
    audio_list = (save_res.get("data") or [[]])[0] or []
    return audio_list[0] if audio_list else None


def synthesize_clone_voice(text: str, voice_id: int):
    payload = {"text": text, "id": voice_id}
    result = request_json("post", f"{BASE_URL}/voice/clone/synthesize", json_body=payload, timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 合成失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result.get("msg")


def create_clone_voice(name: str, audio_url: str | None = None, audio_path: str | None = None, prefix: str = "DeepSop", remark: str | None = None):
    if audio_path and not audio_url:
        audio_url = upload_file(audio_path)
        if not audio_url:
            return None
    if not audio_url:
        print("[ERROR] 必须提供 audio_url 或 audio_path", file=sys.stderr)
        return None
    payload = {"name": name, "prefix": prefix, "audioUrl": audio_url, "remark": remark}
    result = request_json("post", VOICE_CLONE_CREATE_URL, json_body=payload, timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 创建音色失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result.get("data")


def update_clone_voice(data: dict):
    result = request_json("put", VOICE_CLONE_UPDATE_URL, json_body=data, timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 修改音色失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result.get("data")


def delete_clone_voice(voice_id: int):
    result = request_json("delete", f"{BASE_URL}/voice/clone/{voice_id}", timeout=60)
    if result.get("code") != 200:
        print(f"[ERROR] 删除音色失败：{result.get('msg', '未知错误')}", file=sys.stderr)
        return None
    return result


def build_human_parameter(args):
    return {
        "req_key": "jimeng_realman_avatar_picture_omni_v15",
        "methodType": args.method_type,
        "prompt": args.prompt,
        "image_url": args.image_url,
        "video_url": args.video_url,
        "audio_url": args.audio_url,
        "duration": args.duration,
        "output_resolution": args.output_resolution,
        "pe_fast_mode": args.output_resolution == "720",
        "ref_image_url": args.ref_image_url,
        "ref_prompt": args.ref_prompt,
    }


def resolve_audio_url_for_human(args):
    if args.audio_url:
        return args.audio_url

    if args.preset_voice_id is not None or args.preset_voice_model:
        voice_model = args.preset_voice_model or args.preset_voice_id
        if not args.voice_text:
            print("[ERROR] 预设音色合成数字人需要 --voice-text", file=sys.stderr)
            return None
        audio = synthesize_preset_voice(
            args.voice_text,
            voice_model,
            volume=args.volume,
            rate=args.rate,
            pitch=args.pitch,
        )
        if audio:
            print(f"[INFO] 预设音色已合成参考音频：{audio}", file=sys.stderr)
        return audio

    if args.clone_voice_id is not None:
        if not args.voice_text:
            print("[ERROR] 克隆音色合成数字人需要 --voice-text", file=sys.stderr)
            return None
        audio = synthesize_clone_voice(args.voice_text, args.clone_voice_id)
        if audio:
            print(f"[INFO] 克隆音色已合成参考音频：{audio}", file=sys.stderr)
        return audio

    return None


def ensure_human_params(args):
    if not args.audio_url:
        args.audio_url = resolve_audio_url_for_human(args)

    if args.method_type == "0":
        if not args.image_url:
            print("[ERROR] 请上传人像图片！", file=sys.stderr)
            return False
    elif args.method_type == "1":
        if not args.video_url:
            print("[ERROR] 请上传人像视频！", file=sys.stderr)
            return False
    else:
        print(f"[ERROR] 未知数字人 methodType：{args.method_type}", file=sys.stderr)
        return False

    if not args.audio_url:
        print("[ERROR] 请上传参考音频！", file=sys.stderr)
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description="DeepSOP VoxFace 数字人生成与参考音频脚本")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list-models", action="store_true")
    mode.add_argument("--estimate", action="store_true")
    mode.add_argument("--create", action="store_true")
    mode.add_argument("--submit-only", action="store_true")
    mode.add_argument("--poll", metavar="TASK_ID")
    mode.add_argument("--list-preset-voices", action="store_true")
    mode.add_argument("--list-clone-voices", action="store_true")
    mode.add_argument("--synthesize-preset", action="store_true")
    mode.add_argument("--synthesize-clone", action="store_true")
    mode.add_argument("--create-voice", action="store_true")
    mode.add_argument("--update-voice", action="store_true")
    mode.add_argument("--delete-voice", action="store_true")

    parser.add_argument("--task-type", default="12")
    parser.add_argument("--method-type", default=None)
    parser.add_argument("--prompt")
    parser.add_argument("--image-url")
    parser.add_argument("--video-url")
    parser.add_argument("--audio-url")
    parser.add_argument("--duration", type=int)
    parser.add_argument("--output-resolution", default="720")
    parser.add_argument("--ref-image-url")
    parser.add_argument("--ref-prompt")
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--max-wait", type=int, default=1200)
    parser.add_argument("--json-output", action="store_true")
    parser.add_argument("--include-disabled", action="store_true",
                        help="??????? hiddenState != 0 ? HUMAN_MODEL????????????")

    parser.add_argument("--text")
    parser.add_argument("--voice-text")
    parser.add_argument("--voice-id", type=int)
    parser.add_argument("--voice-model")
    parser.add_argument("--preset-voice-id", type=int)
    parser.add_argument("--preset-voice-model")
    parser.add_argument("--clone-voice-id", type=int)
    parser.add_argument("--volume", type=int, default=50)
    parser.add_argument("--rate", type=float, default=1.0)
    parser.add_argument("--pitch", type=float, default=1.0)
    parser.add_argument("--name")
    parser.add_argument("--audio-path")
    parser.add_argument("--prefix", default="DeepSop")
    parser.add_argument("--remark")
    parser.add_argument("--update-json")

    args = parser.parse_args()

    if not check_api_key():
        sys.exit(1)

    if args.list_models:
        rows = list_models(include_disabled=args.include_disabled)
        sys.exit(0 if rows is not None else 1)

    if args.list_preset_voices:
        rows = list_preset_voices()
        sys.exit(0 if rows is not None else 1)

    if args.list_clone_voices:
        rows = list_clone_voices()
        sys.exit(0 if rows is not None else 1)

    if args.poll:
        result = poll_artist_result(args.poll, interval=args.interval, max_wait=args.max_wait)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False))
        elif result.get("status") == "SUCCESS":
            print(result.get("url", ""))
        else:
            print(result.get("message", ""), file=sys.stderr)
        sys.exit(0 if result.get("status") == "SUCCESS" else 1)

    if args.synthesize_preset:
        voice_model = args.voice_model or args.voice_id
        if not args.text or voice_model is None:
            print("[ERROR] 预设音色合成需要 --text 和 --voice-model（或 --voice-id）", file=sys.stderr)
            sys.exit(1)
        audio = synthesize_preset_voice(args.text, voice_model, volume=args.volume, rate=args.rate, pitch=args.pitch)
        if not audio:
            sys.exit(1)
        if args.json_output:
            print(json.dumps({"status": "SUCCESS", "url": audio}, ensure_ascii=False))
        else:
            print(audio)
        sys.exit(0)

    if args.synthesize_clone:
        if not args.text or args.voice_id is None:
            print("[ERROR] 克隆音色合成需要 --text 和 --voice-id", file=sys.stderr)
            sys.exit(1)
        audio = synthesize_clone_voice(args.text, args.voice_id)
        if not audio:
            sys.exit(1)
        if args.json_output:
            print(json.dumps({"status": "SUCCESS", "url": audio}, ensure_ascii=False))
        else:
            print(audio)
        sys.exit(0)

    if args.create_voice:
        if not args.name:
            print("[ERROR] 创建音色需要 --name", file=sys.stderr)
            sys.exit(1)
        data = create_clone_voice(args.name, audio_url=args.audio_url, audio_path=args.audio_path, prefix=args.prefix, remark=args.remark)
        if not data:
            sys.exit(1)
        if args.json_output:
            print(json.dumps(data, ensure_ascii=False))
        else:
            print_json(data)
        sys.exit(0)

    if args.update_voice:
        if not args.update_json:
            print("[ERROR] 修改音色需要 --update-json", file=sys.stderr)
            sys.exit(1)
        data = read_json_arg(args.update_json)
        if not isinstance(data, dict):
            print("[ERROR] --update-json 必须是对象 JSON", file=sys.stderr)
            sys.exit(1)
        updated = update_clone_voice(data)
        if not updated:
            sys.exit(1)
        print_json(updated)
        sys.exit(0)

    if args.delete_voice:
        if args.voice_id is None:
            print("[ERROR] 删除音色需要 --voice-id", file=sys.stderr)
            sys.exit(1)
        deleted = delete_clone_voice(args.voice_id)
        if not deleted:
            sys.exit(1)
        if args.json_output:
            print(json.dumps(deleted, ensure_ascii=False))
        else:
            print_json(deleted)
        sys.exit(0)

    if args.estimate:
        if not args.method_type:
            print("[ERROR] 预估费用需要 --method-type", file=sys.stderr)
            sys.exit(1)
        parameter = build_human_parameter(args)
        data = estimate_cost(args.task_type, args.method_type, parameter)
        sys.exit(0 if data else 1)

    if args.create or args.submit_only:
        if not args.method_type:
            print("[ERROR] 数字人生成需要 --method-type", file=sys.stderr)
            sys.exit(1)
        if not ensure_human_params(args):
            sys.exit(1)

        parameter = build_human_parameter(args)
        estimate = estimate_cost(args.task_type, args.method_type, parameter)
        if not estimate:
            sys.exit(1)
        if estimate.get("sufficientBalance") is False:
            print("[ERROR] 余额不足，无法提交创建任务。", file=sys.stderr)
            sys.exit(1)

        task_ids = submit_artist_task(args.task_type, args.method_type, parameter)
        if not task_ids:
            sys.exit(1)
        first_task_id = task_ids[0]

        if args.submit_only:
            if args.json_output:
                print(json.dumps({"status": "SUBMITTED", "task_id": first_task_id}, ensure_ascii=False))
            else:
                print(first_task_id)
            sys.exit(0)

        result = poll_artist_result(first_task_id, interval=args.interval, max_wait=args.max_wait)
        if args.json_output:
            print(json.dumps(result, ensure_ascii=False))
        elif result.get("status") == "SUCCESS":
            print(result.get("url", ""))
        else:
            print(result.get("message", ""), file=sys.stderr)
        sys.exit(0 if result.get("status") == "SUCCESS" else 1)

    parser.error("未选择有效模式")


if __name__ == "__main__":
    main()
