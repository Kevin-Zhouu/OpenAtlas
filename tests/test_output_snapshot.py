import io
import tarfile

import pytest

from openatlas.execution import extract_output


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
    return stream.getvalue()


def test_repair_snapshot_preserves_deletions_and_unrelated_workspace(tmp_path):
    (tmp_path / "source").mkdir()
    (tmp_path / "source/core").write_bytes(b"obsolete crash dump")
    (tmp_path / "source/app.js").write_text("old")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist/obsolete.js").write_text("old")
    (tmp_path / "manifest.json").write_text("old")
    (tmp_path / "validation.json").write_text("keep publisher state")
    extract_output(
        [
            archive(
                {
                    "source/app.js": b"repaired",
                    "dist/index.html": b"new build",
                    "manifest.json": b'{"entrypoint":"index.html"}',
                }
            )
        ],
        tmp_path,
    )
    assert not (tmp_path / "source/core").exists()
    assert not (tmp_path / "dist/obsolete.js").exists()
    assert (tmp_path / "source/app.js").read_text() == "repaired"
    assert (tmp_path / "dist/index.html").read_text() == "new build"
    assert (tmp_path / "manifest.json").read_text() != "old"
    assert (tmp_path / "validation.json").read_text() == "keep publisher state"


@pytest.mark.parametrize(
    "bad_name,bad_content,secrets",
    [
        ("source/../../escape", b"bad", ()),
        ("source/leak.txt", b"fixture-private-token", ("fixture-private-token",)),
    ],
)
def test_invalid_snapshot_does_not_partially_overwrite_saved_work(
    tmp_path, bad_name, bad_content, secrets
):
    (tmp_path / "source").mkdir()
    (tmp_path / "source/app.js").write_text("saved")
    data = archive({"source/app.js": b"new", bad_name: bad_content})
    with pytest.raises(ValueError):
        extract_output([data], tmp_path, secrets)
    assert (tmp_path / "source/app.js").read_text() == "saved"
    assert list((tmp_path / "source").iterdir()) == [tmp_path / "source/app.js"]


def test_empty_snapshot_preserves_saved_work(tmp_path):
    (tmp_path / "source").mkdir()
    (tmp_path / "source/app.js").write_text("saved")
    with pytest.raises(ValueError, match="no deliverables"):
        extract_output([archive({})], tmp_path)
    assert (tmp_path / "source/app.js").read_text() == "saved"
