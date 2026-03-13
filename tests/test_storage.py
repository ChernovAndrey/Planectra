from planectra import config
from planectra.models import PlanRecord
from planectra.storage import disk, vector


def test_disk_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")

    record = PlanRecord(
        project_uuid="proj-1",
        project_name="test",
        initial_prompt="Design auth system",
        plan_content="# Auth Plan\nUse JWT",
        num_attempts=2,
    )

    path = disk.save_plan(record)
    assert path.exists()

    loaded = disk.load_plan("proj-1", record.plan_uuid)
    assert loaded is not None
    assert loaded.initial_prompt == "Design auth system"
    assert loaded.num_attempts == 2


def test_disk_load_by_uuid(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")

    record = PlanRecord(
        project_uuid="proj-1",
        project_name="test",
        initial_prompt="test prompt",
        plan_content="test content",
    )
    disk.save_plan(record)

    found = disk.load_plan_by_uuid(record.plan_uuid)
    assert found is not None
    assert found.project_name == "test"

    assert disk.load_plan_by_uuid("nonexistent") is None


def test_disk_list_plans(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")

    for i in range(3):
        record = PlanRecord(
            project_uuid="proj-1",
            project_name="test",
            initial_prompt=f"prompt {i}",
            plan_content=f"content {i}",
        )
        disk.save_plan(record)

    plans = disk.list_plans("proj-1")
    assert len(plans) == 3


def test_disk_update_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")

    record = PlanRecord(
        project_uuid="proj-1",
        project_name="test",
        initial_prompt="test",
        plan_content="v1",
    )
    disk.save_plan(record)

    record.plan_issues = "Missing error handling"
    disk.update_plan(record)

    loaded = disk.load_plan("proj-1", record.plan_uuid)
    assert loaded is not None
    assert loaded.plan_issues == "Missing error handling"


def test_vector_add_and_query(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb")
    vector._client = None
    vector._collection = None

    vector.add_plan(
        plan_uuid="plan-1",
        document="Design a caching layer for API responses",
        project_uuid="proj-1",
        created_at="2026-01-01T00:00:00Z",
    )
    vector.add_plan(
        plan_uuid="plan-2",
        document="Implement user authentication with OAuth",
        project_uuid="proj-1",
        created_at="2026-01-02T00:00:00Z",
    )

    results = vector.query_similar("cache API responses", top_k=2)
    assert len(results) > 0
    assert results[0]["plan_uuid"] == "plan-1"
    assert results[0]["similarity"] > 0.5


def test_vector_query_with_project_filter(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb")
    vector._client = None
    vector._collection = None

    vector.add_plan("plan-a", "Build a REST API", "proj-a", "2026-01-01T00:00:00Z")
    vector.add_plan("plan-b", "Build a REST API", "proj-b", "2026-01-01T00:00:00Z")

    results = vector.query_similar("REST API", project_uuids=["proj-a"], top_k=5)
    assert all(r["metadata"]["project_uuid"] == "proj-a" for r in results)


def test_vector_plan_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb")
    vector._client = None
    vector._collection = None

    assert vector.plan_exists("nonexistent") is False

    vector.add_plan("plan-1", "test document", "proj-1", "2026-01-01T00:00:00Z")
    assert vector.plan_exists("plan-1") is True


def test_vector_empty_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "VECTORDB_DIR", tmp_path / "vectordb_empty")
    vector._client = None
    vector._collection = None

    results = vector.query_similar("anything", top_k=3)
    assert results == []
