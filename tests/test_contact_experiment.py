from __future__ import annotations

import pytest

from gmr_improved.contact_experiment import load_contact_experiment_config


def test_contact_config_loader_requires_formal_role(tmp_path) -> None:
    path = tmp_path / "invalid.yaml"
    path.write_text("schema_version: 1\nexperiment_name: x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="formal_role"):
        load_contact_experiment_config(path)
