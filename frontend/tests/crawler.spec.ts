import { expect, test } from "@playwright/test";

const key = "test-only-crawler-administration-0123456789";
const sections = [
  {
    id: "rates",
    title: "Tarifas",
    url: "https://www.skatteetaten.no/en/rates/",
    languages: ["en"],
    downloaded: 3,
    unavailable: 1,
    years: { "2025": 2, unknown: 1 },
    last_download: "2026-09-27T12:00:00Z",
  },
  {
    id: "gifts",
    title: "Donaciones",
    url: "https://www.skatteetaten.no/en/person/taxes/get-the-taxes-right/gift-and-inheritance/",
    languages: ["en"],
    downloaded: 0,
    unavailable: 0,
    years: {},
    last_download: null,
  },
];
function job(state: string) {
  return {
    id: "test-job",
    state,
    max_pages: 12,
    max_depth: 1,
    years: [2025, 2026],
    started_at: "2026-09-27T12:00:00Z",
    finished_at: null,
    detail: "",
    sections: [
      {
        source_id: "gifts",
        state: state === "cancelling" ? "running" : state,
        fetched: 1,
        failed: 0,
        skipped: 0,
        new: 1,
        changed: 0,
        unchanged: 0,
      },
    ],
  };
}

test("catalog selection, bounded start, progress, cancellation and key clearing", async ({
  page,
}) => {
  const commands: Record<string, unknown>[] = [];
  let current: ReturnType<typeof job> | null = null;
  await page.route("**/api/crawl", async (route) => {
    expect(route.request().headers().authorization).toBe(`Bearer ${key}`);
    const command = route.request().postDataJSON();
    commands.push(command);
    if (command.action === "start") current = job("running");
    if (command.action === "cancel") {
      expect(command.job_id).toBe("test-job");
      current = job("cancelled");
    }
    await route.fulfill({
      json: {
        sections: command.action === "get" ? sections : null,
        invalid_manifests: 1,
        job: current,
      },
    });
  });
  await page.goto("/crawler");
  expect(commands).toHaveLength(0);
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await expect(page.getByText("3 páginas descargadas")).toBeVisible();
  await expect(page.getByText(/2025 \(2\)/)).toBeVisible();
  await expect(page.getByText(/1 manifiestos inválidos/)).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Descargar 0/ }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Seleccionar sin descargas" }).click();
  await expect(page.getByLabel("Tarifas", { exact: true })).not.toBeChecked();
  await expect(page.getByLabel("Donaciones", { exact: true })).toBeChecked();
  await page.getByLabel("Máximo de páginas por sección").fill("12");
  await page.getByLabel("Profundidad de enlaces").fill("1");
  await page.getByLabel("Años de tarifas", { exact: false }).fill("2025, 2026");
  await page.getByRole("button", { name: /Descargar 1/ }).click();
  await expect(
    page.getByRole("heading", { name: "Último trabajo: Descargando" }),
  ).toBeVisible();
  expect(commands.find((command) => command.action === "start")).toEqual({
    action: "start",
    sources: ["gifts"],
    years: [2025, 2026],
    max_pages: 12,
    max_depth: 1,
  });
  await expect(page.getByLabel("Donaciones", { exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Cancelar descarga" }).click();
  await expect(
    page.getByRole("heading", { name: "Último trabajo: Cancelado" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await page.getByRole("button", { name: "Bloquear panel" }).click();
  await expect(page.getByLabel("Clave de administración")).toHaveValue("");
});

test("active job recovered after reopening polls until terminal, then refreshes inventory", async ({
  page,
}) => {
  let polls = 0;
  let gets = 0;
  await page.route("**/api/crawl", (route) => {
    const command = route.request().postDataJSON();
    if (command.action === "status") polls++;
    if (command.action === "get") gets++;
    return route.fulfill({
      json: {
        sections: command.action === "get" ? sections : null,
        invalid_manifests: 0,
        job: job(polls ? "completed" : "running"),
      },
    });
  });
  await page.goto("/crawler");
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Último trabajo: Finalizado",
      exact: true,
    }),
  ).toBeVisible();
  expect(polls).toBe(1);
  expect(gets).toBe(2);
});

test("authentication, invalid years and conflict errors remain actionable", async ({
  page,
}) => {
  let authorized = false;
  let starts = 0;
  await page.route("**/api/crawl", (route) => {
    const command = route.request().postDataJSON();
    if (!authorized)
      return route.fulfill({
        status: 401,
        json: { detail: "Invalid administration key" },
      });
    if (command.action === "start") {
      starts++;
      return route.fulfill({
        status: 409,
        json: { detail: "A crawl is already active" },
      });
    }
    return route.fulfill({
      json: { sections, invalid_manifests: 0, job: null },
    });
  });
  await page.goto("/crawler");
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Invalid administration key",
  );
  authorized = true;
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await page.getByLabel("Tarifas", { exact: true }).check();
  await page.getByLabel("Años de tarifas", { exact: false }).fill("2025, ");
  await page.getByRole("button", { name: /Descargar 1/ }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "hasta 5 años únicos",
  );
  expect(starts).toBe(0);
  await page.getByLabel("Años de tarifas", { exact: false }).fill("2025");
  await page.getByRole("button", { name: /Descargar 1/ }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "A crawl is already active",
  );
});

test("crawler proxy forwards only bearer to the fixed endpoint and rejects foreign Origin", async ({
  request,
}) => {
  const response = await request.post("/api/crawl", {
    headers: { Authorization: `Bearer ${key}`, Cookie: "private=value" },
    data: { action: "get" },
  });
  expect(response.status()).toBe(200);
  expect(response.headers()["cache-control"]).toBe("no-store");
  expect(await response.json()).toEqual({
    authorization: `Bearer ${key}`,
    cookie: null,
    origin: null,
  });
  const rejected = await request.post("/api/crawl", {
    headers: { Authorization: `Bearer ${key}`, Origin: "https://evil.test" },
    data: { action: "start" },
  });
  expect(rejected.status()).toBe(403);
});

test("crawler remains usable at mobile width and is linked from the question page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("link", { name: "Corpus / Crawler" }).click();
  await expect(
    page.getByRole("heading", { name: "Crawler de fuentes oficiales" }),
  ).toBeVisible();
  await page.route("**/api/crawl", (route) =>
    route.fulfill({ json: { sections, invalid_manifests: 0, job: null } }),
  );
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear crawler" }).click();
  await expect(page.getByLabel("Donaciones", { exact: true })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
});
