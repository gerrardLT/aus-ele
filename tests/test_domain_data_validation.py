# -*- coding: utf-8 -*-
"""Unit tests for the hand-maintained domain JSON validation layer (R6.6, 2026-09-06).

覆盖四块：
1. 真实 data/ 下 5 份文件当前全部通过（结构演进/误编辑时这里先红）；
2. 破损样本 —— 每类「会静默污染下游分析」的填错都必须被抓（诊断 §4.4）；
3. knowledge_health.check_domain_data_schemas 的三态映射
   （error → overdue / warning → due_soon / 干净 → ok）；
4. 审查修复回归（2026-09-06）：非 UTF-8 文件隔离 / 校验层不可用降级 / capacity
   状态白名单与 CapacityProject Literal 的双向锁。
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import get_args
from unittest.mock import patch

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services import domain_data_validation
from services.domain_data_validation import (
    validate_all,
    validate_capacity_data,
    validate_coal_retirement_schedule,
    validate_contract_revenue_defaults,
    validate_financial_evidence,
    validate_regional_fee_defaults,
)
from services.knowledge_health import check_domain_data_schemas

from models.capacity_models import CapacityProject


# ---------------------------------------------------------------------------
# 最小合法样本（只含各校验器要求的字段，构造破损样本时在其上做变异）
# ---------------------------------------------------------------------------


def _minimal_capacity_data(n_projects=6):
    return {
        "metadata": {"last_updated": "2026-09-01"},
        "projects": [
            {
                "project_name": f"Project {i}",
                "region": "NSW1",
                "capacity_mw": 100,
                "duration_hours": 2,
                "status": "committed",
            }
            for i in range(n_projects)
        ],
        "interconnectors": [
            {
                "name": "TestLink",
                "from_region": "NSW1",
                "to_region": "QLD1",
                "capacity_mw": 500,
                "convergence_factor": 0.9,
            }
        ],
    }


def _minimal_coal_schedule():
    return {
        "metadata": {"last_updated": "2026-09-01"},
        "retirements": [
            {
                "plant_name": "Test Plant",
                "region": "NSW1",
                "confidence": "high",
                "capacity_mw": 100,
                "expected_closure_date": "2030-06-30",
            }
        ],
    }


def _minimal_fee_defaults():
    return {
        region: {"region": region}
        for region in ("NSW1", "QLD1", "SA1", "TAS1", "VIC1", "WEM")
    }


def _minimal_contract_revenue():
    return {
        "meta": {"updated_at": "2026-09-01"},
        "cis": {"floor_price": 50},
        "wem_brcp": {"floor_price": 60},
    }


def _minimal_financial_evidence():
    return {
        "metadata": {"last_updated": "2026-09-01"},
        "cost_structure_evidence": {"evidence_points": [{"source": "test", "value": 1}]},
        "forward_price_evidence": {"evidence_points": [{"source": "test", "value": 2}]},
    }


def _all_minimal_files():
    return {
        "capacity_data.json": _minimal_capacity_data(),
        "coal_retirement_schedule.json": _minimal_coal_schedule(),
        "regional_fee_defaults.json": _minimal_fee_defaults(),
        "contract_revenue_defaults.json": _minimal_contract_revenue(),
        "financial_evidence.json": _minimal_financial_evidence(),
    }


def _write_files(directory, files):
    for name, payload in files.items():
        path = Path(directory) / name
        if isinstance(payload, str):  # 允许直接写坏 JSON 文本
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. 真实文件回归
# ---------------------------------------------------------------------------


class RealDataRegressionTests(unittest.TestCase):
    def test_real_data_dir_all_pass(self):
        result = validate_all()
        self.assertEqual(
            set(result),
            {"capacity_data.json", "coal_retirement_schedule.json",
             "regional_fee_defaults.json", "contract_revenue_defaults.json",
             "financial_evidence.json"},
        )
        for name, report in result.items():
            self.assertTrue(report["ok"], f"{name} 意外校验失败: {report['errors']}")
            self.assertEqual(report["errors"], [], name)


# ---------------------------------------------------------------------------
# 2. per-file 校验器的破损样本
# ---------------------------------------------------------------------------


class CapacityDataTests(unittest.TestCase):
    def test_minimal_valid(self):
        report = validate_capacity_data(_minimal_capacity_data())
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(report["warnings"], [])

    def test_negative_capacity_caught(self):
        data = _minimal_capacity_data()
        data["projects"][0]["capacity_mw"] = -5
        report = validate_capacity_data(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("capacity_mw 必须为正数" in e for e in report["errors"]))

    def test_region_outside_whitelist_caught(self):
        data = _minimal_capacity_data()
        data["projects"][0]["region"] = "XX1"
        report = validate_capacity_data(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("region" in e for e in report["errors"]))

    def test_status_outside_whitelist_caught(self):
        # 新状态必须先确认消费方真的会处理 —— 白名单刻意让校验变红
        data = _minimal_capacity_data()
        data["projects"][0]["status"] = "retired"
        report = validate_capacity_data(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("status" in e for e in report["errors"]))

    def test_convergence_factor_out_of_range_caught(self):
        data = _minimal_capacity_data()
        data["interconnectors"][0]["convergence_factor"] = 1.5
        report = validate_capacity_data(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("convergence_factor" in e for e in report["errors"]))

    def test_truncated_projects_warns(self):
        data = _minimal_capacity_data(n_projects=3)
        report = validate_capacity_data(data)
        self.assertTrue(report["ok"])
        self.assertTrue(report["warnings"], "项目数骤减应产生 warning（疑似截断）")

    def test_bad_metadata_date_caught(self):
        data = _minimal_capacity_data()
        data["metadata"]["last_updated"] = "not-a-date"
        report = validate_capacity_data(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("last_updated" in e for e in report["errors"]))


class CoalRetirementTests(unittest.TestCase):
    def test_minimal_valid(self):
        report = validate_coal_retirement_schedule(_minimal_coal_schedule())
        self.assertTrue(report["ok"], report["errors"])

    def test_bad_closure_date_caught(self):
        data = _minimal_coal_schedule()
        data["retirements"][0]["expected_closure_date"] = "2030/06/30"
        report = validate_coal_retirement_schedule(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("expected_closure_date" in e for e in report["errors"]))

    def test_region_outside_whitelist_caught(self):
        data = _minimal_coal_schedule()
        data["retirements"][0]["region"] = "XX1"
        report = validate_coal_retirement_schedule(data)
        self.assertFalse(report["ok"])


class RegionalFeeTests(unittest.TestCase):
    def test_minimal_valid(self):
        report = validate_regional_fee_defaults(_minimal_fee_defaults())
        self.assertTrue(report["ok"], report["errors"])

    def test_missing_region_caught(self):
        data = _minimal_fee_defaults()
        del data["WEM"]
        report = validate_regional_fee_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("缺少区域配置" in e for e in report["errors"]))

    def test_region_key_value_mismatch_caught(self):
        data = _minimal_fee_defaults()
        data["NSW1"]["region"] = "VIC1"
        report = validate_regional_fee_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("与键名不一致" in e for e in report["errors"]))

    def test_unknown_top_level_field_caught(self):
        # 拼错的字段名会被 pydantic extra=ignore 静默吞掉 —— 必须手动抓
        data = _minimal_fee_defaults()
        data["NSW1"]["aemo_particpant_fee"] = {"rate_per_mwh": 0.4}  # 拼错
        report = validate_regional_fee_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("aemo_particpant_fee" in e and "未知字段" in e for e in report["errors"]))

    def test_unknown_sub_field_caught(self):
        data = _minimal_fee_defaults()
        data["NSW1"]["mlf"] = {"value": 0.97, "valu": 0.98}  # 子字段拼错
        report = validate_regional_fee_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("mlf.valu" in e and "未知字段" in e for e in report["errors"]))

    def test_value_range_violation_caught(self):
        # pydantic Field 值域：mlf ∈ [0.50, 1.50]
        data = _minimal_fee_defaults()
        data["SA1"]["mlf"] = {"value": 2.0}
        report = validate_regional_fee_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("RegionalFeeConfig 契约" in e for e in report["errors"]))


class ContractRevenueTests(unittest.TestCase):
    def test_minimal_valid(self):
        report = validate_contract_revenue_defaults(_minimal_contract_revenue())
        self.assertTrue(report["ok"], report["errors"])

    def test_missing_section_caught(self):
        data = _minimal_contract_revenue()
        del data["cis"]
        report = validate_contract_revenue_defaults(data)
        self.assertFalse(report["ok"])
        self.assertTrue(any("cis" in e for e in report["errors"]))


class FinancialEvidenceTests(unittest.TestCase):
    def test_minimal_valid(self):
        report = validate_financial_evidence(_minimal_financial_evidence())
        self.assertTrue(report["ok"], report["errors"])

    def test_empty_evidence_points_is_warning_only(self):
        # 证据缺失是「可信度问题」不是「会算错」—— 只降级为 warning
        data = _minimal_financial_evidence()
        data["cost_structure_evidence"]["evidence_points"] = []
        report = validate_financial_evidence(data)
        self.assertTrue(report["ok"])
        self.assertTrue(any("evidence_points 为空" in w for w in report["warnings"]))

    def test_missing_section_caught(self):
        data = _minimal_financial_evidence()
        del data["forward_price_evidence"]
        report = validate_financial_evidence(data)
        self.assertFalse(report["ok"])


# ---------------------------------------------------------------------------
# 3. validate_all 文件 IO 层（best-effort 隔离）
# ---------------------------------------------------------------------------


class ValidateAllIoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = self._tmp.name

    def test_missing_files_are_errors(self):
        result = validate_all(self.data_dir)
        self.assertEqual(len(result), 5)
        for name, report in result.items():
            self.assertFalse(report["ok"], name)
            self.assertTrue(any("文件不存在" in e for e in report["errors"]))

    def test_bad_json_isolated(self):
        files = _all_minimal_files()
        files["capacity_data.json"] = "{not valid json"
        _write_files(self.data_dir, files)
        result = validate_all(self.data_dir)
        self.assertFalse(result["capacity_data.json"]["ok"])
        self.assertTrue(any("JSON 不可解析" in e for e in result["capacity_data.json"]["errors"]))
        for name in result:
            if name != "capacity_data.json":
                self.assertTrue(result[name]["ok"], f"{name} 被坏文件串扰: {result[name]['errors']}")

    def test_validator_crash_isolated(self):
        files = _all_minimal_files()
        _write_files(self.data_dir, files)

        def _crash(_data):
            raise ZeroDivisionError("boom")

        with patch.dict(domain_data_validation.VALIDATORS, {"capacity_data.json": _crash}):
            result = validate_all(self.data_dir)
        self.assertFalse(result["capacity_data.json"]["ok"])
        self.assertTrue(any("校验器内部异常" in e for e in result["capacity_data.json"]["errors"]))
        for name in result:
            if name != "capacity_data.json":
                self.assertTrue(result[name]["ok"], name)

    def test_non_utf8_file_isolated(self):
        """审查 #1：GBK/UTF-16 误存文件抛 UnicodeDecodeError（ValueError 子类而非
        OSError），必须被隔离成单文件 error，不得击穿其余 4 份。"""
        files = _all_minimal_files()
        _write_files(self.data_dir, files)
        # 纯 ASCII 的 GBK 字节 == UTF-8，不会触发解码错 —— 必须带非 ASCII 字符
        payload = _minimal_capacity_data()
        payload["projects"][0]["project_name"] = "测试电站-中文"
        gbk_bytes = json.dumps(payload, ensure_ascii=False).encode("gbk")
        (Path(self.data_dir) / "capacity_data.json").write_bytes(gbk_bytes)

        result = validate_all(self.data_dir)
        self.assertFalse(result["capacity_data.json"]["ok"])
        self.assertTrue(
            any("文件编码/解析异常" in e for e in result["capacity_data.json"]["errors"]),
            result["capacity_data.json"]["errors"],
        )
        for name in result:
            if name != "capacity_data.json":
                self.assertTrue(result[name]["ok"], f"{name} 被坏编码文件串扰: {result[name]['errors']}")


# ---------------------------------------------------------------------------
# 4. knowledge_health 三态映射
# ---------------------------------------------------------------------------


def _fake_result(**overrides):
    base = {
        name: {"ok": True, "errors": [], "warnings": [], "item_count": 1}
        for name in domain_data_validation.VALIDATORS
    }
    for name, patch_fields in overrides.items():
        base[name].update(patch_fields)
    return base


class KnowledgeHealthMappingTests(unittest.TestCase):
    def test_errors_map_to_overdue(self):
        fake = _fake_result(**{"capacity_data.json": {"ok": False, "errors": ["坏值"]}})
        with patch("services.domain_data_validation.validate_all", return_value=fake):
            item = check_domain_data_schemas()
        self.assertEqual(item["status"], "overdue")
        self.assertIn("capacity_data.json", item["detail"])
        self.assertIn("运营节奏清单", item["sop_ref"])

    def test_warnings_only_map_to_due_soon(self):
        fake = _fake_result(**{"financial_evidence.json": {"warnings": ["evidence_points 为空"]}})
        with patch("services.domain_data_validation.validate_all", return_value=fake):
            item = check_domain_data_schemas()
        self.assertEqual(item["status"], "due_soon")
        self.assertIn("financial_evidence.json", item["detail"])

    def test_clean_maps_to_ok(self):
        with patch("services.domain_data_validation.validate_all", return_value=_fake_result()):
            item = check_domain_data_schemas()
        self.assertEqual(item["status"], "ok")
        self.assertIn("运营节奏清单", item["sop_ref"])
        # 审查 #6：份数文案跟随 VALIDATORS 注册数，不是字面量
        self.assertIn(f"{len(domain_data_validation.VALIDATORS)} 份", item["detail"])

    def test_validation_unavailable_maps_to_overdue(self):
        """审查 #2：校验层 import/调用报错时必须降级为 overdue，
        不得把整份健康报告带成「完全不可用」。"""
        with patch.dict(sys.modules, {"services.domain_data_validation": None}):
            item = check_domain_data_schemas()
        self.assertEqual(item["status"], "overdue")
        self.assertIn("校验层不可用", item["detail"])
        self.assertIn("运营节奏清单", item["sop_ref"])


# ---------------------------------------------------------------------------
# 5. capacity 状态白名单与 pydantic 真源的双向锁（审查 #3）
# ---------------------------------------------------------------------------


class CapacityStatusWhitelistLockTests(unittest.TestCase):
    """白名单从 CapacityProject.status 的 Literal 派生（不另写第二份口径），
    消费方红门（regional_timing_engine 只分桶 committed/construction/planning，
    registered 待确认）由本测试锁住：Literal 增删值 → 期望集红 → 必须先确认
    消费方再同步更新 EXPECTED_STATUSES。"""

    EXPECTED_STATUSES = {"committed", "construction", "planning", "registered"}

    def test_whitelist_derives_from_literal_true_source(self):
        literal_values = set(get_args(CapacityProject.model_fields["status"].annotation))
        self.assertEqual(domain_data_validation.PROJECT_STATUS_WHITELIST, literal_values)

    def test_literal_matches_consumer_confirmed_statuses(self):
        literal_values = set(get_args(CapacityProject.model_fields["status"].annotation))
        self.assertEqual(
            literal_values, self.EXPECTED_STATUSES,
            "CapacityProject.status Literal 变更：新状态必须先确认 regional_timing_engine "
            "是否真的处理它（分桶逻辑），确认后同步更新 EXPECTED_STATUSES",
        )


if __name__ == "__main__":
    unittest.main()
