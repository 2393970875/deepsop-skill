import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"
SKILL_PATH = Path(__file__).resolve().parents[1] / "SKILL.md"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_image", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_skill_requires_current_uploaded_image_as_image2_reference():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "本轮上传的原始图片路径" in skill
    assert "--reference-image" in skill
    assert "不得只把视觉理解结果或图片描述写进 prompt" in skill
    assert "仅允许作为历史调用的兼容输入" in skill
    assert "均能被 16 整除" in skill
    assert "2K + 16:9` 是 `2560x1440`" in skill
    assert "正方形应提交 `1:1`" in skill


def test_skill_blocks_submission_when_reference_upload_fails_and_preserves_prompt():
    skill = SKILL_PATH.read_text(encoding="utf-8")

    assert "参考图上传失败时不得提交生成任务" in skill
    assert "必须逐字保留用户原始提示词" in skill


def test_json_output_includes_cost_in_compute_units(capsys):
    module = load_module()
    module._LAST_ESTIMATED_COST = 60

    module._emit_cli_result(
        {"status": "SUCCESS", "url": "https://example.com/video.mp4", "message": "生成成功"},
        SimpleNamespace(json_output=True),
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["estimatedCost"] == 60
    assert payload["costUnit"] == "算力"
    assert "元" not in json.dumps(payload, ensure_ascii=False)


def test_v31fb_forces_720p_even_if_allowed_table_drifts(monkeypatch, capsys):
    module = load_module()
    module.DRY_RUN = True
    monkeypatch.setitem(module.VIDEO_RESOLUTIONS_BY_MT, "3", ["720p", "1080p", "4K"])

    task_id = module.create_video_task(
        "生成一个测试AI视频",
        model="V3.1FB",
        generation_type="TEXT",
        resolution="1080p",
        ratio="16:9",
        duration=8,
    )

    assert task_id == "DRY_RUN_TASK_ID"
    output = capsys.readouterr().err
    marker = '{\n  "type": "9"'
    payload = json.loads(output[output.index(marker):])
    parameter = json.loads(payload["parameter"])
    assert payload["saveToDatabase"] is True
    assert parameter["methodType"] == "3"
    assert parameter["resolution"] == "720p"
    assert parameter["duration"] == 8


def test_v31fb_default_generation_type_matches_frontend_reference(capsys):
    module = load_module()
    module.DRY_RUN = True

    task_id = module.create_video_task(
        "让参考图中的人物轻微点头",
        model="V3.1FB",
        image_url_list=["https://example.com/ref.png"],
    )

    assert task_id == "DRY_RUN_TASK_ID"
    output = capsys.readouterr().err
    marker = '{\n  "type": "9"'
    payload = json.loads(output[output.index(marker):])
    parameter = json.loads(payload["parameter"])
    assert payload["saveToDatabase"] is True
    assert parameter["methodType"] == "3"
    assert parameter["generationType"] == "REFERENCE"
    assert parameter["imageUrlList"] == ["https://example.com/ref.png"]


def test_human_video_model_payload_matches_frontend(capsys):
    module = load_module()
    module.DRY_RUN = True

    task_id = module.create_human_task(
        model="1",
        video_url="https://example.com/person.mp4",
        audio_url="https://example.com/audio.mp3",
        duration=12.5,
    )

    assert task_id == "DRY_RUN_TASK_ID"
    output = capsys.readouterr().err
    marker = '{\n  "type": "12"'
    payload = json.loads(output[output.index(marker):])
    parameter = json.loads(payload["parameter"])
    assert payload["saveToDatabase"] is True
    assert payload["methodType"] == "1"
    assert parameter == {
        "req_key": "jimeng_realman_avatar_picture_omni_v15",
        "methodType": "1",
        "prompt": "",
        "image_url": None,
        "video_url": "https://example.com/person.mp4",
        "audio_url": "https://example.com/audio.mp3",
        "duration": 12.5,
        "output_resolution": "720",
        "pe_fast_mode": True,
    }


def test_fetch_model_list_requests_image_video_and_human_models(monkeypatch):
    module = load_module()
    module._MODEL_LIST_CACHE = {"rows": None, "expires_at": 0.0}
    monkeypatch.setattr(module, "_load_disk_cache", lambda: None)
    monkeypatch.setattr(module, "_save_disk_cache", lambda rows, expires_at: None)

    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 200, "rows": []}

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append(json)
        return Response()

    monkeypatch.setattr(module.requests, "post", fake_post)

    module.fetch_model_list(force_refresh=True)

    assert calls[0] == {
        "sourceTypeList": ["IMAGE_MODEL", "VIDEO_MODEL", "HUMAN_MODEL"]
    }


