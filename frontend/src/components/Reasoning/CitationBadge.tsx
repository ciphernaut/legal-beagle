import type { Citation, CitationStatus } from "../../api/types";

export const STATUS_META: Record<CitationStatus, { icon: string; label: string }> = {
  resolved: { icon: "✅", label: "Verified (in context)" },
  resolved_outside_context: { icon: "⚠️", label: "Real, but not in the provided context" },
  unresolved: { icon: "❌", label: "Not found in corpus — treat as unverified" },
  unverifiable: { icon: "❔", label: "Cannot be checked (reported citation)" },
};

export default function CitationBadge({ citation }: { citation: Citation }) {
  const meta = STATUS_META[citation.status];
  return (
    <span className={`cite cite-${citation.status}`} title={meta.label}>
      <span aria-hidden="true">{meta.icon}</span> <code>{citation.raw}</code>
      {citation.node && <small> — {citation.node.label}</small>}
    </span>
  );
}
