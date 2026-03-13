
from planectra import config
from planectra.models import GlobalConfig, ProjectConfig


def test_ensure_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANECTRA_DIR", tmp_path / "planectra")
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "planectra" / "projects")
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "planectra" / "vectordb")

    config.ensure_dirs()
    assert (tmp_path / "planectra").is_dir()
    assert (tmp_path / "planectra" / "projects").is_dir()
    assert (tmp_path / "planectra" / "vectordb").is_dir()


def test_global_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANECTRA_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")

    gc = GlobalConfig(socket_path="/tmp/test.sock", dir_to_project={"/foo": "uuid-1"})
    config.save_global_config(gc)

    loaded = config.load_global_config()
    assert loaded.socket_path == "/tmp/test.sock"
    assert loaded.dir_to_project == {"/foo": "uuid-1"}


def test_project_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")

    proj = ProjectConfig(project_name="test-app", project_dirs=["/code/test-app"])
    config.save_project_config(proj)

    loaded = config.load_project_config(proj.project_uuid)
    assert loaded is not None
    assert loaded.project_name == "test-app"
    assert loaded.project_dirs == ["/code/test-app"]


def test_get_project_for_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PLANECTRA_DIR", tmp_path)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb")
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")

    proj = ProjectConfig(project_name="test", project_dirs=["/my/dir"])
    config.save_project_config(proj)

    gc = GlobalConfig(dir_to_project={"/my/dir": proj.project_uuid})
    config.save_global_config(gc)

    result = config.get_project_for_dir("/my/dir")
    assert result is not None
    assert result.project_name == "test"

    assert config.get_project_for_dir("/other/dir") is None
