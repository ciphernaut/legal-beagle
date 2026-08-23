import { renderHook, act, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { useReverseReasoning } from "./useReverseReasoning";

const okStream = 'event: verification\ndata: {"precision":1,"citations":[]}\n\nevent: done\ndata: {"answer":"ok"}\n\n';

function sse(text: string): Response {
  return new Response(new TextEncoder().encode(text), { status: 200, headers: { "content-type": "text/event-stream" } });
}

function fetchThatRejectsOnAbort(_url: string, init?: RequestInit): Promise<Response> {
  return new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => {
      reject(new DOMException("Aborted", "AbortError"));
    });
  });
}

test("a stale aborted run does not clobber a newer run's state", async () => {
  const fetchMock = vi
    .fn()
    .mockImplementationOnce(fetchThatRejectsOnAbort)
    .mockImplementationOnce(async () => sse(okStream));
  vi.stubGlobal("fetch", fetchMock);

  const { result } = renderHook(() => useReverseReasoning());

  act(() => {
    result.current.run({ type: "case", id: 1, label: "x" });
  });
  expect(result.current.state.phase).toBe("streaming");

  // Starting a second run aborts the first; the first run's fetch promise rejects with
  // AbortError asynchronously, after the second run is already under way.
  act(() => {
    result.current.run({ type: "case", id: 2, label: "y" });
  });
  expect(result.current.state.phase).toBe("streaming");

  await waitFor(() => expect(result.current.state.phase).toBe("verified"));
  // Give the stale first-run rejection a chance to be processed; it must not have reset phase.
  await Promise.resolve();
  expect(result.current.state.phase).toBe("verified");
});

test("cancel() alone moves phase to idle", async () => {
  const fetchMock = vi.fn().mockImplementationOnce(fetchThatRejectsOnAbort);
  vi.stubGlobal("fetch", fetchMock);

  const { result } = renderHook(() => useReverseReasoning());

  act(() => {
    result.current.run({ type: "case", id: 1, label: "x" });
  });
  expect(result.current.state.phase).toBe("streaming");

  act(() => {
    result.current.cancel();
  });

  await waitFor(() => expect(result.current.state.phase).toBe("idle"));
});
