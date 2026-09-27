"use client";

import { useEffect, useState } from "react";
import { CrawlState, crawlCommand, isCrawling } from "../lib/crawler";

const states: Record<string, string> = {
  pending: "Pendiente",
  running: "Descargando",
  cancelling: "Cancelando",
  cancelled: "Cancelado",
  completed: "Finalizado",
  partial: "Finalizado con omisiones o errores",
  failed: "Fallido",
};

function merge(previous: CrawlState | null, next: CrawlState): CrawlState {
  return {
    ...next,
    sections: next.sections ?? previous?.sections ?? null,
    invalid_manifests:
      next.sections === null
        ? (previous?.invalid_manifests ?? 0)
        : next.invalid_manifests,
  };
}

export function CrawlerPanel() {
  const [key, setKey] = useState("");
  const [state, setState] = useState<CrawlState | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [years, setYears] = useState("");
  const [pages, setPages] = useState(50);
  const [depth, setDepth] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = isCrawling(state?.job);
  const jobId = state?.job?.id;
  const jobState = state?.job?.state;

  // Poll only an explicitly started/discovered active job; stop on errors, lock or unmount.
  useEffect(() => {
    if (!active || !key || busy || error) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        let next = await crawlCommand(
          key,
          { action: "status" },
          controller.signal,
        );
        if (!isCrawling(next.job))
          next = await crawlCommand(key, { action: "get" }, controller.signal);
        if (controller.signal.aborted) return;
        setState((previous) => merge(previous, next));
        if (isCrawling(next.job)) timer = setTimeout(poll, 2000);
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(
            reason instanceof Error
              ? reason.message
              : "No se pudo actualizar el progreso",
          );
      }
    }
    timer = setTimeout(poll, 2000);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [active, key, busy, error, jobId, jobState]);

  async function run(action: "get" | "start" | "cancel") {
    setBusy(true);
    setError("");
    try {
      const annualYears = years.trim()
        ? years.split(",").map((year) => year.trim())
        : [];
      if (
        action === "start" &&
        (annualYears.length > 5 ||
          annualYears.some(
            (year) => !/^\d{4}$/.test(year) || +year < 1900 || +year > 2100,
          ) ||
          new Set(annualYears).size !== annualYears.length)
      )
        throw new Error(
          "Introduce hasta 5 años únicos entre 1900 y 2100, separados por comas.",
        );
      let next = await crawlCommand(
        key,
        action === "start"
          ? {
              action,
              sources: selected,
              years: annualYears.map(Number),
              max_pages: pages,
              max_depth: depth,
            }
          : { action, ...(action === "cancel" ? { job_id: jobId } : {}) },
      );
      if (action !== "get" && !isCrawling(next.job))
        next = await crawlCommand(key, { action: "get" });
      setState((previous) => merge(previous, next));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Operación fallida");
    } finally {
      setBusy(false);
    }
  }

  function lock() {
    setKey("");
    setState(null);
    setSelected([]);
    setError("");
  }

  return (
    <main lang="es" className="settings-page">
      <nav className="runtime-actions" aria-label="Administración">
        <a href="/">← Preguntas</a>
        <a href="/settings">Conexiones y servicios</a>
      </nav>
      <p className="eyebrow">CORPUS · ADMINISTRACIÓN PRIVADA</p>
      <h1>Crawler de fuentes oficiales</h1>
      <p>
        Elige qué secciones descargar de Skatteetaten. Los archivos se guardan
        en la máquina de la API, no en este navegador.
      </p>
      <p>
        Descargado no significa completo ni indexado. Este panel no carga
        modelos ni modifica Qdrant.
      </p>
      {!state ? (
        <form
          className="panel"
          onSubmit={(event) => {
            event.preventDefault();
            void run("get");
          }}
        >
          <label htmlFor="crawler-key">Clave de administración</label>
          <input
            id="crawler-key"
            type="password"
            minLength={32}
            required
            autoComplete="off"
            value={key}
            disabled={busy}
            onChange={(event) => setKey(event.target.value)}
          />
          <p className="help">
            Usa TAXGUIDE_ADMIN_TOKEN del backend. La clave solo permanece en
            memoria de esta página.
          </p>
          <button disabled={busy}>Desbloquear crawler</button>
        </form>
      ) : (
        <>
          <div className="runtime-actions">
            <button disabled={busy} onClick={() => void run("get")}>
              Actualizar inventario
            </button>
            <button disabled={busy} onClick={lock}>
              Bloquear panel
            </button>
          </div>
          <p className="help">
            Cerrar o bloquear la página no cancela la descarga. Al volver,
            actualiza el inventario para recuperar el trabajo activo.
          </p>
          {state.invalid_manifests > 0 && (
            <p role="status">
              Hay {state.invalid_manifests} manifiestos inválidos: no se cuentan
              como descargados.
            </p>
          )}
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void run("start");
            }}
          >
            <fieldset disabled={busy || active}>
              <legend>
                <h2>Secciones disponibles</h2>
              </legend>
              <div className="runtime-actions">
                <button
                  type="button"
                  onClick={() =>
                    setSelected(
                      (state.sections ?? [])
                        .slice(0, 8)
                        .map((section) => section.id),
                    )
                  }
                >
                  Seleccionar hasta 8 secciones
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setSelected(
                      (state.sections ?? [])
                        .filter((section) => section.downloaded === 0)
                        .slice(0, 8)
                        .map((section) => section.id),
                    )
                  }
                >
                  Seleccionar sin descargas
                </button>
                <button type="button" onClick={() => setSelected([])}>
                  Limpiar selección
                </button>
              </div>
              <div className="runtime-fields">
                {(state.sections ?? []).map((section) => (
                  <article className="panel crawler-card" key={section.id}>
                    <label className="checkbox">
                      <input
                        type="checkbox"
                        checked={selected.includes(section.id)}
                        disabled={
                          !selected.includes(section.id) && selected.length >= 8
                        }
                        onChange={(event) =>
                          setSelected((current) =>
                            event.target.checked
                              ? [...current, section.id]
                              : current.filter((id) => id !== section.id),
                          )
                        }
                      />
                      {section.title}
                    </label>
                    <span
                      className={`badge ${section.downloaded ? "answered" : "abstained"}`}
                    >
                      {section.downloaded
                        ? `${section.downloaded} páginas descargadas`
                        : "Sin descargas verificadas"}
                    </span>
                    <p className="help">
                      Idioma: {section.languages.join(", ") || "sin filtro"}.
                      Última captura:{" "}
                      {section.last_download
                        ? new Date(section.last_download).toLocaleString(
                            "es-ES",
                          )
                        : "—"}
                    </p>
                    <p>
                      Años verificados:{" "}
                      {Object.entries(section.years)
                        .filter(([year]) => year !== "unknown")
                        .map(([year, count]) => `${year} (${count})`)
                        .join(", ") || "ninguno"}
                      . Sin año: {section.years.unknown ?? 0}.
                    </p>
                    {section.unavailable > 0 && (
                      <p>
                        {section.unavailable} capturas con HTML ausente o no
                        válido.
                      </p>
                    )}
                    <a href={section.url} target="_blank" rel="noreferrer">
                      Ver sección oficial ↗
                    </a>
                  </article>
                ))}
              </div>
              <section className="panel">
                <h2>Límites de la descarga</h2>
                <div className="runtime-fields">
                  <div>
                    <label htmlFor="crawl-pages">
                      Máximo de páginas por sección
                    </label>
                    <input
                      id="crawl-pages"
                      type="number"
                      min={1}
                      max={200}
                      required
                      value={pages}
                      onChange={(event) => setPages(Number(event.target.value))}
                    />
                  </div>
                  <div>
                    <label htmlFor="crawl-depth">Profundidad de enlaces</label>
                    <input
                      id="crawl-depth"
                      type="number"
                      min={0}
                      max={3}
                      required
                      value={depth}
                      onChange={(event) => setDepth(Number(event.target.value))}
                    />
                  </div>
                </div>
                <label htmlFor="crawl-years">
                  Años de tarifas (opcional, separados por comas)
                </label>
                <input
                  id="crawl-years"
                  value={years}
                  placeholder="2025, 2026"
                  onChange={(event) => setYears(event.target.value)}
                />
                <p className="help">
                  Solo se amplían años anunciados por el selector oficial de
                  tarifas. No se asignan años a guías generales. Las variantes
                  anuales y los intentos fallidos cuentan para el límite.
                </p>
                <p>
                  Se procesan secciones una a una, respetando robots.txt y las
                  pausas configuradas. Volver a descargar actualiza las capturas
                  existentes, incluso las que no hayan cambiado.
                </p>
                <button
                  className="primary"
                  disabled={selected.length === 0}
                  type="submit"
                >
                  Descargar {selected.length} secciones seleccionadas
                </button>
              </section>
            </fieldset>
          </form>
          {state.job && (
            <section className="panel" aria-label="Progreso de descarga">
              <h2>
                Último trabajo: {states[state.job.state] ?? state.job.state}
              </h2>
              <p className="help">
                {state.job.id} · Límite: {state.job.max_pages} páginas/sección ·
                Profundidad: {state.job.max_depth} · Años solicitados:{" "}
                {state.job.years.join(", ") || "ninguno"}
              </p>
              <div aria-live="polite">
                {state.job.sections.map((section) => (
                  <article className="service-card" key={section.source_id}>
                    <strong>
                      {state.sections?.find(
                        (item) => item.id === section.source_id,
                      )?.title ?? section.source_id}
                      : {states[section.state]}
                    </strong>
                    <p>
                      Descargadas: {section.fetched} · Errores: {section.failed}{" "}
                      · Omitidas: {section.skipped}
                    </p>
                    <p className="help">
                      Al finalizar la sección: nuevas {section.new}, modificadas{" "}
                      {section.changed}, sin cambios {section.unchanged}.
                    </p>
                  </article>
                ))}
              </div>
              {state.job.detail && <p>{state.job.detail}</p>}
              <p className="help">
                «Finalizado» indica que terminó este trabajo limitado, no que la
                sección esté completa. El progreso del trabajo se pierde al
                reiniciar la API; las capturas permanecen.
              </p>
              {active && (
                <button
                  disabled={busy || state.job.state === "cancelling"}
                  onClick={() => void run("cancel")}
                >
                  Cancelar descarga
                </button>
              )}
              {active && (
                <p className="help">
                  La cancelación conserva archivos y puede esperar a que termine
                  la petición HTTP en curso. Los contadores se actualizan cada 2
                  segundos.
                </p>
              )}
            </section>
          )}
          <section className="panel">
            <h2>Después: preparar el corpus</h2>
            <p>
              La indexación sigue siendo un paso separado por CLI. Ejecuta el
              build con los mismos directorios del backend y los filtros de las
              secciones deseadas. Necesita embeddings y Qdrant disponibles.
            </p>
            <p>Ejemplo para tarifas, desde la raíz del repositorio:</p>
            <pre>
              uv run taxguide corpus build --url-prefix "/en/rates/" --language
              en --index
            </pre>
            <p className="help">
              Los conteos de esta página no verifican la colección vectorial ni
              la calidad de las respuestas.
            </p>
          </section>
        </>
      )}
      {busy && <p role="status">Consultando la API…</p>}
      {error && (
        <p role="alert" className="panel error">
          {error}. Si el envío perdió conexión, actualiza el inventario antes de
          reintentar: el trabajo podría haberse iniciado.
        </p>
      )}
    </main>
  );
}
