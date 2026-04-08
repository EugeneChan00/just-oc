"""Tests for Scaffolder — mock workspace creation."""

from autoresearch.harness.scaffolder import Scaffolder


class TestScaffolder:
    def test_scaffold_creates_directory(self, tmp_path):
        s = Scaffolder(test_dir=tmp_path)
        path = s.scaffold("ceo", "run-001-1")
        assert path.exists()
        assert path.is_dir()

    def test_scaffold_has_package_json(self, tmp_path):
        s = Scaffolder(test_dir=tmp_path)
        path = s.scaffold("ceo", "run-001-1")
        assert (path / "package.json").exists()

    def test_scaffold_has_src_dir(self, tmp_path):
        s = Scaffolder(test_dir=tmp_path)
        path = s.scaffold("ceo", "run-001-1")
        assert (path / "src").is_dir()
        assert (path / "src" / "index.ts").exists()

    def test_scaffold_path_format(self, tmp_path):
        s = Scaffolder(test_dir=tmp_path)
        path = s.scaffold("ceo", "run-001-1")
        assert "ceo" in str(path)
        assert "run-001-1" in str(path)

    def test_cleanup_removes_directory(self, tmp_path):
        s = Scaffolder(test_dir=tmp_path / "autoresearch" / "test")
        path = s.scaffold("ceo", "run-001-1")
        assert path.exists()
        s.cleanup(path)
        assert not path.exists()
