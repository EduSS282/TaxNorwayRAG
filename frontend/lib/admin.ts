export type Service = "generator" | "embeddings" | "reranker" | "qdrant";
export type Connections = {
  generator_url: string;
  generator_model: string;
  generator_timeout: number;
  embedding_url: string;
  embedding_model: string;
  embedding_provider: "ollama" | "local";
  reranker_url: string;
  reranker_model: string;
  reranker_provider: "llamacpp" | "http" | "local";
  qdrant_url: string;
  qdrant_collection: string;
};
export type ServiceStatus = {
  service: Service;
  url: string;
  state: string;
  owned: boolean;
  can_start: boolean;
  ready: boolean;
  detail: string;
};
export type RuntimeState = {
  connections: Connections;
  revision: string;
  can_restore: boolean;
  allowed_origins: string[];
  local_services: Service[];
  services: ServiceStatus[];
  events: string[];
  checks?: ServiceStatus[];
};
export async function manage(
  key: string,
  payload: object,
): Promise<RuntimeState> {
  const response = await fetch("/api/admin", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
    signal: AbortSignal.timeout(90000),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : `Solicitud rechazada (HTTP ${response.status})`,
    );
  return value as RuntimeState;
}
