import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import submit_script_review as submitter


class SubmitScriptReviewTest(unittest.TestCase):
    def test_rejects_published_agent_profile_with_empty_prompt_json(self):
        response = {
            "code": 200,
            "data": {
                "body": {
                    "agentProfile": {
                        "agentProfileId": "ap-1",
                        "promptJson": "{}",
                    }
                }
            },
        }

        result = submitter.validate_agent_profile_prompt_response(response)

        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "agent_profile")
        self.assertIn("promptJson 为空", result["summary"])

    def test_accepts_agent_profile_with_required_prompt_content(self):
        response = {
            "code": 200,
            "data": {
                "body": {
                    "agentProfile": {
                        "agentProfileId": "ap-1",
                        "promptJson": json.dumps({
                            "openingPrompt": "您好，我是客服助理。",
                            "goals": "确认客户是否有采购意向。",
                        }, ensure_ascii=False),
                    }
                }
            },
        }

        result = submitter.validate_agent_profile_prompt_response(response)

        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
