# Private v1 readiness checklist

This is an operator checklist, not a claim that the current checkout has passed a production
release. The API and query endpoints are unauthenticated; use only loopback/private networking.

## Milestone status

| Issue | Current evidence | Remaining gate |
| --- | --- | --- |
| #79–#81 | PII-minimized app logs, conservative injection check, threat model and tests | Model/proxy logs and adversarial semantic review are separate |
| #82 | Retrieval and optional per-case generation artifact comparison with deterministic tests | Reviewed real-case inputs belong to #86 |
| #83 | GitHub Actions checks Python, browser and Compose syntax | Hosted workflow result after push |
| #84 | Dockerfiles and private Compose configuration | Build and live container smoke test on an active Docker daemon |
| #85, #87 | Current technical runbooks, demo script and architecture diagram | Keep synchronized as functionality changes |
| #86 | Preliminary checked-in 30-query retrieval gold set; opt-in harness | Live services, reviewed corpus, saved measurements and human release decision |

## Build and deploy

The existing `compose.yaml` runs Qdrant alone. To add API and frontend on one private host:

```powershell
docker compose -f compose.yaml -f compose.production.yaml config --quiet
docker compose -f compose.yaml -f compose.production.yaml up -d --build
Invoke-RestMethod http://127.0.0.1:8000/v1/health
```

Open `http://127.0.0.1:3000`. The API and UI publish only to loopback. Configure the generator
URL in `configs/base.yaml` or an operator-owned overlay before startup. `configs/container.yaml`
resolves Qdrant by Compose service name and Ollama/reranker on the Docker host via
`host.docker.internal`; check actual reachability from the container. The sample base generator
address is machine-specific. Qdrant data and crawl artifacts are bind-mounted under `data/`;
back them up before upgrades. No models are downloaded or launched by Compose. `/v1/health` only
proves API liveness; a real query is required to prove dependency readiness. Docker Desktop
must be running. The frontend is a production build, but this is still a private deployment.

For the existing desktop + laptop + Oracle split, use
[the three-machine runbook](three-machine-deployment.md). Do not copy the single-host URLs to
other machines without checking routing and firewall policy.

## Release evidence

1. Run `uv run pytest`, Ruff check/format, `uv run mypy src`, frontend typecheck/build/Playwright
   and review the GitHub Actions result. CI uses deterministic doubles, not real models.
2. Freeze commit, crawl manifests, indexed collection, source years, model names/quantizations,
   runtime versions and hardware/driver details. Review gold-set judgments against official
   sources, including annual applicability; exclude personal information.
3. Run the opt-in live retrieval benchmark for all four modes against the frozen collection,
   saving `TAXGUIDE_RETRIEVAL_EVAL_REPORT`. Do not infer quality from the synthetic fixtures.
4. Compare it with a **reviewed artifact for the same gold-set version**:

   ```powershell
   uv run taxguide evaluation regression --baseline path/to/baseline.json --candidate path/to/candidate.json
   ```

   Defaults allow at most a 0.05 absolute drop in Recall@5 or nDCG@5 and a 1.5× mean-latency
   increase for each pipeline. These are exploratory tolerances, not approved tax-safety targets.
   Missing/mismatched artifacts fail the gate. Inspect individual query failures as well.
   If reviewed generation reports exist, pass `--generation-baseline path/to/old.json`
   and `--generation-candidate path/to/new.json` in the same command. The gate checks matched
   cases and score/abstention declines; it does not produce semantic judgments.
5. Run the live grounded-answer smoke test, then perform a reviewed generation-quality study
   (faithfulness, citation correctness, abstention, numerical/year accuracy and injection cases).
   The current smoke test is **not** that study. Record pass/fail and human sign-off.
6. Rehearse backup/restore and Qdrant candidate promotion/rollback. Verify access controls,
   firewall, TLS/authenticated gateway if exposed beyond the private workstation, and independent
   logs of the model servers and proxy.

No production-quality corpus/generation baseline or release approval is committed. If any of
these artifacts or services is missing, mark the release **not ready** rather than bypassing the
gate. See [retrieval](retrieval.md), [generation](generation.md) and
[the threat model](threat-model.md).
