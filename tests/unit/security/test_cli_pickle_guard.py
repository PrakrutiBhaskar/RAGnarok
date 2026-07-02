"""
Regression tests for pickle-format rejection at the CLI's actual input
surfaces (config and queries file loading).

Prior to this test, `backend/security/pickle_detector.py` was fully
implemented and unit-tested in isolation but never called anywhere in
`backend/` — the README's "pickle format rejected at all input surfaces"
claim was not true in practice. `_load_yaml` / `_load_json` in `cli.py`
are the two places user-supplied files actually enter the system, so
that's where the guard belongs.
"""

from __future__ import annotations

import pickle

import pytest
import typer

from backend.cli import _load_json, _load_yaml


class TestLoadYamlRejectsPickle:
    def test_missing_file_gives_clean_error_not_traceback(self, tmp_path):
        path = tmp_path / "does_not_exist.yaml"

        with pytest.raises(typer.Exit):
            _load_yaml(path)

    def test_rejects_pickle_file_disguised_as_yaml(self, tmp_path):
        path = tmp_path / "pipeline.yaml"
        path.write_bytes(pickle.dumps({"name": "malicious"}))

        with pytest.raises(typer.Exit):
            _load_yaml(path)

    def test_accepts_real_yaml(self, tmp_path):
        path = tmp_path / "pipeline.yaml"
        path.write_text("name: My Pipeline\nvector_db:\n  provider: chroma\n")

        result = _load_yaml(path)
        assert result["name"] == "My Pipeline"


class TestLoadJsonRejectsPickle:
    def test_missing_file_gives_clean_error_not_traceback(self, tmp_path):
        path = tmp_path / "does_not_exist.json"

        with pytest.raises(typer.Exit):
            _load_json(path)

    def test_rejects_pickle_file_disguised_as_json(self, tmp_path):
        path = tmp_path / "queries.json"
        path.write_bytes(pickle.dumps([{"query": "malicious"}]))

        with pytest.raises(typer.Exit):
            _load_json(path)

    def test_accepts_real_json_list(self, tmp_path):
        path = tmp_path / "queries.json"
        path.write_text('[{"query": "What is the refund policy?"}]')

        result = _load_json(path)
        assert result == [{"query": "What is the refund policy?"}]

    def test_accepts_real_json_wrapped_in_queries_key(self, tmp_path):
        path = tmp_path / "queries.json"
        path.write_text('{"queries": [{"query": "hello"}]}')

        result = _load_json(path)
        assert result == [{"query": "hello"}]
