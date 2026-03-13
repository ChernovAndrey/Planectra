from planectra.models import ConversationTurn, GlobalConfig, PlanRecord, ProjectConfig, SessionState


def test_plan_record_defaults():
    record = PlanRecord(
        project_uuid="proj-1",
        project_name="test",
        initial_prompt="Design a caching layer",
        plan_content="# Plan\nUse Redis",
    )
    assert record.plan_uuid  # UUID auto-generated
    assert record.num_attempts == 1
    assert record.conversation == []
    assert record.plan_issues is None
    assert record.created_at  # ISO timestamp auto-generated


def test_conversation_turn():
    turn = ConversationTurn(role="user", content="Add error handling", attempt_number=2)
    assert turn.role == "user"
    assert turn.attempt_number == 2


def test_project_config_defaults():
    proj = ProjectConfig(project_name="my-app")
    assert proj.project_uuid  # UUID auto-generated
    assert proj.use_rag is True
    assert proj.top_k == 3
    assert proj.rag_verbosity == "standard"
    assert proj.max_rag_tokens == 4000


def test_global_config_defaults():
    gc = GlobalConfig()
    assert gc.version == "0.1.0"
    assert gc.dir_to_project == {}


def test_session_state():
    session = SessionState(session_id="sess-1")
    assert session.session_id == "sess-1"
    assert session.in_plan_mode is False
    assert session.rag_done is False
    assert session.iteration_count == 0
