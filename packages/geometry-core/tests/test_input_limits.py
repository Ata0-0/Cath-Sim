"""Input-safety tests: oversized, slow and unit-less meshes must be rejected."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cathsim_geometry import (
    MAX_FILE_BYTES,
    MAX_TRIANGLES,
    MeshRejected,
    check_input_limits,
    require_explicit_units,
    synthetic_chamber,
)


def test_oversized_file_is_rejected() -> None:
    with pytest.raises(MeshRejected, match="above the"):
        check_input_limits(MAX_FILE_BYTES + 1, 1000, 0.1)


def test_too_many_triangles_is_rejected() -> None:
    with pytest.raises(MeshRejected, match="triangles"):
        check_input_limits(1000, MAX_TRIANGLES + 1, 0.1)


def test_slow_parse_is_rejected_as_possible_bomb() -> None:
    with pytest.raises(MeshRejected, match="decompression bomb"):
        check_input_limits(1000, 1000, 999.0)


def test_units_are_never_guessed() -> None:
    assert require_explicit_units("mm") == 1.0
    assert require_explicit_units("cm") == 10.0
    with pytest.raises(MeshRejected, match="will not guess"):
        require_explicit_units("UNKNOWN_ASK_USER")


def test_synthetic_chamber_is_labelled_as_a_placeholder() -> None:
    vertices, faces, report = synthetic_chamber()
    assert vertices.shape[1] == 3
    assert faces.shape[1] == 3
    assert report.triangle_count == faces.shape[0]
    assert "not patient data" in report.provenance
    assert report.units == "mm"
    span_mm = vertices.max(axis=0) - vertices.min(axis=0)
    assert all(20.0 < value < 200.0 for value in span_mm[:2])
