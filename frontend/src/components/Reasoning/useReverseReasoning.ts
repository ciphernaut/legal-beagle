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

/**
 * @param selectedKey identifies the node the panel is showing (`"type:id"`, or null for no
 *   selection). When it changes, any in-flight run is cancelled and the state is cleared, so
 *   reasoning about one node can never linger next to another node's details.
 */
export function useReverseReasoning(selectedKey: string | null) {
  const [state, setState] = useState<ReasoningState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  useEffect(() => cancel, [cancel]);

  useEffect(() => {
    cancel();
    setState(INITIAL); // same reference on mount ⇒ React bails out, no extra render
  }, [selectedKey, cancel]);

  const run = useCallback((ref: NodeRef) => {
    cancel();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ ...INITIAL, phase: "streaming" });

    const isActive = () => abortRef.current === controller;

    const apply = (ev: ReasoningEvent) => {
      if (!isActive()) return;
      setState((s) => {
        switch (ev.kind) {
          case "context": return { ...s, context: ev.payload.nodes };
          case "token": return { ...s, answer: s.answer + ev.payload.text };
          case "verification": return { ...s, verification: ev.payload };
          case "done":
            if (s.phase === "error") return s;
            // A `done` with no preceding `verification` means nothing was checked: the answer
            // stays visible, but it must never be presented as verified.
            if (!s.verification) {
              return { ...s, phase: "error", error: "stream ended without verification", answer: ev.payload.answer };
            }
            return { ...s, phase: "verified", answer: ev.payload.answer };
          case "error": return { ...s, phase: "error", error: ev.payload.message };
        }
      });
    };

    streamReverse({ node_type: ref.type, node_id: ref.id }, apply, controller.signal)
      .then(() => {
        if (!isActive()) return;
        setState((s) => (s.phase === "streaming" ? { ...s, phase: "error", error: "stream ended before verification" } : s));
      })
      .catch((e: Error) => {
        if (e.name === "AbortError") {
          // Only an explicit cancel() with no subsequent run() leaves abortRef.current null;
          // a stale abort from a superseded run (abortRef.current is a *different* controller,
          // or this run is still active — which shouldn't happen for a real abort) must not
          // clobber whatever the active run has since done.
          // On a real cancel, drop everything: partial model text has not been citation-checked,
          // and leaving it on screen with no badges would read as if it had been.
          if (abortRef.current === null) setState(INITIAL);
          return;
        }
        if (!isActive()) return;
        setState((s) => ({ ...s, phase: "error", error: e.message }));
      });
  }, [cancel]);

  return { state, run, cancel };
}
