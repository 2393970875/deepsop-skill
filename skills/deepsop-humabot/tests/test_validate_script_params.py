import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_script_params as validator


class ValidateScriptParamsTest(unittest.TestCase):
    def valid_body(self):
        prompt = {
            "name": "",
            "gender": "",
            "age": "",
            "role": "",
            "communicationStyle": "",
            "openingPrompt": "您好，我是测试公司的客服助理。",
            "goals": "确认客户是否有采购意向。",
            "background": "",
            "skills": "",
            "workflow": "",
            "constraint": "",
            "output": "",
            "aiHangupOutput": "",
            "aiSilenceTimeoutOutput": "",
        }
        tts = {
            "voice": "CosyVoice:longcheng",
            "voiceShow": [0, "CosyVoice:longcheng"],
            "volume": 50,
            "speechRate": 0,
            "pitchRate": 0,
            "globalInterruptible": True,
            "engine": "ali",
            "nlsServiceType": "Managed",
        }
        return {
            "agentParams": {
                "model": "model_001",
                "agentProfileId": "",
                "promptJson": json.dumps(prompt, ensure_ascii=False),
                "labelsJson": "[]",
                "variablesJson": "[]",
            },
            "scriptParams": {
                "scriptId": "",
                "scriptName": "测试场景",
                "industry": "通用",
                "scene": "通用",
                "nluEngine": "Prompts",
                "nluAccessType": "Managed",
                "ttsConfig": json.dumps(tts, ensure_ascii=False),
            },
        }

    def test_rejects_scene_without_goal_and_script_name(self):
        body = self.valid_body()
        prompt = json.loads(body["agentParams"]["promptJson"])
        prompt.pop("goals")
        body["agentParams"]["promptJson"] = json.dumps(prompt, ensure_ascii=False)
        body["scriptParams"].pop("scriptName")

        result = validator.run(body)
        paths = {error["path"] for error in result["errors"]}

        self.assertFalse(result["ok"])
        self.assertIn("agentParams.promptJson::goals", paths)
        self.assertIn("scriptParams.scriptName", paths)

    def test_accepts_complete_scene_creation_body(self):
        result = validator.run(self.valid_body())
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