def test_generate_video_uploads_local_reference_paths(monkeypatch):
    module = load_module()
    calls = {}

    def fake_upload_file(path):
        return f"https://files.example/{Path(path).name}"

    def fake_create_video_task(prompt, model=None, ratio=None, resolution=None, duration=None, **kwargs):
        calls["prompt"] = prompt
        calls["model"] = model
        calls["kwargs"] = kwargs
        return "TASK_ID"

    monkeypatch.setattr(module, "upload_file", fake_upload_file)
    monkeypatch.setattr(module, "create_video_task", fake_create_video_task)

    result = module.generate_video(
        "参考素材生成视频",
        model="W2.6r",
        image_url_list=["https://existing.example/ref.png"],
        image_path_list=[r"D:\tmp\local-image.png"],
        video_url_list=["https://existing.example/ref.mp4"],
        video_path_list=[r"D:\tmp\local-video.mp4"],
        audio_path=r"D:\tmp\voice.mp3",
        first_clip_path=r"D:\tmp\base-clip.mp4",
        submit_only=True,
    )

    assert result["task_id"] == "TASK_ID"
    assert calls["kwargs"]["image_url_list"] == [
        "https://existing.example/ref.png",
        "https://files.example/local-image.png",
    ]
    assert calls["kwargs"]["video_url_list"] == [
        "https://existing.example/ref.mp4",
        "https://files.example/local-video.mp4",
    ]
    assert calls["kwargs"]["audio_url"] == "https://files.example/voice.mp3"
    assert calls["kwargs"]["first_clip_url"] == "https://files.example/base-clip.mp4"


def test_generate_image_stops_when_local_reference_upload_fails(monkeypatch):
    module = load_module()
    monkeypatch.setattr(
        module,
        "create_generation_task",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("task must not be submitted")),
    )
    monkeypatch.setattr(module, "upload_file", lambda path: None)

    result = module.generate_image(
        "保持用户原始提示词",
        model="Image2",
        reference_image_path=r"D:\tmp\reference.png",
        submit_only=True,
    )

    assert result == {
        "status": "FAILED",
        "url": None,
        "message": "参考图上传失败，未提交生成任务",
        "model": "Image2",
    }


def test_generate_image_submits_uploaded_reference_and_original_prompt(monkeypatch):
    module = load_module()
    calls = {}

    def fake_create_task(prompt, quality=None, size=None, model=None, reference_image_url=None, **kwargs):
        calls["prompt"] = prompt
        calls["reference_image_url"] = reference_image_url
        return "TASK_ID"

    monkeypatch.setattr(
        module,
        "upload_file",
        lambda path: "https://files.example/reference.png",
    )
    monkeypatch.setattr(module, "create_generation_task", fake_create_task)

    original_prompt = "把参考图里的报价慢一天 单子少一年改成：AI落地到底能省多少钱？"
    result = module.generate_image(
        original_prompt,
        model="Image2",
        reference_image_path=r"D:\tmp\reference.png",
        submit_only=True,
    )

    assert result["task_id"] == "TASK_ID"
    assert calls["prompt"] == original_prompt
    assert calls["reference_image_url"] == "https://files.example/reference.png"


