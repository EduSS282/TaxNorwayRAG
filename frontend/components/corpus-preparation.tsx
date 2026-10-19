"use client";

import { useEffect, useState } from "react";
import { CorpusState, corpusCommand } from "../lib/corpus";

const states: Record<string, string> = {
  running: "Preparando", cancelling: "Cancelando", cancelled: "Cancelado",
  completed: "Finalizado", partial: "Finalizado con errores", failed: "Fallido",
};

export function CorpusPreparation({ adminKey }: { adminKey: string }) {
  const [state, setState] = useState<CorpusState | null>(null);
  const [prefix, setPrefix] = useState("/en/");
  const [language, setLanguage] = useState("en");
  const [limit, setLimit] = useState(200);
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<Record<string, number> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const active = ["running", "cancelling"].includes(state?.job?.state ?? "");

  useEffect(() => {
    if (!active || busy || error) return;
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      try {
        const next = await corpusCommand(adminKey, { action: "get" }, controller.signal);
        if (!controller.signal.aborted) setState(next);
      } catch (reason) {
        if (!controller.signal.aborted)
          setError(reason instanceof Error ? reason.message : "No se pudo actualizar");
      }
    }, 2000);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [active, busy, error, adminKey, state]);

  function invalidate() { setPreview(null); setConfirmed(false); }

  async function run(action: "get" | "preview" | "start" | "cancel", index = false) {
    setBusy(true);
    setError("");
    try {
      const next = await corpusCommand(adminKey, {
        action,
        ...(action === "preview" || action === "start" ? {
          revision: state?.revision, url_prefix: prefix, language, limit,
          index, confirm_index: confirmed,
        } : {}),
        ...(action === "cancel" ? { job_id: state?.job?.id } : {}),
      });
      setState(next);
      setPreview(action === "preview" ? next.selection : null);
      if (action !== "preview") setConfirmed(false);
    } catch (reason) {
      setPreview(null);
      setError(reason instanceof Error ? reason.message : "Operación fallida");
    } finally { setBusy(false); }
  }

  function downloadReport() {
    if (!state?.job?.report) return;
    const url = URL.createObjectURL(new Blob(
      [JSON.stringify(state.job, null, 2)], { type: "application/json" },
    ));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `corpus-${state.job.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="panel" aria-label="Preparación e indexación">
      <h2>Preparar corpus e indexar en Qdrant</h2>
      <p>
        1. Configura y comprueba servicios en <a href="/settings">Conexiones y servicios</a>.
        {" "}2. Descarga fuentes arriba. 3. Revisa la selección aquí.
        {" "}4. Construye e indexa. 5. Abre <a href="/">Preguntas e inspector</a>.
      </p>
      <p className="help">
        No necesitas comandos para enviar vectores. Usa las conexiones guardadas de la API.
        Los modelos y servicios deben estar instalados en el entorno.
      </p>
      <button disabled={busy} onClick={() => void run("get")}>
        Actualizar preparación
      </button>
      {state && <>
        <p>
          Colección: <strong>{state.collection}</strong> · Embeddings: {state.embedding_model}
          {" "}· Chunks: {state.chunk_strategy}, {state.max_tokens} tokens.
        </p>
        <fieldset disabled={busy || active}>
          <legend>Selección de capturas</legend>
          <label htmlFor="corpus-prefix">Prefijo de ruta oficial</label>
          <input id="corpus-prefix" value={prefix} maxLength={512}
            onChange={(event) => { setPrefix(event.target.value); invalidate(); }} />
          <label htmlFor="corpus-language">Idioma del corpus</label>
          <select id="corpus-language" value={language}
            onChange={(event) => { setLanguage(event.target.value); invalidate(); }}>
            <option value="">Todos</option><option value="en">English</option>
            <option value="nb">Norsk bokmål</option><option value="nn">Nynorsk</option>
          </select>
          <label htmlFor="corpus-limit">Máximo de documentos</label>
          <input id="corpus-limit" type="number" min={1} max={2000} value={limit}
            onChange={(event) => { setLimit(Number(event.target.value)); invalidate(); }} />
          <button onClick={() => void run("preview")}>Revisar selección</button>
          {preview && <p role="status">
            Capturas examinadas: {preview.scanned} · Seleccionadas: {preview.selected}
            {" "}· Excluidas por límite: {preview.excluded_limit}
            {" "}· Duplicadas: {preview.excluded_duplicate}.
          </p>}
          <p className="help">
            Construir sin indexar comprueba parsing y chunking. No guarda un índice consultable.
            Indexar crea la colección si falta y actualiza documentos seleccionados.
            Una escritura parcial puede verse en consultas. Usa una colección nueva para una reconstrucción aislada.
          </p>
          <label className="checkbox">
            <input type="checkbox" checked={confirmed} disabled={!preview?.selected}
              onChange={(event) => setConfirmed(event.target.checked)} />
            Confirmo escribir vectores en {state.collection}
          </label>
          <div className="runtime-actions">
            <button disabled={!preview?.selected} onClick={() => void run("start")}>
              Construir sin indexar
            </button>
            <button className="primary" disabled={!preview?.selected || !confirmed}
              onClick={() => void run("start", true)}>Construir e indexar</button>
          </div>
        </fieldset>
        {state.job && <section aria-label="Progreso de preparación" aria-live="polite">
          <h3>{states[state.job.state] ?? state.job.state}</h3>
          <p>{state.job.id} · Colección del trabajo: {state.job.collection}
            {" "}· Modelo: {state.job.embedding_model}</p>
          <p>Seleccionados: {state.job.selected} · Procesados: {state.job.processed}
            {" "}· Sin cambios: {state.job.unchanged} · Fallidos: {state.job.failed}</p>
          {active && <button disabled={busy || state.job.state === "cancelling"}
            onClick={() => void run("cancel")}>Cancelar preparación</button>}
          {state.job.detail && <p role="alert">{state.job.detail}</p>}
          {state.job.report && <>
            <p>Chunks generados: {state.job.report.chunks_generated}
              {" "}· Indexación: {state.job.report.indexing_enabled ? "sí" : "no"}</p>
            <p>Años de documentos: {Object.entries(state.job.report.documents_by_tax_year)
              .map(([year, count]) => `${year}: ${count}`).join(", ") || "ninguno"}</p>
            <p>Errores por etapa: {Object.entries(state.job.report.failure_categories)
              .map(([stage, count]) => `${stage}: ${count}`).join(", ") || "ninguno"}</p>
            <p>Segundos por etapa: {Object.entries(state.job.report.stage_seconds)
              .map(([stage, seconds]) => `${stage}: ${seconds.toFixed(2)}`).join(", ")}</p>
            <button onClick={downloadReport}>Descargar informe de preparación</button>
          </>}
        </section>}
      </>}
      <p className="help">
        El trabajo continúa al cerrar la página. Actualiza para recuperarlo.
        Cancelar espera al documento en curso y conserva escrituras; no hace rollback.
        El último informe final permanece tras reiniciar. Los trabajos interrumpidos no se reanudan.
        Un informe correcto no certifica precisión fiscal. Comprueba respuestas y citas en el inspector.
      </p>
      {busy && <p role="status">Consultando preparación…</p>}
      {error && <p role="alert">{error}. Actualiza antes de reintentar: el trabajo podría estar activo.</p>}
    </section>
  );
}
