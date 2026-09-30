import { expect, test } from "@playwright/test";

const key = "test-only-administration-key-0123456789";
const connections = {
  generator_url: "http://127.0.0.1:8080",
  generator_model: "llm",
  generator_timeout: 180,
  embedding_url: "http://127.0.0.1:11434",
  embedding_model: "embed",
  embedding_provider: "ollama",
  reranker_url: "http://127.0.0.1:8001",
  reranker_model: "rank",
  reranker_provider: "llamacpp",
  qdrant_url: "http://127.0.0.1:6333",
  qdrant_collection: "taxguide",
};

test("authenticated settings save, draft probe, rollback, start and confirmed stop", async ({
  page,
}) => {
  const commands: Record<string, unknown>[] = [];
  let current = { ...connections };
  let previous = { ...connections };
  let owned = false;
  await page.route("**/api/admin", async (route) => {
    expect(route.request().headers().authorization).toBe(`Bearer ${key}`);
    const command = route.request().postDataJSON();
    commands.push(command);
    if (command.action === "save") {
      previous = current;
      current = command.connections;
    }
    if (command.action === "restore") current = previous;
    if (command.action === "start") owned = true;
    if (command.action === "stop") {
      expect(command.confirm_stop).toBe(true);
      owned = false;
    }
    const status = {
      service: "generator",
      url: current.generator_url,
      state: owned ? "starting" : "unavailable",
      ready: false,
      owned,
      can_start: true,
      detail: "Test process only",
    };
    await route.fulfill({
      json: {
        connections: current,
        revision: "rev",
        can_restore: true,
        allowed_origins: [current.generator_url],
        local_services: ["generator"],
        services: [status],
        events: [],
        ...(command.action === "check" ? { checks: [status] } : {}),
      },
    });
  });
  await page.goto("/settings");
  expect(commands).toHaveLength(0);
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear" }).click();
  await page
    .getByLabel("Modelo LLM (alias del servidor)", { exact: true })
    .fill("another-model");
  await expect(
    page.getByRole("button", { name: "Iniciar Generador LLM", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Probar conexiones" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Comprobación del borrador (no guardado)",
    }),
  ).toBeVisible();
  expect(commands.at(-1)?.action).toBe("check");
  expect(current.generator_model).toBe("llm");
  await page.getByRole("button", { name: "Guardar y aplicar" }).click();
  await expect(
    page.getByText(/Configuración aplicada a nuevas consultas/),
  ).toBeVisible();
  expect(current.generator_model).toBe("another-model");
  await page
    .getByRole("button", { name: "Restaurar configuración anterior" })
    .click();
  await expect(
    page.getByLabel("Modelo LLM (alias del servidor)", { exact: true }),
  ).toHaveValue("llm");
  await page
    .getByRole("button", { name: "Iniciar Generador LLM", exact: true })
    .click();
  await expect(
    page.getByText("Generador LLM · starting", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Detener Generador LLM", exact: true }),
  ).toBeDisabled();
  await page.getByLabel(/Confirmo detener el servicio seleccionado/).check();
  await page
    .getByRole("button", { name: "Detener Generador LLM", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Preparar servicios para consultar" })
    .click();
  await expect(page.getByText(/Preparación por etapas:/)).toBeVisible();
  expect(commands.at(-1)?.action).toBe("prepare");
  expect(
    await page.evaluate(() => localStorage.length + sessionStorage.length),
  ).toBe(0);
  await page.getByRole("button", { name: "Bloquear panel" }).click();
  await expect(page.getByLabel("Clave de administración")).toHaveValue("");
});

test("API errors remain visible; external services cannot be stopped", async ({
  page,
}) => {
  let fail = true;
  await page.route("**/api/admin", (route) =>
    route.fulfill(
      fail
        ? { status: 401, json: { detail: "Invalid administration key" } }
        : {
            json: {
              connections,
              revision: "rev",
              can_restore: false,
              allowed_origins: [],
              local_services: [],
              events: [],
              services: [
                {
                  service: "generator",
                  url: connections.generator_url,
                  state: "external",
                  owned: false,
                  ready: true,
                  can_start: false,
                  detail: "External process",
                },
              ],
            },
          },
    ),
  );
  await page.goto("/settings");
  await page.getByLabel("Clave de administración").fill(key);
  await page.getByRole("button", { name: "Desbloquear" }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "Invalid administration key",
  );
  fail = false;
  await page.getByRole("button", { name: "Desbloquear" }).click();
  await page.getByLabel(/Confirmo detener el servicio seleccionado/).check();
  await expect(
    page.getByRole("button", { name: "Detener Generador LLM", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Iniciar Generador LLM", exact: true }),
  ).toBeDisabled();
});

test("proxy forwards admin key only to administration, without cookies or Origin", async ({
  request,
}) => {
  const result = await request.post("/api/admin", {
    headers: {
      Authorization: `Bearer ${key}`,
      Cookie: "private=not-forwarded",
    },
    data: { action: "get" },
  });
  expect(result.status()).toBe(200);
  expect(await result.json()).toEqual({
    authorization: `Bearer ${key}`,
    cookie: null,
    origin: null,
  });
  const query = await request.post("/api/query", {
    headers: { Authorization: `Bearer ${key}` },
    data: { question: "echo" },
  });
  expect((await query.json()).authorization).toBeNull();
  expect(
    (
      await request.post("/api/admin", {
        headers: {
          Authorization: `Bearer ${key}`,
          Origin: "https://evil.test",
        },
        data: { action: "start" },
      })
    ).status(),
  ).toBe(403);
});