def test_generate_image_prefers_local_reference_over_existing_url(monkeypatch):
    module = load_module()
    calls = {}

    monkeypatch.setattr(
        module,
        "upload_file",
        lambda path: "https://files.example/current-upload.png",
    )

    def fake_create_task(prompt, quality=None, size=None, model=None, reference_image_url=None, **kwargs):
        calls["reference_image_url"] = reference_image_url
        return "TASK_ID"

    monkeypatch.setattr(module, "create_generation_task", fake_create_task)

    result = module.generate_image(
        "保持用户原始提示词",
        model="Image2",
        reference_image_path=r"D:\tmp\current-upload.png",
        reference_image_url="https://files.example/stale-reference.png",
        submit_only=True,
    )

    assert result["task_id"] == "TASK_ID"
    assert calls["reference_image_url"] == "https://files.example/current-upload.png"


def test_image2_reference_url_is_preflighted_before_submission(monkeypatch):
    module = load_module()
    module.DRY_RUN = False
    calls = {"post": 0}

    class Response:
        headers = {"Content-Type": "image/png", "Content-Length": "8"}
        content = b"\x89PNG\r\n\x1a\n"

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(module, "check_model_available", lambda model: True)
    monkeypatch.setattr(module, "estimate_generation_cost", lambda payload: True)

    def fake_post(*args, **kwargs):
        calls["post"] += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"code": 200, "data": ["TASK_ID"]},
        )

    monkeypatch.setattr(module.requests, "post", fake_post)

    task_id = module.create_generation_task(
        "测试参考图",
        model="Image2",
        reference_image_url="https://files.example/reference.png",
    )

    assert task_id == "TASK_ID"
    assert calls["post"] == 1


def test_image2_reference_url_failure_stops_submission(monkeypatch):
    module = load_module()
    module.DRY_RUN = False
    calls = {"post": 0, "estimate": 0}

    class Response:
        headers = {"Content-Type": "text/html"}
        content = b"<html>not an image</html>"

        def raise_for_status(self):
            return None

        def iter_content(self, chunk_size=65536):
            yield self.content

        def close(self):
            return None

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(module, "check_model_available", lambda model: True)
    monkeypatch.setattr(
        module,
        "estimate_generation_cost",
        lambda payload: calls.__setitem__("estimate", calls["estimate"] + 1) or True,
    )
    monkeypatch.setattr(
        module.requests,
        "post",
        lambda *args, **kwargs: calls.__setitem__("post", calls["post"] + 1),
    )

    with pytest.raises(module.GenerationTaskCreationError, match="参考图不可用.*内容类型"):
        module.create_generation_task(
            "测试参考图",
            model="Image2",
            reference_image_url="https://files.example/reference.png",
        )

    assert calls == {"post": 0, "estimate": 0}


def test_image2_reference_url_over_10mb_stops_submission(monkeypatch):
    module = load_module()
    module.DRY_RUN = False

    class Response:
        headers = {
            "Content-Type": "image/png",
            "Content-Length": str(10 * 1024 * 1024 + 1),
        }

        def raise_for_status(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: Response())
    monkeypatch.setattr(module, "check_model_available", lambda model: True)
    monkeypatch.setattr(
        module,
        "estimate_generation_cost",
        lambda payload: (_ for _ in ()).throw(AssertionError("must not estimate cost")),
    )

    with pytest.raises(module.GenerationTaskCreationError, match="超过 10MB"):
        module.create_generation_task(
            "测试参考图",
            model="Image2",
            reference_image_url="https://files.example/large.png",
        )


def test_image2_restriction_matches_provider_reference_limit():
    module = load_module()

    assert module.IMAGE_RESTRICTIONS_BY_MT["10"]["targetMaxSize"] == 10
    assert module.IMAGE_RESTRICTIONS_BY_MT["11"]["targetMaxSize"] == 10


