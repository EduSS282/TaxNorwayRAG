import asyncio

import httpx

from taxguide.reranking.service import create_app


class FakeCrossEncoder:
    def predict(self, sentences: list[tuple[str, str]], *, show_progress_bar: bool) -> list[float]:
        assert show_progress_bar is False
        return [-8.9375 for _ in sentences]


def test_service_loads_model_once_and_returns_raw_negative_logits() -> None:
    loaded: list[str] = []
    app = create_app(
        "configured-model",
        model_factory=lambda model_id: loaded.append(model_id) or FakeCrossEncoder(),
    )

    async def exercise_service() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            health = await client.get("/health")
            response = await client.post(
                "/rerank", json={"query": "deadline", "documents": ["first", "second"]}
            )
        return health, response

    health, response = asyncio.run(exercise_service())

    assert health.json() == {"status": "ok", "model": "configured-model"}
    assert response.status_code == 200
    assert response.json() == {"scores": [-8.9375, -8.9375]}
    assert loaded == ["configured-model"]


def test_service_rejects_malformed_requests() -> None:
    app = create_app(model_factory=lambda _: FakeCrossEncoder())

    async def exercise_service() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post("/rerank", json={"query": "", "documents": []})

    response = asyncio.run(exercise_service())

    assert response.status_code == 422
