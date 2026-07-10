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


if __name__ == "__main__":
    unittest.main()