def test_create_image_task_rejects_overlong_prompt_without_truncating(capsys):
    module = load_module()
    module.DRY_RUN = True
    prompt = "原" * 16001

    with pytest.raises(module.GenerationTaskCreationError, match="提示词长度.*超过限制 16000"):
        module.create_generation_task(prompt, model="Image2")

    assert '"type": "10"' not in capsys.readouterr().err


def _dry_run_image_parameter(module, capsys, **kwargs):
    module.DRY_RUN = True
    task_id = module.create_generation_task("测试图片", **kwargs)
    assert task_id == "DRY_RUN_TASK_ID"
    output = capsys.readouterr().err
    marker = '{\n  "type": "10"'
    payload = json.loads(output[output.index(marker):])
    return json.loads(payload["parameter"])


def test_image2_normalizes_legacy_star_pixel_size_to_provider_format(capsys):
    module = load_module()

    parameter = _dry_run_image_parameter(
        module,
        capsys,
        model="Image2",
        size="1792*1024",
    )

    assert parameter["methodType"] == "10"
    assert parameter["size"] == "1792x1024"


def test_image2_keeps_auto_and_ratio_sizes(capsys):
    module = load_module()

    auto_parameter = _dry_run_image_parameter(module, capsys, model="Image2")
    ratio_parameter = _dry_run_image_parameter(
        module,
        capsys,
        model="Image2",
        size="16:9",
    )

    assert auto_parameter["size"] == "auto"
    assert ratio_parameter["size"] == "16:9"


def test_pixel_form_image_models_keep_star_separator(capsys):
    module = load_module()

    parameter = _dry_run_image_parameter(
        module,
        capsys,
        model="6",
        size="1792x1024",
    )

    assert parameter["methodType"] == "6"
    assert parameter["size"] == "1792*1024"


@pytest.mark.parametrize(
    "size, message",
    [
        ("1000x1000", "能被 16 整除"),
        ("512x1024", "0.64MP 到 8.29MP"),
        ("3840x1024", "最长边不得超过 3840"),
    ],
)
def test_image2_rejects_provider_invalid_pixel_sizes(capsys, size, message):
    module = load_module()
    module.DRY_RUN = True

    with pytest.raises(module.GenerationTaskCreationError, match=message):
        module.create_generation_task("测试图片", model="Image2", size=size)

    assert '"type": "10"' not in capsys.readouterr().err


def test_seedream5_uses_frontend_resolution_for_wide_ratio(capsys):
    module = load_module()

    parameter = _dry_run_image_parameter(
        module,
        capsys,
        model="4",
        quality="2K",
        size="16:9",
    )

    assert parameter["methodType"] == "4"
    assert parameter["size"] == "2560x1440"


def test_seedream5_rejects_pixel_size_below_provider_minimum(capsys):
    module = load_module()
    module.DRY_RUN = True

    with pytest.raises(module.GenerationTaskCreationError, match="至少需要 3686400 像素"):
        module.create_generation_task(
            "测试图片",
            model="4",
            size="1024x1024",
        )

    assert '"type": "10"' not in capsys.readouterr().err


def test_gemini_image_normalizes_pixel_size_to_supported_ratio(capsys):
    module = load_module()

    parameter = _dry_run_image_parameter(
        module,
        capsys,
        model="5",
        size="1024x1024",
    )

    assert parameter["methodType"] == "5"
    assert parameter["size"] == "1:1"


def test_gemini_image_rejects_auto_size(capsys):
    module = load_module()
    module.DRY_RUN = True

    with pytest.raises(module.GenerationTaskCreationError, match="不支持 size='auto'"):
        module.create_generation_task("测试图片", model="5", size="auto")

    assert '"type": "10"' not in capsys.readouterr().err


def test_cli_exposes_single_audio_reference_params():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        check=True,
        capture_output=True,
    )
    stdout = result.stdout.decode("utf-8", errors="ignore")

    assert "--audio-url AUDIO_URL" in stdout
    assert "--audio AUDIO" in stdout


