export type BuildReport = {
  run_id: string;
  selected: number;
  processed: number;
  unchanged: number;
  failed: number;
  chunks_generated: number;
  indexing_enabled: boolean;
  vector_collection: string | null;
  documents_by_tax_year: Record<string, number>;
  stage_seconds: Record<string, number>;
  failure_categories: Record<string, number>;
};

export type CorpusState = {
  revision: string;
  collection: string;
  embedding_model: string;
  chunk_strategy: string;
  max_tokens: number;
  selection: Record<string, number> | null;
  job: {
    id: string;
    state: string;
    selected: number;
    processed: number;
    unchanged: number;
    failed: number;
    index: boolean;
    collection: string;
    embedding_model: string;
    revision: string;
    detail: string;
    report: BuildReport | null;
  } | null;
};

export async function corpusCommand(
  key: string,
  payload: object,
  signal?: AbortSignal,
): Promise<CorpusState> {
  const response = await fetch("/api/corpus", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
    body: JSON.stringify(payload),
    cache: "no-store",
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
      : AbortSignal.timeout(30000),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(typeof value.detail === "string"
      ? value.detail : `Solicitud rechazada (HTTP ${response.status})`);
  return value as CorpusState;
}
