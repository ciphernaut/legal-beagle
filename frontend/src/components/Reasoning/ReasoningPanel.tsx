import type { NodeRef } from "../../api/types";
import CitationBadge from "./CitationBadge";
import { useReverseReasoning } from "./useReverseReasoning";
import "./Reasoning.css";

export default function ReasoningPanel({ selected }: { selected: NodeRef | null }) {
  const { state, run, cancel } = useReverseReasoning(selected ? `${selected.type}:${selected.id}` : null);
  const streaming = state.phase === "streaming";
  const checkable = state.verification ? state.verification.citations.filter((c) => c.status !== "unverifiable") : [];
  const resolvedCount = checkable.filter((c) => c.status !== "unresolved").length;

  return (
    <section className="reasoning">
      <div className="reasoning-controls">
        <button type="button" disabled={!selected || streaming} onClick={() => selected && run(selected)}>
          Explain the chain of authority
        </button>
        {streaming && <button type="button" onClick={cancel}>Cancel</button>}
      </div>

      {state.context.length > 0 && (
        <ul className="context" aria-label="Context supplied to the model">
          {state.context.map((n) => (
            <li key={`${n.type}:${n.id}`} className={`ctx ctx-${n.via}`}>{n.label} · {n.via}</li>
          ))}
        </ul>
      )}

      {streaming && <p role="status" className="unverified">Streaming — citations not yet verified</p>}
      {state.phase === "error" && (
        <>
          <p role="alert" className="reasoning-error">{state.error}</p>
          {state.answer && <p className="unverified">The text below was not verified.</p>}
        </>
      )}

      {state.answer && <div className="answer">{state.answer}</div>}

      {state.verification && state.phase === "verified" && (
        <div className="verification">
          <p className="precision">
            Citation precision: {Math.round(state.verification.precision * 100)}% ({resolvedCount} of {checkable.length} checkable)
          </p>
          <ul className="citations">
            {state.verification.citations.map((c, i) => (
              <li key={i}><CitationBadge citation={c} /></li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
