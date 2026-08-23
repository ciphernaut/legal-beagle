import { useCallback, useEffect, useRef, useState } from "react";
import { streamReverse } from "../../api/sse";
import type { Citation, ContextNode, NodeRef, ReasoningEvent } from "../../api/types";

export type Phase = "idle" | "streaming" | "verified" | "error";

export interface ReasoningState {
  phase: Phase;
  context: ContextNode[];
  answer: string;
  verification: { precision: number; citations: Citation[] } | null;
  error: string | null;
}

const INITIAL: ReasoningState = { phase: "idle", context: [], answer: "", verification: null, error: null };

export function useReverseReasoning() {
  const [state, setState] = useState<ReasoningState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  useEffect(() => cancel, [cancel]);

  const run = useCallback((ref: NodeRef) => {
    cancel();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ ...INITIAL, phase: "streaming" });

    const apply = (ev: ReasoningEvent) =>
      setState((s) => {
        switch (ev.kind) {
          case "context": return { ...s, context: ev.payload.nodes };
          case "token": return { ...s, answer: s.answer + ev.payload.text };
          case "verification": return { ...s, verification: ev.payload };
          case "done": return s.phase === "error" ? s : { ...s, phase: "verified", answer: ev.payload.answer };
          case "error": return { ...s, phase: "error", error: ev.payload.message };
        }
      });

    streamReverse({ node_type: ref.type, node_id: ref.id }, apply, controller.signal)
      .then(() => setState((s) => (s.phase === "streaming" ? { ...s, phase: "error", error: "stream ended before verification" } : s)))
      .catch((e: Error) => {
        if (e.name === "AbortError") return setState((s) => ({ ...s, phase: "idle" }));
        setState((s) => ({ ...s, phase: "error", error: e.message }));
      });
  }, [cancel]);

  return { state, run, cancel };
}
