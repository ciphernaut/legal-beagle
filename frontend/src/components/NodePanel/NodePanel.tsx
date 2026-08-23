import { useEffect, useState } from "react";
import { getNode } from "../../api/client";
import type { NodeDetail, NodeRef } from "../../api/types";
import ProvenanceBadge from "../ProvenanceBadge";
import "./NodePanel.css";

interface Props { selected: NodeRef | null; onNavigate: (ref: NodeRef) => void }

export default function NodePanel({ selected, onNavigate }: Props) {
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    let cancelled = false;
    setDetail(null);
    setError(null);
    getNode(selected.type, selected.id)
      .then((d) => !cancelled && setDetail(d))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [selected?.type, selected?.id]);

  if (!selected) return <p className="node-empty">Select a node in the tree.</p>;
  if (error) return <p role="alert" className="node-error">Could not load node: {error}</p>;
  if (!detail) return <p className="node-loading">Loading {selected.label}…</p>;

  return (
    <section className="node-panel">
      <h2>{detail.label}</h2>
      <p className="node-meta">{detail.type} #{detail.id}</p>
      {detail.text && <pre className="node-text">{detail.text}</pre>}
      <h3>Relationships</h3>
      {detail.neighbours.length === 0 ? (
        <p>No recorded relationships.</p>
      ) : (
        <ul className="neighbours">
          {detail.neighbours.map((n, i) => (
            <li key={i}>
              <span className="nb-dir" aria-hidden="true">{n.direction === "out" ? "→" : "←"}</span>
              <span className="nb-kind">{n.kind}</span>
              {n.treatment && <span className="nb-treatment">({n.treatment})</span>}
              <button type="button" className="nb-label" onClick={() => onNavigate(n.node)}>{n.node.label}</button>
              <ProvenanceBadge extraction={n.extraction} confidence={n.confidence} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
