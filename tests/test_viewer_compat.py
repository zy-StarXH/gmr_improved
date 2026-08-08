from __future__ import annotations

import pickle

import numpy as np

from gmr_improved.viewer_compat import create_viewer_compatible_copy


def test_compat_copy_adds_viewer_keys_without_changing_motion(tmp_path) -> None:
    source = tmp_path / "source.pkl"
    destination = tmp_path / "copy.pkl"
    payload = {
        "fps": 30.0,
        "root_pos": np.zeros((2, 3)),
        "root_rot": np.zeros((2, 4)),
        "dof_pos": np.zeros((2, 29)),
    }
    with source.open("wb") as stream:
        pickle.dump(payload, stream)
    result = create_viewer_compatible_copy(source, destination)
    with destination.open("rb") as stream:
        copy = pickle.load(stream)
    assert copy["local_body_pos"] is None
    assert copy["link_body_list"] is None
    assert result["added_keys"] == ["link_body_list", "local_body_pos"]
    np.testing.assert_array_equal(copy["dof_pos"], payload["dof_pos"])
