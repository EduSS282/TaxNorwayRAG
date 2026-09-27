"""Operator controls never launch real models in the deterministic test suite."""

import json
import subprocess
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from taxguide.api.app import create_app
from taxguide.config.models import AppConfig
from taxguide.runtime.controller import AdminRequest, ConflictError, RuntimeController
from taxguide.runtime.models import Connections, LaunchProfile, LocalProfiles, ServiceStatus
from taxguide.runtime.probes import check
from taxguide.runtime.processes import (
    ChildHandle,
    DockerHandle,
    LocalLauncher,
    _flags,
    local_endpoint,
)
from taxguide.runtime.storage import SettingsStore
from taxguide.runtime.supervisor import Supervisor

TOKEN = "test-only-administration-key-0123456789"


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_process_flags_without_windows_constant(monkeypatch, platform):
    monkeypatch.setattr("taxguide.runtime.processes.sys.platform", platform)
    monkeypatch.delattr(subprocess, "CREATE_NO_WINDOW", raising=False)
    assert _flags() == 0


def test_process_flags_hide_windows_console(monkeypatch):
    monkeypatch.setattr("taxguide.runtime.processes.sys.platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert _flags() == 0x08000000


class FakeHandle:
    def __init__(self):
        self.code = None
        self.stops = 0

    def poll(self):
        return self.code

    def stop(self):
        self.stops += 1
        self.code = 0


class FakeLauncher:
    def __init__(self):
        self.calls = []
        self.handles = []

    def start(self, service, profile, connections):
        self.calls.append(service)
        handle = FakeHandle()
        self.handles.append(handle)
        return handle


def unavailable(service, connections):
    return ServiceStatus(service=service, url=connections.url(service), state="unavailable")


def available(service, connections):
    return ServiceStatus(
        service=service, url=connections.url(service), state="available", ready=True
    )


@pytest.fixture
def control(tmp_path):
    base = AppConfig()
    base.retrieval.reranker_provider = "llamacpp"
    profiles = LocalProfiles(
        services={
            name: LaunchProfile(
                executable=tmp_path / "native.exe", gpu_layers=1 if name == "generator" else 0
            )
            for name in ["generator", "embeddings", "reranker", "qdrant"]
        }
    )
    supervisor = Supervisor(
        profiles, launcher=FakeLauncher(), checker=unavailable, occupied=lambda _: False
    )
    return RuntimeController(base, SettingsStore(tmp_path / "connections.json"), supervisor)


def command(control, action, **kwargs):
    return control.execute(AdminRequest(action=action, revision=control.state.revision, **kwargs))


def test_atomic_save_replaces_backend_and_restores_settings(control):
    config_before, backend_before = control.snapshot()
    changed = control.state.current.model_copy(update={"generator_model": "another-model"})
    result = command(control, "save", connections=changed)
    assert result["connections"]["generator_model"] == "another-model"
    assert control.snapshot()[1] is not backend_before
    assert config_before.generation.model != "another-model"
    assert control.snapshot()[0].generation.model == "another-model"
    assert control.store.read().current == changed
    command(control, "restore")
    assert control.snapshot()[0].generation.model == config_before.generation.model
    restarted = RuntimeController(control.base, control.store, control.supervisor)
    assert restarted.state.current == control.state.current


def test_failed_write_and_stale_revision_leave_active_backend_untouched(control, monkeypatch):
    before = control.snapshot()
    changed = control.state.current.model_copy(update={"generator_model": "new-model"})
    with pytest.raises(ConflictError):
        control.execute(AdminRequest(action="save", connections=changed, revision="stale"))
    monkeypatch.setattr(control.store, "write", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        command(control, "save", connections=changed)
    assert control.snapshot() == before
    assert not control.store.path.exists()


def test_embedding_changes_require_acknowledgement_and_new_collection(control):
    changed = control.state.current.model_copy(update={"embedding_model": "new-embedding"})
    with pytest.raises(ValueError, match="different collection"):
        command(control, "save", connections=changed, confirm_reindex=True)
    changed = changed.model_copy(update={"qdrant_collection": "new_collection"})
    with pytest.raises(ValueError, match="acknowledgement"):
        command(control, "save", connections=changed)
    command(control, "save", connections=changed, confirm_reindex=True)
    with pytest.raises(ValueError, match="acknowledgement"):
        command(control, "restore")
    command(control, "restore", confirm_reindex=True)


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/model",
        "http://user:password@localhost:8080",
        "http://localhost:8080/v1",
        "http://localhost:8080?token=x",
        "http://localhost:8080/#x",
    ],
)
def test_url_validation_rejects_credentials_paths_and_non_http(control, url):
    with pytest.raises(ValueError):
        Connections.model_validate({**control.state.current.model_dump(), "generator_url": url})


