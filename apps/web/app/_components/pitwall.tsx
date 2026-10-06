"use client";

import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import type { PageContext, QueryResponse } from "../_lib/pitwall-contracts";
import { pitwallError, queryRequest } from "../_lib/pitwall";
import { askPitwall } from "../pitwall/actions";
import { PitwallAnswer } from "./pitwall-answer";
import "../pitwall/pitwall.css";

interface Props {
  context: PageContext;
  label: string;
  contextDetails?: { label: string; value: string }[];
  suggestions: string[];
  names?: Record<string, string>;
  selectionKey?: string;
  questionScope?: string;
}
export function Pitwall(props: Props) {
  // A new selection owns a new question/answer. No response can cross contexts.
  return (
    <PitwallPanel
      key={JSON.stringify([
        props.context,
        props.label,
        props.contextDetails,
        props.selectionKey,
        props.questionScope,
      ])}
      {...props}
    />
  );
}
function PitwallPanel({
  context,
  label,
  contextDetails = [],
  suggestions,
  names = {},
  questionScope,
}: Props) {
  const prefix = useId();
  const current = useRef(0);
  const [question, setQuestion] = useState("");
  const [asked, setAsked] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  useEffect(
    () => () => {
      current.current += 1;
    },
    [],
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    let request;
    try {
      if (!question.trim()) throw new Error("Empty question");
      request = queryRequest(
        questionScope ? `${questionScope}\n\n${question.trim()}` : question,
        context,
      );
    } catch {
      setError("Enter a question of up to 4,000 characters.");
      return;
    }
    const sequence = ++current.current;
    setPending(true);
    setError(null);
    setResponse(null);
    setAsked(question.trim());
    try {
      const result = await askPitwall(request);
      if (sequence !== current.current) return;
      if (result.error) setError(result.error);
      else if (result.response) setResponse(result.response);
    } catch {
      if (sequence === current.current) setError(pitwallError(503));
    } finally {
      if (sequence === current.current) setPending(false);
    }
  }
  return (
    <section
      id="pitwall"
      className="pitwall"
      aria-labelledby={`${prefix}-heading`}
    >
      <div className="section-heading">
        <h2 id={`${prefix}-heading`}>Ask Pitwall</h2>
        <span className="muted">Analysis from recorded data</span>
      </div>
      <div className="pitwall-layout">
        <div className="pitwall-question">
          <div className="pitwall-context" aria-label="Active analysis context">
            <p className="pitwall-context-title">{label}</p>
            {contextDetails.length > 0 && (
              <dl>
                {contextDetails.map((detail) => (
                  <div key={detail.label}>
                    <dt>{detail.label}</dt>
                    <dd>{detail.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
          <form onSubmit={submit} aria-busy={pending}>
            <label htmlFor={`${prefix}-question`}>Your question</label>
            <textarea
              id={`${prefix}-question`}
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={4000 - (questionScope ? questionScope.length + 2 : 0)}
              required
              rows={4}
              disabled={pending}
              aria-describedby={`${prefix}-help`}
              placeholder="What do the recorded data show?"
            />
            <p className="pitwall-note" id={`${prefix}-help`}>
              Facts and calculations use retrieved records. Missing data stays
              unavailable.
            </p>
            <button
              className="button"
              type="submit"
              disabled={pending || !question.trim()}
            >
              {pending
                ? "Preparing analysis…"
                : error
                  ? "Ask again"
                  : "Ask Pitwall"}
            </button>
          </form>
          <div className="pitwall-suggestions" aria-label="Suggested questions">
            {suggestions.map((suggestion) => (
              <button
                className="pitwall-suggestion"
                key={suggestion}
                type="button"
                disabled={pending}
                onClick={() => {
                  setQuestion(suggestion);
                  document.getElementById(`${prefix}-question`)?.focus();
                }}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
        <div className="pitwall-result" aria-busy={pending}>
          <p role="status" aria-live="polite" className="pitwall-note">
            {pending
              ? "Retrieving recorded data and preparing analysis. This can take a minute."
              : response
                ? response.status === "answered"
                  ? "Analysis ready."
                  : "Insufficient data for this question."
                : ""}
          </p>
          {error ? (
            <div role="alert" className="pitwall-answer-group">
              <h3>Analysis unavailable</h3>
              <p>{error}</p>
            </div>
          ) : response ? (
            <>
              <p className="pitwall-asked">
                <strong>Your question</strong>
                <br />
                {asked}
              </p>
              <PitwallAnswer
                response={response}
                names={names}
                prefix={prefix}
              />
            </>
          ) : (
            !pending && (
              <div className="pitwall-ready">
                <h3>Start with a question.</h3>
                <p>
                  Explore the records behind this page. Pitwall separates source
                  data, calculations and interpretation.
                </p>
                <p className="pitwall-note">
                  Public race data cannot confirm team intent or private
                  engineering channels.
                </p>
              </div>
            )
          )}
        </div>
      </div>
    </section>
  );
}