def test_default_model_prefers_prompt_description_match(monkeypatch):
    module = load_module()

    rows = [
        {
            "sourceType": "IMAGE_MODEL",
            "sourceValue": "8",
            "hiddenState": "0",
            "sourceName": "DeepSop·Nano2",
            "sourceDescription": "精细参数调节 文字渲染",
            "remark": "",
            "sourceKey": "usedNano2",
        },
        {
            "sourceType": "IMAGE_MODEL",
            "sourceValue": "10",
            "hiddenState": "0",
            "sourceName": "DeepSop·Image2",
            "sourceDescription": "精准控图 角色一致性 细节丰富",
            "remark": "",
            "sourceKey": "usedImage2",
        },
    ]
    monkeypatch.setattr(module, "fetch_model_list", lambda: rows)

    selected = module._get_default_model("image", prompt="生成角色一致性的产品海报")

    assert selected == "Image2"


def test_default_video_model_prefers_digital_human_sales_description(monkeypatch):
    module = load_module()

    rows = [
        {
            "sourceType": "VIDEO_MODEL",
            "sourceValue": "20",
            "hiddenState": "0",
            "sourceName": "DeepSop.S2.0 Evo",
            "sourceDescription": "影视级真人视频生成，数字人讲解视频",
            "remark": "",
            "sourceKey": "",
        },
        {
            "sourceType": "VIDEO_MODEL",
            "sourceValue": "21",
            "hiddenState": "0",
            "sourceName": "DeepSop.S2.0 Fast Evo",
            "sourceDescription": "可快速制作真人视频，数字人带货视频，输出画面基础流畅，音画同步效果出色，兼容15秒竖屏视频规格",
            "remark": "",
            "sourceKey": "",
        },
    ]
    monkeypatch.setattr(module, "fetch_model_list", lambda: rows)

    selected = module._get_default_model("video", prompt="数字人带货视频你用什么模型")

    assert selected == "S2.0FastEvo"


def test_recommend_model_for_prompt_returns_live_description(monkeypatch):
    module = load_module()

    rows = [
        {
            "sourceType": "VIDEO_MODEL",
            "sourceValue": "21",
            "hiddenState": "0",
            "sourceName": "DeepSop.S2.0 Fast Evo",
            "sourceDescription": "可快速制作真人视频，数字人带货视频，输出画面基础流畅，音画同步效果出色，兼容15秒竖屏视频规格",
            "remark": "",
            "sourceKey": "",
        },
    ]
    monkeypatch.setattr(module, "fetch_model_list", lambda: rows)

    recommendation = module.recommend_model_for_prompt("数字人带货视频你用什么模型")

    assert recommendation["sourceValue"] == "21"
    assert recommendation["key"] == "S2.0FastEvo"
    assert "数字人带货视频" in recommendation["description"]


def test_recommend_model_searches_all_source_types_and_prefers_description_match(monkeypatch):
    module = load_module()

    rows = [
        {
            "sourceType": "HUMAN_MODEL",
            "sourceValue": "1",
            "hiddenState": "0",
            "sourceName": "DeepSop.Video-digital human",
            "sourceDescription": "根据用户上传的视频片段 + 音频，生成与视频主体嘴型同步、表情自然的数字人视频。",
            "remark": "",
            "sourceKey": "",
        },
        {
            "sourceType": "VIDEO_MODEL",
            "sourceValue": "21",
            "hiddenState": "0",
            "sourceName": "DeepSop.S2.0 Fast Evo",
            "sourceDescription": "可快速制作真人视频，数字人带货视频，输出画面基础流畅，音画同步效果出色，兼容15秒竖屏视频规格",
            "remark": "",
            "sourceKey": "",
        },
    ]
    monkeypatch.setattr(module, "fetch_model_list", lambda: rows)

    recommendation = module.recommend_model_for_prompt("数字人带货视频你用什么模型")

    assert recommendation["sourceType"] == "VIDEO_MODEL"
    assert recommendation["sourceValue"] == "21"