def test_unapproved_destinations_are_never_contacted(control):
    draft = control.state.current.model_copy(update={"generator_url": "http://169.254.169.254"})
    control.supervisor.checker = Mock(side_effect=AssertionError("must not contact endpoint"))
    with pytest.raises(ValueError, match="Destination not authorized"):
        command(control, "check", connections=draft)
    with pytest.raises(ValueError, match="Destination not authorized"):
        command(control, "save", connections=draft)


def test_draft_check_does_not_save_or_replace_connections(control):
    before = control.snapshot()
    draft = control.state.current.model_copy(update={"generator_model": "other"})
    result = command(control, "check", connections=draft)
    assert len(result["checks"]) == 4
    assert control.snapshot() == before
    assert not control.store.path.exists()


def test_start_idempotency_ownership_stop_confirmation_and_save_guard(control):
    command(control, "start", service="generator")
    command(control, "start", service="generator")
    assert control.supervisor.launcher.calls == ["generator"]
    assert control.supervisor.has_owned()
    with pytest.raises(ValueError, match="Confirm stop"):
        command(control, "stop", service="generator")
    with pytest.raises(ConflictError, match="Stop managed"):
        command(control, "save", connections=control.state.current)
    command(control, "stop", service="generator", confirm_stop=True)
    assert control.supervisor.launcher.handles[0].stops == 1
    with pytest.raises(ValueError, match="not owned"):
        command(control, "stop", service="generator", confirm_stop=True)


def test_external_services_not_adopted_and_unready_port_blocks_preparation(control):
    control.supervisor.occupied = lambda _: True
    result = command(control, "prepare", mode="reranked")
    assert control.supervisor.launcher.calls == []
    assert len(result["services"]) == 1
    assert result["services"][0]["state"] == "external"
    assert not result["services"][0]["ready"]
    with pytest.raises(ValueError, match="not owned"):
        command(control, "stop", service="qdrant", confirm_stop=True)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("sparse", ["qdrant", "generator"]),
        ("dense", ["qdrant", "embeddings", "generator"]),
        ("hybrid", ["qdrant", "embeddings", "generator"]),
        ("reranked", ["qdrant", "embeddings", "reranker", "generator"]),
    ],
)
def test_prepare_order_depends_on_mode(control, mode, expected):
    control.supervisor.checker = available
    command(control, "prepare", mode=mode)
    assert control.supervisor.launcher.calls == expected


def test_prepare_stops_at_starting_dependency_and_gpu_guard(control):
    command(control, "prepare", mode="reranked")
    assert control.supervisor.launcher.calls == ["qdrant"]
    control.supervisor.profiles.services["reranker"].gpu_layers = 1
    command(control, "start", service="generator")
    with pytest.raises(ValueError, match="GPU model"):
        command(control, "start", service="reranker")


def test_remote_and_in_process_providers_cannot_launch(control):
    draft = control.state.current.model_copy(update={"generator_url": "http://192.168.1.25:8080"})
    control.allowed_origins.add(draft.generator_url)
    command(control, "save", connections=draft)
    with pytest.raises(ValueError, match="No matching local"):
        command(control, "start", service="generator")
    control.state.current.embedding_provider = "local"
    with pytest.raises(ValueError, match="No matching local"):
        command(control, "start", service="embeddings")


