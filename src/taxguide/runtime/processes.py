"""Fixed argument launchers. Only handles created here can be stopped here."""

import json
import os
import signal
import socket
import subprocess
import sys
from typing import Any, Protocol, cast
from urllib.parse import urlsplit

from taxguide.runtime.models import Connections, LaunchProfile, ServiceName


class Handle(Protocol):
    def poll(self) -> int | None: ...
    def stop(self) -> None: ...


class Launcher(Protocol):
    def start(
        self, service: ServiceName, profile: LaunchProfile, connections: Connections
    ) -> Handle: ...


def local_endpoint(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}


def port_open(url: str) -> bool:
    parsed = urlsplit(url)
    try:
        with socket.create_connection(
            (parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=0.3
        ):
            return True
    except OSError:
        return False


def _flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


class ChildHandle:
    def __init__(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process

    def poll(self) -> int | None:
        return self.process.poll()

    def stop(self) -> None:
        if self.poll() is not None:
            return
        if sys.platform == "win32":
            # Known, still-live child only. Never look up or adopt a PID from the network.
            subprocess.run(
                ["taskkill.exe", "/PID", str(self.process.pid), "/T", "/F"],
                check=True,
                timeout=10,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_flags(),
            )
        else:
            os.killpg(self.process.pid, signal.SIGTERM)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if sys.platform != "win32":
                os.killpg(self.process.pid, signal.SIGKILL)
            else:
                self.process.kill()
            self.process.wait(timeout=5)


class DockerHandle:
    def __init__(self, command: list[str], container_id: str, started_at: str) -> None:
        self.command = command
        self.container_id = container_id
        self.started_at = started_at

    def poll(self) -> int | None:
        info = _docker_inspect(self.command, self.container_id)
        state = info["State"]
        # Another actor restarting the same container revokes our ownership.
        return None if state["Running"] and state["StartedAt"] == self.started_at else 0

    def stop(self) -> None:
        if self.poll() is None:
            _docker_run([*self.command, "stop", "--time", "5", self.container_id])


def _docker_run(command: list[str]) -> str:
    result = subprocess.run(
        command, check=True, capture_output=True, text=True, timeout=15, creationflags=_flags()
    )
    return result.stdout


def _docker_inspect(command: list[str], container: str) -> dict[str, Any]:
    value = json.loads(_docker_run([*command, "inspect", container]))
    if not isinstance(value, list) or not value or not isinstance(value[0], dict):
        raise ValueError("Docker returned invalid container metadata")
    return cast(dict[str, Any], value[0])


class LocalLauncher:
    def start(
        self, service: ServiceName, profile: LaunchProfile, connections: Connections
    ) -> Handle:
        url = connections.url(service)
        if not local_endpoint(url):
            raise ValueError("Only loopback HTTP services can be started on the API host")
        executable = profile.executable
        if not executable.is_absolute() or not executable.is_file():
            raise ValueError("Configure an existing absolute executable path in the local profile")
        if executable.suffix.lower() in {".bat", ".cmd", ".ps1", ".py", ".sh"}:
            raise ValueError("Launch profiles must refer to native executables, not scripts")
        parsed = urlsplit(url)
        host = "::1" if parsed.hostname == "::1" else "127.0.0.1"
        port = parsed.port or 80
        if service == "qdrant":
            # Explicit local Docker transport; ignore remote Docker contexts / DOCKER_HOST.
            daemon = (
                "npipe:////./pipe/docker_engine"
                if sys.platform == "win32"
                else "unix:///var/run/docker.sock"
            )
            command = [str(executable), "--host", daemon]
            if not profile.container:
                raise ValueError("Configure an existing stopped Qdrant container")
            info = _docker_inspect(command, profile.container)
            if info["State"]["Running"]:
                raise ValueError("Container already running; it will not be adopted")
            bindings = info["HostConfig"].get("PortBindings") or {}
            rest = bindings.get("6333/tcp") or []
            if not any(item["HostIp"] == host and item["HostPort"] == str(port) for item in rest):
                raise ValueError(
                    "Qdrant container port must match the configured loopback endpoint"
                )
            if any(
                item["HostIp"] not in {"127.0.0.1", "::1"}
                for items in bindings.values()
                for item in (items or [])
            ):
                raise ValueError("Managed Qdrant container ports must all bind to loopback")
            container_id = info["Id"]
            _docker_run([*command, "start", container_id])
            started = _docker_inspect(command, container_id)
            return DockerHandle(command, container_id, started["State"]["StartedAt"])
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("TAXGUIDE_", "LLAMA_ARG_"))
        }
        if service == "embeddings":
            if connections.embedding_provider != "ollama":
                raise ValueError("Only the Ollama embedding provider has a managed process")
            command = [str(executable), "serve"]
            environment["OLLAMA_HOST"] = url
            # Conservative CPU-only default for managed embeddings; do not compete for 6 GB VRAM.
            environment["CUDA_VISIBLE_DEVICES"] = "-1"
            environment["HIP_VISIBLE_DEVICES"] = "-1"
            environment["ROCR_VISIBLE_DEVICES"] = "-1"
            environment["OLLAMA_VULKAN"] = "0"
            environment["GGML_VK_VISIBLE_DEVICES"] = "-1"
            environment["OLLAMA_NUM_PARALLEL"] = "1"
            environment["OLLAMA_MAX_LOADED_MODELS"] = "1"
        else:
            if service == "reranker" and connections.reranker_provider != "llamacpp":
                raise ValueError("Only llama.cpp reranking has a managed process")
            model = profile.model_path
            if (
                model is None
                or not model.is_absolute()
                or not model.is_file()
                or model.suffix.lower() != ".gguf"
            ):
                raise ValueError(
                    "Configure an existing absolute GGUF model path; downloads are manual"
                )
            alias = (
                connections.generator_model
                if service == "generator"
                else connections.reranker_model
            )
            if profile.model_id != alias:
                raise ValueError("Saved model must match the model_id of the trusted GGUF profile")
            command = [
                str(executable),
                "-m",
                str(model),
                "--alias",
                alias,
                "--host",
                host,
                "--port",
                str(port),
                "-c",
                str(profile.context_size),
                "-ngl",
                str(profile.gpu_layers),
                "--parallel",
                "1",
            ]
            command += ["--jinja"] if service == "generator" else ["--reranking"]
        process = subprocess.Popen(
            command,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=_flags(),
            start_new_session=sys.platform != "win32",
        )
        return ChildHandle(process)
