"""Opt-in live smoke test for the complete grounded answer path."""

import os
from pathlib import Path
from typing import cast

import pytest

from taxguide.cli.answer import build_grounded_service
from taxguide.config.loader import load_config
from taxguide.generation.service import GroundedRagStatus
from taxguide.retrieval.factory import RetrievalMode

pytestmark = pytest.mark.generation_eval


@pytest.mark.skipif(
    os.getenv("TAXGUIDE_RUN_GENERATION_EVAL") != "1",
    reason="set TAXGUIDE_RUN_GENERATION_EVAL=1",
)
def test_live_grounded_answer() -> None:
    settings = load_config(Path("configs/base.yaml"))
    mode = os.getenv("TAXGUIDE_GENERATION_EVAL_MODE", "reranked")
    if mode not in {"dense", "sparse", "hybrid", "reranked"}:
        raise ValueError("TAXGUIDE_GENERATION_EVAL_MODE is invalid")
    question = os.getenv(
        "TAXGUIDE_GENERATION_EVAL_QUESTION",
        "What does Skatteetaten say about wealth tax for 2025?",
    )
    service = build_grounded_service(
        settings,
        mode=cast(RetrievalMode, mode),
        candidate_limit=settings.retrieval.candidate_limit,
    )

    result = service.answer(question, retrieval_limit=5)

    print(result.model_dump_json(indent=2))
    assert result.status in {GroundedRagStatus.ANSWERED, GroundedRagStatus.ABSTAINED}
    assert result.generator_model == settings.generation.model
