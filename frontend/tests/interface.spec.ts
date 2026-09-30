import { expect, test } from "@playwright/test";

test("question, year and language cross the proxy; citations and final context render", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await page.getByLabel("Language", { exact: true }).selectOption("es");
  await expect(page.locator("html")).toHaveAttribute("lang", "es");
  await page.getByLabel("Tu pregunta fiscal").fill("Pregunta fiscal");
  await page.getByLabel("Año fiscal", { exact: true }).fill("2025");
  await page
    .getByText("Inspector de retrieval para desarrolladores", { exact: true })
    .click();
  await page.getByLabel("Incluir contexto final en la respuesta").check();
  const request = page.waitForRequest("**/api/query");
  await page.getByRole("button", { name: "Buscar respuesta" }).click();
  expect((await request).postDataJSON()).toMatchObject({
    tax_year: 2025,
    response_language: "es",
    include_context: true,
  });
  await expect(
    page.getByText("Test answer in es. [S1]", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Official tax source" }),
  ).toHaveAttribute("href", "https://www.skatteetaten.no/en/taxes/");
  await page
    .getByText("Contexto final seleccionado para esta respuesta", {
      exact: true,
    })
    .click();
  await page
    .getByText("#1 · 0.9000 · Official tax source", { exact: true })
    .click();
  await expect(
    page.getByText("Exact official evidence.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Comparar retrieval" }).click();
  for (const stage of ["dense", "sparse", "fused", "reranked"])
    await expect(
      page.getByRole("heading", { name: `${stage} (1)`, exact: true }),
    ).toBeVisible();
  await expect(
    page.getByText("Test answer in es. [S1]", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/Trace: answer-trace/)).toBeVisible();
  await expect(
    page.getByText("Trace: retrieval-trace", { exact: true }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

for (const [question, output] of [
  ["clarify", "More information needed"],
  ["abstain", "Insufficient evidence"],
  ["unavailable", "Service unavailable"],
]) {
  test(`renders ${question} without invented citations`, async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("Your tax question").fill(question);
    await page.getByRole("button", { name: "Find an answer" }).click();
    await expect(page.getByText(output, { exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Sources cited in the answer" }),
    ).toHaveCount(0);
  });
}

test("empty comparison, validation, loading and stale-result clearing", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("button", { name: "Find an answer" }),
  ).toBeDisabled();
  await page.getByLabel("Your tax question").fill("slow");
  await page.getByLabel("Tax year", { exact: true }).fill("2101");
  await page.getByRole("button", { name: "Find an answer" }).click();
  await expect(page.locator("#year:invalid")).toHaveCount(1);
  await page.getByLabel("Tax year", { exact: true }).fill("2025");
  await page.getByRole("button", { name: "Find an answer" }).click();
  await expect(page.getByRole("status")).toHaveText("Working…");
  await expect(page.getByLabel("Your tax question")).toBeDisabled();
  await expect(
    page.getByText("Test answer in en. [S1]", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Your tax question").fill("empty");
  await expect(
    page.getByText("Test answer in en. [S1]", { exact: true }),
  ).toHaveCount(0);
  await page
    .getByText("Developer retrieval inspector", { exact: true })
    .click();
  await page.getByRole("button", { name: "Compare retrieval" }).click();
  await expect(
    page.getByText("No evidence returned.", { exact: true }),
  ).toHaveCount(4);
});

test("unsafe source URLs never become clickable; mobile fits viewport", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("Your tax question").fill("unsafe");
  await page.getByRole("button", { name: "Find an answer" }).click();
  await expect(
    page.getByText("Evidence-based answer", { exact: true }),
  ).toBeVisible();
  await expect(page.locator('a[href^="javascript:"]')).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});

test("proxy allowlist, input guards, upstream status and trace preservation", async ({
  request,
}) => {
  const response = await request.post("/api/query", {
    data: { question: "echo", tax_year: 2025, response_language: "nb" },
    headers: { Cookie: "secret=do-not-forward" },
  });
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({
    payload: { question: "echo", tax_year: 2025, response_language: "nb" },
    cookie: null,
    authorization: null,
  });
  expect(response.headers()["x-trace-id"]).toBe("answer-trace");
  expect(response.headers()["cache-control"]).toBe("no-store");
  expect((await request.post("/api/metrics", { data: {} })).status()).toBe(404);
  expect(
    (
      await request.post("/api/query", {
        data: {},
        headers: { Origin: "https://evil.example" },
      })
    ).status(),
  ).toBe(403);
  expect((await request.post("/api/query", { data: "no-json" })).status()).toBe(
    415,
  );
  expect(
    (
      await request.post("/api/query", {
        data: Buffer.from("{"),
        headers: { "Content-Type": "application/json" },
      })
    ).status(),
  ).toBe(400);
  expect(
    (
      await request.post("/api/query", {
        data: { question: "x".repeat(33000) },
      })
    ).status(),
  ).toBe(413);
  expect(
    (
      await request.post("/api/query", { data: { question: "unavailable" } })
    ).status(),
  ).toBe(503);
  expect(
    (
      await request.post("/api/query", { data: { question: "bad-json" } })
    ).status(),
  ).toBe(502);
});
