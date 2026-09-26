"""Request-serialized ownership and readiness of backend-local services."""

from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from subprocess import SubprocessError
from threading import RLock

from taxguide.runtime.models import Connections, LocalProfiles, ServiceName, ServiceStatus
from taxguide.runtime.probes import Probe, probe
from taxguide.runtime.processes import Handle, Launcher, LocalLauncher, local_endpoint, port_open


class Supervisor:
    def __init__(
        self,
        profiles: LocalProfiles,
        *,
        launcher: Launcher | None = None,
        checker: Probe = probe,
        occupied: Callable[[str], bool] = port_open,
    ) -> None:
        self.profiles = profiles
        self.launcher = launcher or LocalLauncher()
        self.checker = checker
        self.occupied = occupied
        self.handles: dict[ServiceName, Handle] = {}
        self.events: deque[str] = deque(maxlen=20)
        self.lock = RLock()

    def _event(self, service: ServiceName, message: str) -> None:
        self.events.append(f"{datetime.now(UTC).isoformat()} {service}: {message}")

    def _owned(self, service: ServiceName) -> bool:
        handle = self.handles.get(service)
        if handle is None:
            return False
        result = handle.poll()
        if result is None:
            return True
        self._event(service, f"process exited or ownership ended (code {result})")
        del self.handles[service]
        return False

    def has_owned(self) -> bool:
        with self.lock:
            return any(self._owned(service) for service in list(self.handles))

    def can_start(self, service: ServiceName, connections: Connections) -> bool:
        if service not in self.profiles.services or not local_endpoint(connections.url(service)):
            return False
        return not (
            (service == "embeddings" and connections.embedding_provider != "ollama")
            or (service == "reranker" and connections.reranker_provider != "llamacpp")
        )

    def status(self, service: ServiceName, connections: Connections) -> ServiceStatus:
        with self.lock:
            try:
                owned = self._owned(service)
            except (OSError, RuntimeError, ValueError, SubprocessError):
                return ServiceStatus(
                    service=service,
                    url=connections.url(service),
                    state="error",
                    owned=True,
                    detail="Cannot inspect owned process; ownership retained, check runtime",
                )
            status = self.checker(service, connections)
            status.owned = owned
            status.can_start = self.can_start(service, connections)
            if owned and status.state == "unavailable":
                status.state = "starting"
                status.detail = (
                    "Process running, dependency not ready. "
                    "Check again; model or corpus may be missing"
                )
            elif not owned and local_endpoint(status.url) and self.occupied(status.url):
                status.state = "external"
                status.detail = f"Not owned by TaxGuide. {status.detail}"
            return status

    def start(self, service: ServiceName, connections: Connections) -> ServiceStatus:
        with self.lock:
            if self._owned(service):
                return self.status(service, connections)
            if not self.can_start(service, connections):
                raise ValueError(
                    "No matching local profile; remote and in-process services are not launched"
                )
            if self.occupied(connections.url(service)):
                return self.status(service, connections)
            profile = self.profiles.services[service]
            if profile.gpu_layers > 0:
                for other in list(self.handles):
                    if self._owned(other) and self.profiles.services[other].gpu_layers > 0:
                        raise ValueError(
                            "Another managed GPU model is running; stop it before starting this one"
                        )
            try:
                self.handles[service] = self.launcher.start(service, profile, connections)
            except (OSError, RuntimeError, ValueError, SubprocessError) as exc:
                self._event(service, "start failed; check binary, model, container and port")
                raise ValueError(
                    "Start failed; check the operator launch profile and local prerequisites"
                ) from exc
            self._event(service, "started by TaxGuide")
            return self.status(service, connections)

    def stop(self, service: ServiceName, connections: Connections) -> ServiceStatus:
        with self.lock:
            if not self._owned(service):
                raise ValueError(
                    "This service is not owned by this TaxGuide process; stop it manually"
                )
            self.handles[service].stop()
            del self.handles[service]
            self._event(service, "stopped by TaxGuide")
            return ServiceStatus(
                service=service,
                url=connections.url(service),
                state="stopped",
                can_start=self.can_start(service, connections),
            )

    def close(self) -> None:
        with self.lock:
            for service in list(self.handles):
                try:
                    if self._owned(service):
                        self.handles[service].stop()
                except (OSError, RuntimeError, ValueError, SubprocessError):
                    self._event(service, "shutdown failed; manual inspection required")
