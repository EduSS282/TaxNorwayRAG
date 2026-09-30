import { RetrievalResult, safeSourceUrl } from "../lib/contracts";
import { Labels } from "../lib/labels";

export function RetrievalInspector({
  result,
  text,
}: {
  result: RetrievalResult;
  text: Labels;
}) {
  const stages = result.stages || { [result.mode]: result.results };
  return (
    <div className="stages">
      {Object.entries(stages).map(([name, items]) => (
        <section key={name}>
          <h3>
            {name} <span className="metadata">({items.length})</span>
          </h3>
          {items.length === 0 ? (
            <p>{text.noEvidence}</p>
          ) : (
            items.map(({ chunk, score }, index) => (
              <details className="evidence" key={`${chunk.id}-${index}`}>
                <summary>
                  #{index + 1} · {score.toFixed(4)} ·{" "}
                  {chunk.metadata.title || chunk.id.slice(0, 12)}
                </summary>
                <p className="metadata">
                  {text.year}: {chunk.metadata.tax_year ?? "—"} ·{" "}
                  {chunk.metadata.language ?? "—"}
                </p>
                {safeSourceUrl(chunk.metadata.source_url) ? (
                  <a
                    href={safeSourceUrl(chunk.metadata.source_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {chunk.metadata.source_url} ↗
                  </a>
                ) : null}
                <p>{chunk.section_path.join(" / ")}</p>
                <p className="answer-text">{chunk.text}</p>
                <code>
                  chunk: {chunk.id}
                  <br />
                  document: {chunk.document_id}
                </code>
              </details>
            ))
          )}
        </section>
      ))}
    </div>
  );
}
