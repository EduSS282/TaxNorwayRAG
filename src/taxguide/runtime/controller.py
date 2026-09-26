"""Atomic connection replacement and explicit local lifecycle operations."""

import os
from pathlib import Path
from subprocess import SubprocessError
from threading import RLock
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import Field

from taxguide.api.backend import ApiBackend, ConfiguredBackend
from taxguide.config.models import AppConfig, ConfigModel
from taxguide.runtime.models import (
    SERVICES,
    Connections,
    LocalProfiles,
    SavedConnections,
    ServiceName,
    ServiceStatus,
    endpoint,
)
from taxguide.runtime.storage import SettingsStore
from taxguide.runtime.supervisor import Supervisor


class ConflictError(ValueError):
    """An operator must refresh or stop owned services before retrying."""


class AdminRequest(ConfigModel):
    action: Literal["get", "save", "restore", "check", "start", "stop", "prepare"]
    connections: Connections | None = None
    revision: str | None = Field(default=None, max_length=64)
    service: ServiceName | None = None
    mode: Literal["dense", "sparse", "hybrid", "reranked"] = "dense"
    confirm_reindex: bool = False
    confirm_stop: bool = False


class RuntimeController:
    def __init__(
        self,
        base: AppConfig,
        store: SettingsStore,
        supervisor: Supervisor,
        *,
        allowed_origins: set[str] | None = None,
    ) -> None:
        self.base = base
        self.store = store
        self.supervisor = supervisor
        self.lock = RLock()
        initial = Connections.from_config(base)
        self.allowed_origins = allowed_origins or {initial.url(service) for service in SERVICES}
        self.state = store.read() or SavedConnections(current=initial, revision=uuid4().hex)
        self.validate_destinations(self.state.current)
        self._config = self.state.current.apply(base)
        self._backend: ApiBackend = ConfiguredBackend(self._config)
        self.statuses: dict[ServiceName, ServiceStatus] = {}

    def snapshot(self) -> tuple[AppConfig, ApiBackend]:
        with self.lock:
            return self._config, self._backend

    def validate_destinations(self, connections: Connections) -> None:
        for service in SERVICES:
            if connections.url(service) not in self.allowed_origins:
                raise ValueError(
                    "Destination not authorized; add its exact origin to "
                    "TAXGUIDE_SERVICE_ORIGINS on the API host"
                )

    def view(self) -> dict[str, object]:
        return {
            "connections": self.state.current.model_dump(),
            "revision": self.state.revision,
            "can_restore": self.state.previous is not None,
            "allowed_origins": sorted(self.allowed_origins),
            "local_services": [
                service
                for service in SERVICES
                if self.supervisor.can_start(service, self.state.current)
            ],
            "services": [item.model_dump() for item in self.statuses.values()],
            "events": list(self.supervisor.events),
        }

    def _replace(self, connections: Connections, request: AdminRequest) -> None:
        if request.revision != self.state.revision:
            raise ConflictError("Configuration changed; reload before saving or restoring")
        if self.supervisor.has_owned():
            raise ConflictError("Stop managed services before changing connections")
        self.validate_destinations(connections)
        previous = self.state.current
        embedding_changed = (connections.embedding_provider, connections.embedding_model) != (
            previous.embedding_provider,
            previous.embedding_model,
        )
        if embedding_changed and (
            not request.confirm_reindex
            or connections.qdrant_collection == previous.qdrant_collection
        ):
            raise ValueError(
                "Changing embedding model/provider requires a different collection "
                "and explicit reindex acknowledgement"
            )
        new_config = connections.apply(self.base)
        new_backend = ConfiguredBackend(new_config)
        new_state = SavedConnections(current=connections, previous=previous, revision=uuid4().hex)
        self.store.write(new_state)  # Publish only after durable, atomic persistence succeeds.
        self.state, self._config, self._backend = new_state, new_config, new_backend
        self.statuses.clear()

    def execute(self, request: AdminRequest) -> dict[str, object]:
        with self.lock:
            if request.action == "save":
                if request.connections is None:
                    raise ValueError("Connections are required")
                self._replace(request.connections, request)
            elif request.action == "restore":
                if self.state.previous is None:
                    raise ValueError("No previous configuration saved")
                self._replace(self.state.previous, request)
            elif request.action == "check":
                draft = request.connections or self.state.current
                self.validate_destinations(draft)
                # Draft checks do not replace cached status of the active settings.
                checks = [
                    self.supervisor.checker(service, draft).model_dump() for service in SERVICES
                ]
                return {**self.view(), "checks": checks}
            elif request.action in {"start", "stop"}:
                if request.revision != self.state.revision:
                    raise ConflictError("Configuration changed; reload before operating services")
                if request.service is None:
                    raise ValueError("Service is required")
                if request.action == "stop" and not request.confirm_stop:
                    raise ValueError("Confirm stop; active queries may fail")
                operation = (
                    self.supervisor.start if request.action == "start" else self.supervisor.stop
                )
                self.statuses[request.service] = operation(request.service, self.state.current)
            elif request.action == "prepare":
                if request.revision != self.state.revision:
                    raise ConflictError("Configuration changed; reload before preparing services")
                needed: list[ServiceName] = ["qdrant"]
                if request.mode != "sparse":
                    needed.append("embeddings")
                if request.mode == "reranked":
                    needed.append("reranker")
                needed.append("generator")
                for service in needed:
                    try:
                        if self.supervisor.can_start(service, self.state.current):
                            status = self.supervisor.start(service, self.state.current)
                        else:
                            status = self.supervisor.status(service, self.state.current)
                    except (OSError, RuntimeError, ValueError, SubprocessError):
                        status = ServiceStatus(
                            service=service,
                            url=self.state.current.url(service),
                            state="error",
                            detail="Cannot prepare service; check profile and GPU budget",
                        )
                    self.statuses[service] = status
                    # Never continue loading models after a dependency fails/is still starting.
                    if not status.ready and status.state != "in_process":
                        break
            elif request.action == "get":
                # Explicit refresh only: no polling, model loading or automatic start.
                self.statuses = {
                    service: self.supervisor.status(service, self.state.current)
                    for service in SERVICES
                }
            return self.view()


def from_environment(config: AppConfig) -> RuntimeController:
    name = os.environ.get("TAXGUIDE_LOCAL_SERVICES")
    profiles = (
        LocalProfiles.model_validate(yaml.safe_load(Path(name).read_text(encoding="utf-8")))
        if name
        else LocalProfiles()
    )
    initial = Connections.from_config(config)
    allowed = {initial.url(service) for service in SERVICES}
    allowed.update(
        endpoint(value.strip())
        for value in os.environ.get("TAXGUIDE_SERVICE_ORIGINS", "").split(",")
        if value.strip()
    )
    store = SettingsStore(
        Path(os.environ.get("TAXGUIDE_CONNECTIONS_FILE", "data/runtime/connections.json"))
    )
    return RuntimeController(config, store, Supervisor(profiles), allowed_origins=allowed)
