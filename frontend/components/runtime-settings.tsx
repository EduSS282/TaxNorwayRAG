"use client";

import { useState } from "react";
import {
  Connections,
  RuntimeState,
  Service,
  ServiceStatus,
  manage,
} from "../lib/admin";

const names: Record<Service, string> = {
  generator: "Generador LLM",
  embeddings: "Embeddings",
  reranker: "Reranker",
  qdrant: "Qdrant",
};
const fields: { key: keyof Connections; label: string; type?: string }[] = [
  { key: "generator_url", label: "Dirección del LLM", type: "url" },
  { key: "generator_model", label: "Modelo LLM (alias del servidor)" },
  { key: "generator_timeout", label: "Timeout LLM (segundos)", type: "number" },
  { key: "embedding_url", label: "Dirección de embeddings", type: "url" },
  { key: "embedding_model", label: "Modelo de embeddings" },
  { key: "reranker_url", label: "Dirección del reranker", type: "url" },
  { key: "reranker_model", label: "Modelo del reranker" },
  { key: "qdrant_url", label: "Dirección de Qdrant", type: "url" },
  { key: "qdrant_collection", label: "Colección de Qdrant" },
];

function Status({ item }: { item: ServiceStatus }) {
  return (
    <div className="runtime-status">
      <strong>
        {names[item.service]} · {item.state}
      </strong>
      <p>
        {item.ready ? "Comprobación disponible" : "Preparación no verificada"} ·{" "}
        {item.owned ? "Iniciado por TaxGuide" : "No gestionado por TaxGuide"}
      </p>
      <p className="help">
        {item.url}
        <br />
        {item.detail}
      </p>
    </div>
  );
}

