// Test-only upstream. Never imported by the application; no model quality claims.
import { createServer } from "node:http";

const evidence = {
  score: 0.9,
  chunk: {
    id: "a".repeat(64),
    document_id: "b".repeat(64),
    text: "Exact official evidence.",
    section_path: ["Tax"],
    metadata: {
      title: "Official tax source",
      source_url: "https://www.skatteetaten.no/en/taxes/",
      tax_year: 2025,
      language: "en",
    },
  },
};
createServer(async (request, response) => {
  response.setHeader("Content-Type", "application/json");
  response.setHeader(
    "X-Trace-ID",
    request.url === "/v1/query" ? "answer-trace" : "retrieval-trace",
  );
  response.setHeader("X-Request-ID", "test-request");
  if (request.method === "GET") return response.end("{}");
  let body = "";
  for await (const part of request) body += part;
  const payload = JSON.parse(body);
  const question = payload.question || payload.query;
  if (question === "unavailable") {
    response.statusCode = 503;
    return response.end('{"detail":"configured service unavailable"}');
  }
  if (question === "bad-json") return response.end("not JSON");
  if (question === "echo")
    return response.end(
      JSON.stringify({ payload, cookie: request.headers.cookie || null }),
    );
  if (question === "slow")
    await new Promise((resolve) => setTimeout(resolve, 600));
  if (request.url === "/v1/retrieve")
    return response.end(
      JSON.stringify({
        mode: "all",
        results: [],
        stages: Object.fromEntries(
          ["dense", "sparse", "fused", "reranked"].map((stage) => [
            stage,
            question === "empty" ? [] : [evidence],
          ]),
        ),
      }),
    );
  const result = {
    status: "answered",
    evidence_count: 1,
    clarification_questions: [],
    error: null,
    generator_model: "test-only",
    routing: { action: "retrieve", tax_year: payload.tax_year },
    final_context: payload.include_context
      ? { evidence: [{ ...evidence, evidence_id: "S1" }] }
      : null,
  };
  result.answer = {
    answer: `Test answer in ${payload.response_language}. [S1]`,
    tax_year: payload.tax_year,
    confidence: "low",
    warnings: ["Verify the source."],
    missing_information: [],
    citations: [
      {
        citation_id: "S1",
        chunk_id: evidence.chunk.id,
        source_title: evidence.chunk.metadata.title,
        source_url:
          question === "unsafe"
            ? "javascript:alert(1)"
            : evidence.chunk.metadata.source_url,
      },
    ],
  };
  if (question === "clarify") {
    result.status = "clarification_required";
    result.answer = null;
    result.clarification_questions = ["Which tax year?"];
  }
  if (question === "abstain") {
    result.status = "abstained";
    result.answer.answer = "Insufficient evidence.";
    result.answer.citations = [];
  }
  response.end(JSON.stringify(result));
}).listen(18001, "127.0.0.1");
