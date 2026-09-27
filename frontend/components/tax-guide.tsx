"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  Language,
  Mode,
  QueryResult,
  RetrievalResult,
  post,
} from "../lib/contracts";
import { labels } from "../lib/labels";
import { AnswerPanel } from "./answer-panel";
import { RetrievalInspector } from "./retrieval-inspector";

export function TaxGuide() {
  const [language, setLanguage] = useState<Language>("en");
  const [question, setQuestion] = useState("");
  const [year, setYear] = useState("");
  const [mode, setMode] = useState<Mode>("dense");
  const [includeContext, setIncludeContext] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [retrieval, setRetrieval] = useState<RetrievalResult | null>(null);
  const [trace, setTrace] = useState<string | null>(null);
  const [retrievalTrace, setRetrievalTrace] = useState<string | null>(null);
  const text = labels[language];
  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  function clearResults() {
    setResult(null);
    setRetrieval(null);
    setError("");
    setTrace(null);
    setRetrievalTrace(null);
  }
  async function run(inspect: boolean) {
    if (!question.trim() || busy) return;
    setError("");
    setBusy(true);
    if (inspect) {
      setRetrieval(null);
      setRetrievalTrace(null);
    } else {
      setResult(null);
      setTrace(null);
    }
    try {
      const tax_year = year ? Number(year) : null;
      if (inspect) {
        const response = await post<RetrievalResult>("retrieve", {
          query: question.trim(),
          tax_year,
          mode: "all",
          limit: 5,
        });
        setRetrieval(response.data);
        setRetrievalTrace(response.trace);
      } else {
        const response = await post<QueryResult>("query", {
          question: question.trim(),
          tax_year,
          mode,
          response_language: language,
          include_context: includeContext,
          retrieval_limit: 5,
        });
        setResult(response.data);
        setTrace(response.trace);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void run(false);
  }

  return (
    <>
      <header className="topbar">
        <a href="/" className="brand">
          <span className="brand-mark">T</span> TaxGuide <span>Norway</span>
        </a>
        <span className="version">RESEARCH PREVIEW · v0.9</span>
        <a href="/settings">{text.settings}</a>
        <a href="/crawler">Corpus / Crawler</a>
      </header>
      <main>
        <div className="intro">
          <p className="eyebrow">{text.eyebrow}</p>
          <h1>{text.title}</h1>
          <p>{text.intro}</p>
        </div>
        <div className="workspace">
          <form className="panel question-panel" onSubmit={submit}>
            <fieldset disabled={busy}>
              <label htmlFor="question">{text.question}</label>
              <textarea
                id="question"
                required
                maxLength={4000}
                rows={6}
                value={question}
                placeholder={text.placeholder}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  clearResults();
                }}
              />
              <div className="controls">
                <div>
                  <label htmlFor="year">{text.year}</label>
                  <input
                    id="year"
                    type="number"
                    min={1900}
                    max={2100}
                    step={1}
                    placeholder={text.unspecified}
                    value={year}
                    onChange={(event) => {
                      setYear(event.target.value);
                      clearResults();
                    }}
                  />
                </div>
                <div>
                  <label htmlFor="language">{text.language}</label>
                  <select
                    id="language"
                    value={language}
                    onChange={(event) => {
                      setLanguage(event.target.value as Language);
                      clearResults();
                    }}
                  >
                    <option value="en">English</option>
                    <option value="nb">Norsk bokmål</option>
                    <option value="es">Español</option>
                  </select>
                </div>
              </div>
              <p className="help">{text.yearNote}</p>
              <button
                className="primary"
                disabled={!question.trim()}
                type="submit"
              >
                {busy ? text.loading : text.ask}
                <span aria-hidden="true"> →</span>
              </button>
              <p className="help">{text.privacy}</p>
              <details className="developer">
                <summary>{text.developer}</summary>
                <p className="help">{text.inspectorNote}</p>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={includeContext}
                    onChange={(event) => {
                      setIncludeContext(event.target.checked);
                      clearResults();
                    }}
                  />
                  {text.includeContext}
                </label>
                <label htmlFor="mode">{text.mode}</label>
                <select
                  id="mode"
                  value={mode}
                  onChange={(event) => {
                    setMode(event.target.value as Mode);
                    clearResults();
                  }}
                >
                  <option value="dense">Dense</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="reranked">Hybrid + rerank</option>
                </select>
                <button
                  type="button"
                  disabled={!question.trim()}
                  onClick={(event) => {
                    if (event.currentTarget.form?.reportValidity())
                      void run(true);
                  }}
                >
                  {text.inspect}
                </button>
              </details>
            </fieldset>
          </form>
          <div className="result-area" aria-live="polite" aria-busy={busy}>
            {busy ? (
              <div className="panel empty" role="status">
                {text.loading}
              </div>
            ) : null}
            {error ? (
              <div className="panel error" role="alert">
                <h2>{text.failed}</h2>
                <p>{text.error}</p>
                <code>{error}</code>
              </div>
            ) : null}
            {result ? (
              <AnswerPanel result={result} trace={trace} text={text} />
            ) : null}
            {retrieval ? (
              <section className="panel">
                <h2>{text.developer}</h2>
                <p className="help">{text.inspectorNote}</p>
                <RetrievalInspector result={retrieval} text={text} />
                {retrievalTrace ? (
                  <p className="metadata">Trace: {retrievalTrace}</p>
                ) : null}
              </section>
            ) : null}
            {!busy && !error && !result && !retrieval ? (
              <div className="panel empty">
                <span className="empty-symbol" aria-hidden="true">
                  §
                </span>
                <p>{text.empty}</p>
              </div>
            ) : null}
          </div>
        </div>
        <footer>{text.disclaimer}</footer>
      </main>
    </>
  );
}
