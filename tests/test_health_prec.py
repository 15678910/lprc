# -*- coding: utf-8 -*-
import health_check


def test_prec_fail_problem_threshold():
    assert health_check.prec_fail_problem({"failed": 50, "recheck_failed": 50}) is None
    assert "101" in health_check.prec_fail_problem({"failed": 1, "recheck_failed": 100})
    assert health_check.prec_fail_problem({}) is None
    assert health_check.prec_fail_problem({"failed": "x"}) is not None


def test_prec_files_checked():
    assert "prec/index.json" in health_check.PREC_FILES
    assert "prec/terms.json" in health_check.PREC_FILES
