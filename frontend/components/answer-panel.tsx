import { QueryResult, safeSourceUrl } from "../lib/contracts";
import { Labels } from "../lib/labels";
import { RetrievalInspector } from "./retrieval-inspector";

export function AnswerPanel({
  result,
  trace,
  text,
}: {
  result: QueryResult;
  trace: string | null;
  text: Labels;
}) {
  const answer = result.answer;
  return (
    <section className="panel answer" aria-label={text.answer}>
      <span className={`badge ${result.status}`}>{text[result.status]}</span>
      {result.clarification_questions.map((question, i) => (
        <p key={i}>{question}</p>
      ))}
      {answer ? (
        <>
          <p className="answer-text">{answer.answer}</p>
          <p className="metadata">
            {text.year}: {answer.tax_year ?? "—"} · {text.confidence}:{" "}
            {answer.confidence}
          </p>
          {answer.warnings.length > 0 ? (
            <>
              <h3>{text.warnings}</h3>
              <ul>
                {answer.warnings.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </>
          ) : null}
          {answer.missing_information.length > 0 ? (
            <>
              <h3>{text.missing}</h3>
              <ul>
                {answer.missing_information.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </>
          ) : null}
          {answer.citations.length > 0 ? (
            <>
              <h3>{text.sources}</h3>
              <div className="sources">
                {answer.citations.map((source) => {
                  const url = safeSourceUrl(source.source_url);
                  return (
                    <article className="source" key={source.citation_id}>
                      <span className="source-id">[{source.citation_id}]</span>
                      <div>
                        {url ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {source.source_title || source.source_url} ↗
                          </a>
                        ) : (
                          <span>
                            {source.source_title || source.source_url}
                          </span>
                        )}
                        <p className="source-url">{source.source_url}</p>
                        <code>{source.chunk_id}</code>
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          ) : null}
        </>
      ) : null}
      <p className="metadata">
        {text.evidence}: {result.evidence_count}
        {trace ? ` · Trace: ${trace}` : ""}
      </p>
      {result.routing ? (
        <details>
          <summary>{text.routing}</summary>
          <pre>{JSON.stringify(result.routing, null, 2)}</pre>
        </details>
      ) : null}
      {result.final_context ? (
        <details>
          <summary>{text.finalContext}</summary>
          <p className="help">
            {result.final_context.evidence
              .map((item) => `[${item.evidence_id}] ${item.chunk.id}`)
              .join("\n")}
          </p>
          <RetrievalInspector
            text={text}
            result={{
              mode: "context",
              stages: null,
              results: result.final_context.evidence,
            }}
          />
        </details>
      ) : null}
    </section>
  );
}
