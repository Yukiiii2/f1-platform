import type { GroundedValue, QueryResponse } from "../_lib/pitwall-contracts";
import {
  displayValue,
  evidenceTitle,
  formatValue,
  unavailableLabel,
  valueField,
  valueLabel,
} from "../_lib/pitwall";

export function PitwallAnswer({
  response,
  names,
  prefix,
}: {
  response: QueryResponse;
  names: Record<string, string>;
  prefix: string;
}) {
  function citation(id: string) {
    const number = response.evidence.findIndex((row) => row.id === id) + 1;
    return number > 0 ? (
      <a
        className="pitwall-citation"
        href={`#${prefix}-evidence-${number}`}
        aria-label={`Evidence ${number}`}
        onClick={() => {
          const details = document
            .getElementById(`${prefix}-evidence-${number}`)
            ?.closest("details");
          if (details) details.open = true;
        }}
      >
        [{number}]
      </a>
    ) : null;
  }
  function values(
    title: string,
    rows: GroundedValue[],
    classification: GroundedValue["classification"],
  ) {
    const visible = rows.filter(
      (row) => row.classification === classification && displayValue(row),
    );
    return (
      visible.length > 0 && (
        <div className={`pitwall-answer-group pitwall-${classification}`}>
          <h3>{title}</h3>
          <dl className="pitwall-values">
            {visible.map((row, index) => (
              <div key={`${row.evidence_id}:${row.pointer}:${index}`}>
                <dt>
                  {valueLabel(row, response.evidence, names)}{" "}
                  {citation(row.evidence_id)}
                </dt>
                <dd>{formatValue(valueField(row.pointer), row.value)}</dd>
              </div>
            ))}
          </dl>
          {classification === "estimate" && (
            <p className="pitwall-note">
              Estimated values are not official telemetry.
            </p>
          )}
        </div>
      )
    );
  }
  const visible = [
    ...response.facts,
    ...response.calculations,
    ...response.estimates,
  ].filter(displayValue);
  const hasDelta = visible.some((row) =>
    valueField(row.pointer).endsWith("delta_ms"),
  );
  return (
    <div className="pitwall-answer">
      {values("Source data", response.facts, "source")}
      {values("Calculated", response.calculations, "derived")}
      {hasDelta && (
        <p className="pitwall-note">
          Timing deltas are A − B: positive means A is slower; negative means A
          is faster.
        </p>
      )}
      {values("Estimate", response.estimates, "estimate")}
      {response.interpretations.length > 0 && (
        <div className="pitwall-answer-group">
          <h3>AI analysis</h3>
          {response.interpretations.map((row, index) => (
            <p key={index}>
              {row.text}{" "}
              {row.evidence_ids.map((id) => (
                <span key={id}>{citation(id)} </span>
              ))}
            </p>
          ))}
          <p className="pitwall-note">
            Not confirmed team intent. Interpretation does not establish cause.
          </p>
        </div>
      )}
      {(response.unavailable.length > 0 ||
        response.status === "unavailable" ||
        (!visible.length && !response.interpretations.length)) && (
        <div className="pitwall-answer-group">
          <h3>Unavailable</h3>
          {response.unavailable.length ? (
            <ul>
              {[
                ...new Set(
                  response.unavailable.map((message) =>
                    unavailableLabel(message, response.evidence, names),
                  ),
                ),
              ].map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          ) : (
            <p>
              No supported answer is available for this question. Try another
              session or a more specific question.
            </p>
          )}
        </div>
      )}
      {response.evidence.length > 0 && (
        <details className="pitwall-evidence">
          <summary>Retrieved evidence ({response.evidence.length})</summary>
          <ol>
            {response.evidence.map((row, index) => (
              <li
                key={row.id}
                id={`${prefix}-evidence-${index + 1}`}
                tabIndex={-1}
              >
                <strong>{evidenceTitle(row.tool)}</strong> ·{" "}
                {row.status === "available" ? "Retrieved" : "Unavailable"}
                {row.truncated && (
                  <span className="pitwall-note">
                    Partial records. This answer does not establish full
                    coverage.
                  </span>
                )}
              </li>
            ))}
          </ol>
        </details>
      )}
    </div>
  );
}
