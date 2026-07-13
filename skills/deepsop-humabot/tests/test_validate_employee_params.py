import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import validate_employee_params as validator


class ValidateEmployeeParamsTest(unittest.TestCase):
    def valid_body(self):
        return {
            "completed": True,
            "collaborationSubmitTaskParam": {
                "taskName": "小龙虾客户挖掘",
                "taskDescription": "挖掘苏州地区黄焖鸡餐饮老板200个",
                "currentModule": "content",
                "executionMode": 1,
                "recentFilter": True,
                "sourceSettings": None,
                "employeeParams": {
                    "AiWa": {
                        "totalTarget": 200,
                        "incrementalTarget": 5000,
                        "upperLimitTarget": 5000,
                        "keywordList": ["黄焖鸡", "餐饮老板"],
                        "continent": None,
                        "country": None,
                        "countryCodeList": [],
                        "excludeCountry": None,
                        "excludeCountryCodeList": [],
                        "addressObjList": [
                            {
                                "type": 1,
                                "province": "",
                                "city": "苏州市",
                                "county": "",
                                "address": "",
                            }
                        ],
                        "industryList": ["餐饮"],
                    }
                },
            },
        }

    def test_rejects_suzhou_as_free_text_address(self):
        body = self.valid_body()
        body["collaborationSubmitTaskParam"]["employeeParams"]["AiWa"]["addressObjList"] = [
            {
                "type": 0,
                "province": "",
                "city": "",
                "county": "",
                "address": "苏州",
            }
        ]

        result = validator.run(body)

        self.assertFalse(result["ok"])
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("CITY_ALIAS_SHOULD_BE_STRUCTURED", codes)

    def test_accepts_suzhou_as_structured_city(self):
        result = validator.run(self.valid_body())

        self.assertTrue(result["ok"], result)

    def test_rejects_other_known_city_as_free_text_address(self):
        body = self.valid_body()
        body["collaborationSubmitTaskParam"]["employeeParams"]["AiWa"]["addressObjList"] = [
            {
                "type": 0,
                "province": "",
                "city": "",
                "county": "",
                "address": "杭州地区",
            }
        ]

        result = validator.run(body)

        self.assertFalse(result["ok"])
        suggestions = "\n".join(error.get("suggestion", "") for error in result["errors"])
        self.assertIn('"city":"杭州市"', suggestions)

    def aiwa_fran_body(self):
        body = self.valid_body()
        cstp = body["collaborationSubmitTaskParam"]
        cstp["sourceSettings"] = {
            "groupId": [],
            "stageId": [],
            "labelId": [],
            "level": [],
            "seasGroupIds": [],
            "addressId": [],
            "fileList": [],
            "updateSupport": 1,
            "cascader": None,
            "aiMining": None,
            "customerMining": None,
            "seasMining": None,
            "uploadMining": None,
            "countryId": None,
            "addressMining": None,
        }
        cstp["employeeParams"]["Fran"] = {
            "ringingDuration": 25,
            "incrementalTarget": 1000,
            "upperLimitTarget": 1000,
            "minConcurrency": 1,
            "priority": "Daily",
            "callingNumber": ["30350903"],
            "scriptId": "script-001",
            "agentProfileId": "chatbot-001",
        }
        return body

    def test_rejects_aiwa_fran_when_fran_contains_only_content_step_fields(self):
        body = self.aiwa_fran_body()
        body["collaborationSubmitTaskParam"]["employeeParams"]["Fran"] = {
            "scriptId": "script-001",
            "agentProfileId": "chatbot-001",
        }

        result = validator.run(body)

        self.assertFalse(result["ok"])
        codes = {error["code"] for error in result["errors"]}
        self.assertIn("FRAN_CONTENT_STEP_ONLY", codes)

    def test_rejects_aiwa_fran_when_joint_source_settings_key_missing(self):
        body = self.aiwa_fran_body()
        del body["collaborationSubmitTaskParam"]["sourceSettings"]["aiMining"]

        result = validator.run(body)

        self.assertFalse(result["ok"])
        errors = result["errors"]
        self.assertTrue(
            any(
                error["path"] == "...sourceSettings.aiMining"
                and error["code"] == "MISSING_KEY"
                for error in errors
            ),
            errors,
        )

    def test_accepts_aiwa_fran_frontend_chain_body(self):
        result = validator.run(self.aiwa_fran_body())

        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
