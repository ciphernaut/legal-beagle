import type { Extraction } from "../api/types";
import "./ProvenanceBadge.css";

const TITLES: Record<Extraction, string> = {
  curated: "Curated by a human",
  parsed: "Parsed from the source text",
  llm_extracted: "Inferred by the model — lower confidence",
};

export default function ProvenanceBadge({ extraction, confidence }: { extraction: Extraction; confidence: number }) {
  return (
    <span className={`prov prov-${extraction}`} title={TITLES[extraction]}>
      {extraction} · {confidence.toFixed(2)}
    </span>
  );
}