export function RuntimeSettings() {
  const [key, setKey] = useState("");
  const [state, setState] = useState<RuntimeState | null>(null);
  const [draft, setDraft] = useState<Connections | null>(null);
  const [checks, setChecks] = useState<ServiceStatus[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reindex, setReindex] = useState(false);
  const [stop, setStop] = useState(false);
  const [mode, setMode] = useState("dense");
  const dirty =
    state && draft
      ? JSON.stringify(state.connections) !== JSON.stringify(draft)
      : false;

  async function run(action: string, service?: Service) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const response = await manage(key, {
        action,
        revision: state?.revision,
        service,
        connections: ["save", "check"].includes(action) ? draft : undefined,
        confirm_reindex: reindex,
        confirm_stop: stop,
        mode,
      });
      setState(response);
      if (["get", "save", "restore"].includes(action)) {
        setDraft(response.connections);
        setChecks([]);
        setReindex(false);
      }
      if (action === "check") setChecks(response.checks || []);
      if (action === "save" || action === "restore")
        setNotice(
          "Configuración aplicada a nuevas consultas. Las consultas en curso conservan su configuración anterior.",
        );
      if (action === "prepare")
        setNotice(
          "Preparación por etapas: revisa los estados. Si un servicio está arrancando, comprueba y pulsa Preparar de nuevo cuando esté listo.",
        );
      setStop(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Operación fallida");
    } finally {
      setBusy(false);
    }
  }

  function lock() {
    setKey("");
    setState(null);
    setDraft(null);
    setChecks([]);
    setError("");
    setNotice("");
  }

  return (
    <main lang="es" className="settings-page">
      <a href="/">← Volver a las preguntas</a>
      <p className="eyebrow">ADMINISTRACIÓN PRIVADA</p>
      <h1>Conexiones y servicios</h1>
      <p>
        «Local» significa la máquina donde corre la API de TaxGuide, no
        necesariamente este navegador. No se controlan procesos remotos.
      </p>
      {!state ? (
        <form
          className="panel"
          onSubmit={(event) => {
            event.preventDefault();
            void run("get");
          }}
        >
          <label htmlFor="admin-key">Clave de administración</label>
          <input
            id="admin-key"
            type="password"
            required
            minLength={32}
            autoComplete="off"
            value={key}
            disabled={busy}
            onChange={(event) => setKey(event.target.value)}
          />
          <p className="help">
            Configura TAXGUIDE_ADMIN_TOKEN en el backend. La clave solo
            permanece en memoria de esta página; no se guarda en el navegador.
          </p>
          <button disabled={busy} type="submit">
            {busy ? "Comprobando…" : "Desbloquear"}
          </button>
        </form>
      ) : (
        <>
          <div className="runtime-actions">
            <button disabled={busy} onClick={lock}>
              Bloquear panel
            </button>
            <button disabled={busy} onClick={() => void run("get")}>
              Recargar y descartar cambios
            </button>
          </div>
          <form
            className="panel"
            onSubmit={(event) => {
              event.preventDefault();
              void run("save");
            }}
          >
            <h2>Conexiones</h2>
            <p className="help">
              URL base sin /v1, credenciales ni rutas. La API solo acepta los
              destinos autorizados por el operador.
            </p>
            <fieldset disabled={busy}>
              <div className="runtime-fields">
                {fields.map((field) => (
                  <div key={field.key}>
                    <label htmlFor={field.key}>{field.label}</label>
                    <input
                      id={field.key}
                      type={field.type || "text"}
                      required
                      maxLength={2048}
                      min={field.type === "number" ? 1 : undefined}
                      max={field.type === "number" ? 180 : undefined}
                      value={draft?.[field.key] ?? ""}
                      onChange={(event) => {
                        setDraft((current) =>
                          current
                            ? {
                                ...current,
                                [field.key]:
                                  field.type === "number"
                                    ? Number(event.target.value)
                                    : event.target.value,
                              }
                            : current,
                        );
                        setChecks([]);
                        setNotice("");
                      }}
                    />
                  </div>
                ))}
                <div>
                  <label htmlFor="embedding-provider">
                    Proveedor de embeddings
                  </label>
                  <select
                    id="embedding-provider"
                    value={draft?.embedding_provider}
                    onChange={(event) => {
                      setDraft((current) =>
                        current
                          ? {
                              ...current,
                              embedding_provider: event.target
                                .value as Connections["embedding_provider"],
                            }
                          : current,
                      );
                      setChecks([]);
                    }}
                  >
                    <option value="ollama">Ollama (HTTP)</option>
                    <option value="local">En el proceso Python</option>
                  </select>
                </div>
                <div>
                  <label htmlFor="reranker-provider">
                    Proveedor de reranking
                  </label>
                  <select
                    id="reranker-provider"
                    value={draft?.reranker_provider}
                    onChange={(event) => {
                      setDraft((current) =>
                        current
                          ? {
                              ...current,
                              reranker_provider: event.target
                                .value as Connections["reranker_provider"],
                            }
                          : current,
                      );
                      setChecks([]);
                    }}
                  >
                    <option value="llamacpp">llama.cpp</option>
                    <option value="http">Servicio HTTP TaxGuide</option>
                    <option value="local">En el proceso Python</option>
                  </select>
                </div>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={reindex}
                  onChange={(event) => setReindex(event.target.checked)}
                />
                Entiendo que cambiar el modelo/proveedor de embeddings exige
                otra colección compatible y reindexar fuera de la app.
              </label>
              <p className="help">
                No cambies el modelo servido detrás de una URL de embeddings sin
                tratarlo como un cambio de modelo. Probar conexión no valida la
                compatibilidad de sus vectores.
              </p>
              <p className="help">
                Los proveedores «En el proceso Python» pueden descargar pesos
                ausentes al consultar. Prepara su caché/modo offline si no quieres
                descargas; los botones de este panel no cargan esos modelos.
              </p>
              <div className="runtime-actions">
                <button
                  type="button"
                  onClick={(event) => {
                    if (event.currentTarget.form?.reportValidity())
                      void run("check");
                  }}
                >
                  Probar conexiones
                </button>
                <button type="submit" disabled={!dirty}>
                  Guardar y aplicar
                </button>
                <button
                  type="button"
                  disabled={!state.can_restore || !!dirty}
                  onClick={() => void run("restore")}
                >
                  Restaurar configuración anterior
                </button>
              </div>
              <details>
                <summary>Destinos autorizados</summary>
                <ul>
                  {state.allowed_origins.map((origin) => (
                    <li key={origin}>
                      <code>{origin}</code>
                    </li>
                  ))}
                </ul>
                <p className="help">
                  Para autorizar otro destino, configura
                  TAXGUIDE_SERVICE_ORIGINS en el backend y reinícialo.
                </p>
              </details>
            </fieldset>
            {checks.length > 0 ? (
              <section aria-label="Resultado de probar conexiones">
                <h3>Comprobación del borrador (no guardado)</h3>
                {checks.map((item) => (
                  <Status key={item.service} item={item} />
                ))}
              </section>
            ) : null}
          </form>
          <section className="panel">
            <h2>Servicios en la máquina del backend</h2>
            <p>
              Los perfiles de arranque se definen en TAXGUIDE_LOCAL_SERVICES. No
              se instalan binarios ni se descargan modelos. Los procesos ajenos
              nunca se detienen.
            </p>
            <p className="help">
              Arrancar un servicio consume RAM/VRAM. Solo un modelo llama.cpp
              gestionado puede usar GPU a la vez; esto no controla procesos
              externos ni garantiza que quepa en memoria.
            </p>
            <fieldset disabled={busy || !!dirty}>
              <button onClick={() => void run("get")}>
                Comprobar servicios
              </button>
              <label htmlFor="prepare-mode">Modo que quieres preparar</label>
              <select
                id="prepare-mode"
                value={mode}
                onChange={(event) => setMode(event.target.value)}
              >
                <option value="dense">Dense</option>
                <option value="sparse">Sparse</option>
                <option value="hybrid">Hybrid</option>
                <option value="reranked">Hybrid + rerank</option>
              </select>
              <button onClick={() => void run("prepare")}>
                Preparar servicios para consultar
              </button>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={stop}
                  onChange={(event) => setStop(event.target.checked)}
                />
                Confirmo detener el servicio seleccionado; las consultas en
                curso pueden fallar.
              </label>
              {state.services.map((item) => (
                <article key={item.service} className="service-card">
                  <Status item={item} />
                  <div className="runtime-actions">
                    <button
                      disabled={
                        !state.local_services.includes(item.service) ||
                        item.owned ||
                        item.state === "external"
                      }
                      onClick={() => void run("start", item.service)}
                    >
                      Iniciar {names[item.service]}
                    </button>
                    <button
                      disabled={!item.owned || !stop}
                      onClick={() => void run("stop", item.service)}
                    >
                      Detener {names[item.service]}
                    </button>
                  </div>
                </article>
              ))}
            </fieldset>
            {dirty ? (
              <p>Guarda o descarta los cambios antes de operar servicios.</p>
            ) : null}
            <details>
              <summary>Eventos recientes del gestor</summary>
              <pre>
                {state.events.join("\n") ||
                  "Sin eventos. No se muestran prompts ni salida bruta de los modelos."}
              </pre>
            </details>
          </section>
        </>
      )}
      <div aria-live="polite">
        {busy ? <p role="status">Operación en curso…</p> : null}
        {notice ? <p>{notice}</p> : null}
      </div>
      {error ? (
        <p role="alert" className="panel error">
          {error}
        </p>
      ) : null}
    </main>
  );
}
