import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_image.py"


def load_module():
    spec = importlib.util.spec_from_file_location("generate_image", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
        resolution="1080p",
        ratio="16:9",
        duration=8,
    )

    assert task_id == "DRY_RUN_TASK_ID"
    output = capsys.readouterr().err
    marker = '{\n  "type": "9"'
    payload = json.loads(output[output.index(marker):])
    parameter = json.loads(payload["parameter"])
    assert parameter["methodType"] == "3"
    assert parameter["resolution"] == "720p"
    assert parameter["duration"] == 8


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
