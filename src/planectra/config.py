from __future__ import annotations

import json
from pathlib import Path

from planectra.models import GlobalConfig, ProjectConfig

PLANECTRA_DIR = Path.home() / ".planectra"
PROJECTS_DIR = PLANECTRA_DIR / "projects"
VECTORDB_DIR = PLANECTRA_DIR / "vectordb"
SESSIONS_DIR = PLANECTRA_DIR / "sessions"
SOCKET_PATH = PLANECTRA_DIR / "planectra.sock"
CONFIG_PATH = PLANECTRA_DIR / "config.json"


def ensure_dirs() -> None:
    PLANECTRA_DIR.mkdir(exist_ok=True)
    PROJECTS_DIR.mkdir(exist_ok=True)
    VECTORDB_DIR.mkdir(exist_ok=True)
    SESSIONS_DIR.mkdir(exist_ok=True)


def load_global_config() -> GlobalConfig:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text())
        return GlobalConfig(**data)
    config = GlobalConfig(socket_path=str(SOCKET_PATH))
    save_global_config(config)
    return config


def save_global_config(config: GlobalConfig) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(json.dumps(config.model_dump(), indent=2))


def load_project_config(project_uuid: str) -> ProjectConfig | None:
    path = PROJECTS_DIR / project_uuid / "config.json"
    if path.exists():
        return ProjectConfig(**json.loads(path.read_text()))
    return None


def save_project_config(config: ProjectConfig) -> None:
    project_dir = PROJECTS_DIR / config.project_uuid
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "plans").mkdir(exist_ok=True)
    (project_dir / "config.json").write_text(json.dumps(config.model_dump(), indent=2))


def get_project_for_dir(cwd: str) -> ProjectConfig | None:
    gc = load_global_config()
    project_uuid = gc.dir_to_project.get(cwd)
    if project_uuid:
        return load_project_config(project_uuid)
    return None


def create_project_config(project_name: str, project_dirs: list[str] | None = None) -> ProjectConfig:
    """Create a new ProjectConfig inheriting defaults from GlobalConfig."""
    gc = load_global_config()
    proj = ProjectConfig(
        project_name=project_name,
        project_dirs=project_dirs or [],
        use_rag=gc.default_use_rag,
        top_k=gc.default_top_k,
        rag_verbosity=gc.default_rag_verbosity,
        max_rag_tokens=gc.default_max_rag_tokens,
        include_user_comment=gc.default_include_user_comment,
    )
    proj.scan_project_ids = [proj.project_uuid]
    return proj


def list_all_projects() -> list[ProjectConfig]:
    projects = []
    if not PROJECTS_DIR.exists():
        return projects
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir():
            cfg = load_project_config(d.name)
            if cfg:
                projects.append(cfg)
    return projects
