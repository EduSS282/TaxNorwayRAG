import { expect, test } from "@playwright/test";

const key = "test-only-corpus-administration-0123456789";
const report = {
  run_id: "report-one", selected: 2, processed: 2, unchanged: 0, failed: 0,
  chunks_generated: 4, indexing_enabled: true, vector_collection: "demo-candidate",
  documents_by_tax_year: { "2025": 2 }, stage_seconds: { embedding: 1.2 },
  failure_categories: {},
};
const job = {
  id: "build-one", state: "running", selected: 2, processed: 0, unchanged: 0,
  failed: 0, index: true, collection: "demo-candidate", embedding_model: "demo-embedding",
  revision: "revision-one", detail: "", report: null as typeof report | null,
};
const view = {
  revision: "revision-one", collection: "demo-candidate", embedding_model: "demo-embedding",
  chunk_strategy: "structural", max_tokens: 512,
  selection: null as Record<string, number> | null, job: null as typeof job | null,
};

test("preview, explicit Qdrant writes, polling, report download and locking", async ({ page }) => {
  const commands: Record<string, unknown>[] = [];
  let started = false;
  await page.route("**/api/crawl", (route) => route.fulfill({
    json: { sections: [], invalid_manifests: 0, job: null },
  }));
  await page.route("**/api/corpus", (route) => {
    expect(route.request().headers().authorization).toBe(`Bearer ${key}`);
    const command = route.request().postDataJSON();
    commands.push(command);
    if (command.action === "start") started = true;
    return route.fulfill({ json: {
      ...view,
      selection: command.action === "preview"
        ? { scanned: 3, selected: 2, excluded_limit: 1, excluded_duplicate: 0 } : null,
      job: command.action === "start" ? job : started
        ? { ...job, state: "completed", processed: 2, report } : null,
    } });
  });
  await page.goto("/crawler");
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  expect(commands).toHaveLength(0);
  await page.getByRole("button", { name: "Actualizar preparación" }).click();
  await expect(page.getByRole("button", { name: "Construir e indexar" })).toBeDisabled();
  await page.getByLabel("Prefijo de ruta oficial").fill("/en/rates/");
  await page.getByLabel("Máximo de documentos", { exact: true }).fill("2");
  await page.getByRole("button", { name: "Revisar selección" }).click();
  await expect(page.getByText(/Seleccionadas: 2/)).toBeVisible();
  await page.getByLabel(/Confirmo escribir vectores/).check();
  await page.getByRole("button", { name: "Construir e indexar" }).click();
  expect(commands.find((command) => command.action === "start")).toMatchObject({
    revision: "revision-one", url_prefix: "/en/rates/", language: "en", limit: 2,
    index: true, confirm_index: true,
  });
  await expect(page.getByLabel("Progreso de preparación")).toContainText("Finalizado");
  await expect(page.getByText(/Chunks generados: 4/)).toBeVisible();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Descargar informe de preparación" }).click();
  expect((await downloaded).suggestedFilename()).toBe("corpus-build-one.json");
  expect(await page.evaluate(() => localStorage.length + sessionStorage.length)).toBe(0);
  await page.getByRole("button", { name: "Bloquear panel" }).click();
  await expect(page.getByRole("button", { name: "Actualizar preparación" })).toHaveCount(0);
});

test("active work recovery, cancellation, errors and mobile layout", async ({ page }) => {
  let current = { ...job };
  let reject = false;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/crawl", (route) => route.fulfill({
    json: { sections: [], invalid_manifests: 0, job: null },
  }));
  await page.route("**/api/corpus", (route) => {
    const command = route.request().postDataJSON();
    if (reject) return route.fulfill({ status: 409, json: { detail: "Connections changed" } });
    if (command.action === "cancel") {
      expect(command.job_id).toBe(job.id);
      current = { ...current, state: "cancelled" };
    }
    return route.fulfill({ json: { ...view, job: current } });
  });
  await page.goto("/crawler");
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await page.getByRole("button", { name: "Actualizar preparación" }).click();
  await expect(page.getByLabel("Prefijo de ruta oficial")).toBeDisabled();
  await page.getByRole("button", { name: "Cancelar preparación" }).click();
  await expect(page.getByLabel("Progreso de preparación")).toContainText("Cancelado");
  reject = true;
  await page.getByRole("button", { name: "Revisar selección" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText("Connections changed");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("corpus proxy isolates credentials and rejects foreign origins", async ({ request }) => {
  const result = await request.post("/api/corpus", {
    headers: { Authorization: `Bearer ${key}`, Cookie: "secret=value" },
    data: { action: "get" },
  });
  expect(result.status()).toBe(200);
  expect(result.headers()["cache-control"]).toBe("no-store");
  expect(await result.json()).toEqual({ authorization: `Bearer ${key}`, cookie: null, origin: null });
  const rejected = await request.post("/api/corpus", {
    headers: { Origin: "https://foreign.test", Authorization: `Bearer ${key}` },
    data: { action: "start" },
  });
  expect(rejected.status()).toBe(403);
});
