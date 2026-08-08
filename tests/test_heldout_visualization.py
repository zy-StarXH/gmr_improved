from pathlib import Path

from gmr_improved.heldout_visualization import sha256_file


def test_visualization_sha256(tmp_path: Path) -> None:
    path = tmp_path / "known.txt"
    path.write_bytes(b"abc")
    assert sha256_file(path) == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )

