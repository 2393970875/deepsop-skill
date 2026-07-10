import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import submit_task as submitter


class SubmitTaskEncodingGuardTest(unittest.TestCase):
    def test_rejects_question_mark_replacement_in_user_text(self):
        body = {
            "completed": True,
            "collaborationSubmitTaskParam": {
                "taskName": "???????????????",
                "taskDescription": "?????????????????100???????",
                "currentModule": "content",
                "executionMode": 1,
                "recentFilter": True,
                "employeeParams": {
                    "AiWa": {
                        "keywordList": ["???????", "raw rice noodle franchise"],
                        "addressObjList": [{"province": "???", "city": "???"}],
                        "countryCodeList": ["CN"],
                        "totalTarget": 100,
                        "incrementalTarget": 5000,
                    }
                },
            },
        }

        result = submitter.run_encoding_damage_check(body)

        self.assertIsNotNone(result)
        self.assertFalse(result["ok"])
        self.assertEqual(result["phase"], "encoding_damage")
        paths = {error["path"] for error in result["errors"]}
        self.assertIn("collaborationSubmitTaskParam.taskName", paths)
        self.assertIn("collaborationSubmitTaskParam.taskDescription", paths)
        self.assertIn("collaborationSubmitTaskParam.employeeParams.AiWa.keywordList[0]", paths)

    def test_allows_normal_chinese_question_marks(self):
        body = {
            "collaborationSubmitTaskParam": {
                "taskName": "帮我找云南米线加盟客户？",
                "taskDescription": "帮我找云南省昆明市100个米线加盟客户？",
                "employeeParams": {
                    "AiWa": {
                        "keywordList": ["米线加盟", "raw rice noodle franchise"],
                        "addressObjList": [{"province": "云南省", "city": "昆明市"}],
                    }
                },
            },
        }

        self.assertIsNone(submitter.run_encoding_damage_check(body))


if __name__ == "__main__":
    unittest.main()
