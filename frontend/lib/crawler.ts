export type CrawlSection = {
  id: string;
  title: string;
  url: string;
  languages: string[];
  downloaded: number;
  unavailable: number;
  years: Record<string, number>;
  last_download: string | null;
};

export type CrawlJob = {
  id: string;
  state: string;
  started_at: string;
  finished_at: string | null;
  years: number[];
  max_pages: number;
  max_depth: number;
  detail: string;
  sections: {
    source_id: string;
    state: string;
    fetched: number;
    failed: number;
    skipped: number;
    new: number;
    changed: number;
    unchanged: number;
  }[];
};

export type CrawlState = {
  sections: CrawlSection[] | null;
  invalid_manifests: number;
  job: CrawlJob | null;
};

export function isCrawling(job: CrawlJob | null | undefined) {
  return job?.state === "running" || job?.state === "cancelling";
}

export async function crawlCommand(
  key: string,
  payload: object,
  signal?: AbortSignal,
): Promise<CrawlState> {
  const response = await fetch("/api/crawl", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${key}`,
    },
    body: JSON.stringify(payload),
    cache: "no-store",
    signal: signal
      ? AbortSignal.any([signal, AbortSignal.timeout(30000)])
      : AbortSignal.timeout(30000),
  });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      typeof value.detail === "string"
        ? value.detail
        : `Solicitud rechazada (HTTP ${response.status})`,
    );
  return value as CrawlState;
}
