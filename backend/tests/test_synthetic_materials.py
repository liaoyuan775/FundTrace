from collections import Counter
from pathlib import Path

import pytest

from tools.generate_multisource_fixtures import build_distribution, build_truth, generate_xlsx, validate_material_set


def test_synthetic_case_has_fixed_scale_and_multiformat_distribution():
    truth = build_truth()
    distribution = build_distribution(truth["transactions"])

    assert len(truth["entities"]) == 32
    assert len(truth["transactions"]) == 120
    assert len(distribution) == 10
    appearances = [transaction_id for item in distribution for transaction_id in item["transaction_ids"]]
    assert len(appearances) == 135
    assert len(set(appearances)) == 120
    assert sum(count - 1 for count in Counter(appearances).values()) == 15
    assert Counter(Path(item["filename"]).suffix for item in distribution) == {
        ".csv": 2,
        ".xlsx": 2,
        ".pdf": 2,
        ".docx": 2,
        ".png": 1,
        ".jpg": 1,
    }


def test_material_set_validation_rejects_missing_xlsx_files(tmp_path):
    (tmp_path / "materials").mkdir()

    with pytest.raises(RuntimeError, match="材料文件集合不完整"):
        validate_material_set(tmp_path)


def test_xlsx_generation_requires_explicit_artifact_runtime(tmp_path):
    with pytest.raises(RuntimeError, match="artifact-tool"):
        generate_xlsx(tmp_path, "node", "")
