"""Authenticated operator-only endpoint, disabled unless explicitly configured."""

from secrets import compare_digest
from subprocess import SubprocessError

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from taxguide.runtime.controller import AdminRequest, ConflictError, RuntimeController


def admin_router(controller: RuntimeController | None, token: str | None) -> APIRouter:
    router = APIRouter()

    def authorize(request: Request) -> None:
        if controller is None or not token:
            raise HTTPException(
                503, "Administration disabled; configure TAXGUIDE_ADMIN_TOKEN on the API host"
            )
        # The same-origin Next proxy strips Origin; direct browser mutations are forbidden.
        if request.headers.get("origin"):
            raise HTTPException(403, "Use the same-origin administration proxy")
        supplied = request.headers.get("authorization", "")
        if not compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "Invalid administration key")

    @router.post("/v1/admin", dependencies=[Depends(authorize)])
    def manage(payload: AdminRequest, response: Response) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        assert controller is not None
        try:
            return controller.execute(payload)
        except ConflictError as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except (OSError, RuntimeError, SubprocessError) as exc:
            raise HTTPException(
                503, "Local operation failed; verify files, processes and permissions"
            ) from exc

    return router
