export type Language = "en" | "nb" | "es";
export type Mode = "dense" | "hybrid" | "reranked";
export type Citation = {
  citation_id: string;
  chunk_id: string;
  source_title: string | null;
  source_url: string;
};
export type Answer = {
  answer: string;
  tax_year: number | null;
  citations: Citation[];
  confidence: string;
  missing_information: string[];
  warnings: string[];
};
export type QueryResult = {
  status: "answered" | "clarification_required" | "abstained" | "failed";
  answer: Answer | null;
  clarification_questions: string[];
  evidence_count: number;
  routing: unknown;
  generator_model: string | null;
  error: string | null;
  final_context?: { evidence: (Evidence & { evidence_id: string })[] } | null;
};
export type Evidence = {
  score: number;
  chunk: {
    id: string;
    document_id: string;
    text: string;
    section_path: string[];
    metadata: {
      title: string | null;
      source_url: string;
      tax_year: number | null;
      language: string | null;
    };
  };
};
export type RetrievalResult = {
  mode: string;
  results: Evidence[];
  stages: Record<string, Evidence[]> | null;
};

export function safeSourceUrl(value: string): string | undefined {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : undefined;
  } catch {
    return undefined;
  }
}

export async function post<T>(
  operation: "query" | "retrieve",
  payload: object,
): Promise<{ data: T; trace: string | null }> {
  const response = await fetch(`/api/${operation}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(190000),
  });
  if (!response.ok)
    throw new Error(
      `HTTP ${response.status}${response.headers.get("x-trace-id") ? ` · trace ${response.headers.get("x-trace-id")}` : ""}`,
    );
  return {
    data: (await response.json()) as T,
    trace: response.headers.get("x-trace-id"),
  };
}