def test_exited_children_are_not_reused_and_shutdown_stops_only_owned(control):
    command(control, "start", service="generator")
    handle = control.supervisor.launcher.handles[0]
    handle.code = 3
    result = command(control, "get")
    assert not result["services"][-1]["owned"]
    assert any("code 3" in event for event in result["events"])
    command(control, "start", service="generator")
    control.supervisor.close()
    assert handle.stops == 0
    assert control.supervisor.launcher.handles[1].stops == 1


def test_auth_disabled_wrong_key_origin_and_arbitrary_commands(control):
    with TestClient(create_app(settings=AppConfig(), admin_token="")) as client:
        assert client.post("/v1/admin", json={"action": "get"}).status_code == 503
    with TestClient(create_app(runtime=control, admin_token=TOKEN)) as client:
        assert client.post("/v1/admin", json={"action": "get"}).status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        assert client.post("/v1/admin", headers=headers, json={"action": "get"}).status_code == 200
        assert (
            client.post(
                "/v1/admin",
                headers={**headers, "Origin": "http://evil.test"},
                json={"action": "get"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/v1/admin", headers=headers, json={"action": "start", "command": "anything"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                "/v1/admin",
                headers=headers,
                json={
                    "action": "save",
                    "revision": "stale",
                    "connections": control.state.current.model_dump(),
                },
            ).status_code
            == 409
        )
    with pytest.raises(ValueError, match="32 characters"):
        create_app(admin_token="short")


def test_lifespan_terminates_managed_children_and_log_does_not_include_key(control, caplog):
    with TestClient(create_app(runtime=control, admin_token=TOKEN)) as client:
        response = client.post(
            "/v1/admin",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={
                "action": "start",
                "service": "generator",
                "revision": control.state.revision,
            },
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-trace-id"]
        assert TOKEN not in response.text
    assert control.supervisor.launcher.handles[0].stops == 1
    assert TOKEN not in caplog.text


def test_store_lock_excludes_second_controller(control):
    second = SettingsStore(control.store.path)
    control.store.acquire()
    try:
        with pytest.raises(RuntimeError, match="one API worker"):
            second.acquire()
    finally:
        control.store.release()
    second.acquire()
    second.release()


def test_atomic_replace_failure_keeps_last_saved_file(control, monkeypatch):
    command(control, "save", connections=control.state.current)
    before = control.store.path.read_bytes()
    monkeypatch.setattr("taxguide.runtime.storage.os.replace", Mock(side_effect=OSError("disk")))
    with pytest.raises(OSError):
        command(control, "save", connections=control.state.current)
    assert control.store.path.read_bytes() == before
    assert not list(control.store.path.parent.glob(".connections-*"))


def test_query_uses_new_backend_after_admin_save(control, monkeypatch):
    from taxguide.generation.service import GroundedRagResult, GroundedRagStatus

    class Backend:
        def __init__(self, config):
            self.config = config

        def query(self, *args, **kwargs):
            return GroundedRagResult(
                status=GroundedRagStatus.CLARIFICATION_REQUIRED,
                clarification_questions=(self.config.generation.model,),
            )

    monkeypatch.setattr("taxguide.runtime.controller.ConfiguredBackend", Backend)
    changed = control.state.current.model_copy(update={"generator_model": "new-model"})
    with TestClient(create_app(runtime=control, admin_token=TOKEN)) as client:
        assert (
            client.post(
                "/v1/admin",
                headers={"Authorization": f"Bearer {TOKEN}"},
                json={
                    "action": "save",
                    "connections": changed.model_dump(),
                    "revision": control.state.revision,
                },
            ).status_code
            == 200
        )
        response = client.post("/v1/query", json={"question": "Tax question"})
    assert response.json()["clarification_questions"] == ["new-model"]


def test_docker_inspection_failure_does_not_hide_other_services(control):
    command(control, "start", service="qdrant")
    control.supervisor.handles["qdrant"].poll = Mock(
        side_effect=subprocess.CalledProcessError(1, "docker")
    )
    result = command(control, "get")
    assert len(result["services"]) == 4
    assert result["services"][0]["state"] == "error"
    assert result["services"][0]["owned"]


def test_model_alias_cannot_disguise_a_different_local_gguf(control, tmp_path):
    executable, model = tmp_path / "native.exe", tmp_path / "local.gguf"
    executable.touch()
    model.touch()
    profile = LaunchProfile(executable=executable, model_path=model, model_id="wrong-alias")
    with pytest.raises(ValueError, match="model_id"):
        LocalLauncher().start("generator", profile, control.state.current)


@pytest.mark.parametrize(
    "service,payload,ready",
    [
        ("generator", {"data": [{"id": "Qwen/Qwen3-4B-Instruct-2507"}]}, True),
        ("generator", {"data": [{"id": "wrong-model"}]}, False),
        ("embeddings", {"models": [{"name": "qwen3-embedding:0.6b"}]}, True),
        ("embeddings", {"models": []}, False),
        ("qdrant", {"result": {"status": "green", "points_count": 1}}, True),
        ("qdrant", {"result": {"status": "green", "points_count": 0}}, False),
        ("reranker", {"status": "ok"}, True),
    ],
)
def test_probes_read_only_and_check_configured_resources(control, service, payload, ready):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=payload)

    result = check(service, control.state.current, transport=httpx.MockTransport(respond))
    assert result.ready is ready
    assert all(request.method == "GET" for request in requests)
    assert len(requests) == 1


@pytest.mark.parametrize("status", [302, 401, 404, 503])
def test_probes_fail_closed_on_redirects_and_errors(control, status):
    result = check(
        "generator",
        control.state.current,
        transport=httpx.MockTransport(
            lambda _: httpx.Response(status, headers={"Location": "http://unapproved.test"})
        ),
    )
    assert not result.ready


def test_native_launcher_uses_fixed_argv_no_shell_and_existing_files(
    control, tmp_path, monkeypatch
):
    executable = tmp_path / "llama-server.exe"
    model = tmp_path / "model.gguf"
    executable.touch()
    model.touch()
    popen = Mock(return_value=Mock())
    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setenv("TAXGUIDE_ADMIN_TOKEN", "never-forward-this-secret")
    monkeypatch.setenv("LLAMA_ARG_HF_REPO", "must-not-download")
    profile = LaunchProfile(
        executable=executable,
        model_path=model,
        gpu_layers=10,
        model_id=control.state.current.generator_model,
    )
    LocalLauncher().start("generator", profile, control.state.current)
    args, kwargs = popen.call_args
    assert args[0][0] == str(executable)
    assert "--jinja" in args[0]
    assert "--host" in args[0] and "127.0.0.1" in args[0]
    assert kwargs["shell"] is False
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert "TAXGUIDE_ADMIN_TOKEN" not in kwargs["env"]
    assert "LLAMA_ARG_HF_REPO" not in kwargs["env"]
    profile.model_id = control.state.current.reranker_model
    LocalLauncher().start("reranker", profile, control.state.current)
    assert "--reranking" in popen.call_args.args[0]
    LocalLauncher().start("embeddings", profile, control.state.current)
    assert popen.call_args.args[0] == [str(executable), "serve"]
    assert popen.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "-1"
    assert popen.call_args.kwargs["env"]["GGML_VK_VISIBLE_DEVICES"] == "-1"
    assert popen.call_args.kwargs["env"]["OLLAMA_VULKAN"] == "0"


def test_native_launcher_refuses_remote_scripts_and_missing_models(control, tmp_path):
    launcher = LocalLauncher()
    script = tmp_path / "run.cmd"
    script.touch()
    profile = LaunchProfile(executable=script)
    with pytest.raises(ValueError, match="native executables"):
        launcher.start("generator", profile, control.state.current)
    profile.executable = tmp_path / "missing.exe"
    with pytest.raises(ValueError, match="existing absolute executable"):
        launcher.start("generator", profile, control.state.current)
    profile.executable.touch()
    with pytest.raises(ValueError, match="GGUF"):
        launcher.start("generator", profile, control.state.current)
    assert not local_endpoint("http://192.168.1.5:8080")
    assert not local_endpoint("https://localhost:8080")


def test_docker_ownership_is_lost_if_container_restarted_elsewhere(monkeypatch):
    monkeypatch.setattr(
        "taxguide.runtime.processes._docker_inspect",
        lambda *args: {
            "State": {"Running": True, "StartedAt": "different-instance"},
        },
    )
    run = Mock()
    monkeypatch.setattr("taxguide.runtime.processes._docker_run", run)
    handle = DockerHandle(["docker"], "container-id", "our-instance")
    handle.stop()
    assert handle.poll() == 0
    run.assert_not_called()


def test_native_stop_targets_only_live_owned_child(monkeypatch):
    process = Mock(pid=12345)
    process.poll.return_value = None
    run, killpg = Mock(), Mock()
    monkeypatch.setattr("taxguide.runtime.processes.sys.platform", "win32")
    monkeypatch.setattr("taxguide.runtime.processes._flags", lambda: 0)
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("taxguide.runtime.processes.os.killpg", killpg, raising=False)
    ChildHandle(process).stop()
    assert run.call_args.args[0] == ["taskkill.exe", "/PID", "12345", "/T", "/F"]
    assert run.call_args.kwargs["check"] is True
    assert run.call_args.kwargs["timeout"] == 10
    process.wait.assert_called_once_with(timeout=5)
    killpg.assert_not_called()
    run.reset_mock()
    process.poll.return_value = 0
    ChildHandle(process).stop()
    run.assert_not_called()


def test_native_stop_posix_escalates_only_own_process_group(monkeypatch):
    process = Mock(pid=12345)
    process.poll.return_value = None
    process.wait.side_effect = [subprocess.TimeoutExpired("owned-child", 5), 0]
    killpg = Mock()
    monkeypatch.setattr("taxguide.runtime.processes.sys.platform", "linux")
    monkeypatch.setattr("taxguide.runtime.processes.signal.SIGKILL", 9, raising=False)
    monkeypatch.setattr("taxguide.runtime.processes.os.killpg", killpg, raising=False)
    ChildHandle(process).stop()
    assert [call.args[0] for call in killpg.call_args_list] == [12345, 12345]
    assert process.wait.call_count == 2


def test_docker_launcher_starts_existing_local_container_without_create_pull_or_delete(
    control, tmp_path, monkeypatch
):
    executable = tmp_path / "docker.exe"
    executable.touch()
    info = {
        "Id": "owned-id",
        "State": {"Running": False, "StartedAt": "old"},
        "HostConfig": {"PortBindings": {"6333/tcp": [{"HostIp": "127.0.0.1", "HostPort": "6333"}]}},
    }
    calls = []

    def run(argv):
        calls.append(argv)
        if "start" in argv:
            info["State"] = {"Running": True, "StartedAt": "ours"}
            return "owned-id"
        return json.dumps([info])

    monkeypatch.setattr("taxguide.runtime.processes._docker_run", run)
    handle = LocalLauncher().start(
        "qdrant",
        LaunchProfile(executable=executable, container="trusted-qdrant"),
        control.state.current,
    )
    assert handle.poll() is None
    handle.stop()
    assert any("stop" in argv for argv in calls)
    assert all("--host" in argv for argv in calls)
    assert all(not {"run", "pull", "rm", "create"}.intersection(argv) for argv in calls)


@pytest.mark.parametrize("running,host_ip", [(True, "127.0.0.1"), (False, "0.0.0.0")])
def test_docker_launcher_rejects_external_or_public_container(
    control, tmp_path, monkeypatch, running, host_ip
):
    executable = tmp_path / "docker.exe"
    executable.touch()
    run = Mock(
        return_value=json.dumps(
            [
                {
                    "Id": "external-id",
                    "State": {"Running": running, "StartedAt": "old"},
                    "HostConfig": {
                        "PortBindings": {"6333/tcp": [{"HostIp": host_ip, "HostPort": "6333"}]}
                    },
                }
            ]
        )
    )
    monkeypatch.setattr("taxguide.runtime.processes._docker_run", run)
    with pytest.raises(ValueError):
        LocalLauncher().start(
            "qdrant",
            LaunchProfile(executable=executable, container="trusted-qdrant"),
            control.state.current,
        )
    assert all("inspect" in call.args[0] for call in run.call_args_list)
