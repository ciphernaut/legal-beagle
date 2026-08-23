import { SseParser, streamReverse, toReasoningEvent } from "./sse";
import type { ReasoningEvent } from "./types";

const body = [
  'event: context\ndata: {"nodes":[{"type":"case","id":100,"label":"Mabo","via":"root"}]}\n\n',
  'event: token\ndata: {"text":"## Prec"}\n\n',
  'event: token\ndata: {"text":"edent"}\n\n',
  'event: verification\ndata: {"precision":0.5,"citations":[{"raw":"[1992] HCA 23","status":"resolved","node":{"type":"case","id":100,"label":"Mabo"}},{"raw":"[1950] HCA 99","status":"unresolved","node":null}]}\n\n',
  'event: done\ndata: {"answer":"## Precedent"}\n\n',
].join("");

test("SseParser splits blocks and survives partial chunks", () => {
  const p = new SseParser();
  const first = p.push(body.slice(0, 40));
  expect(first).toEqual([]);
  const rest = p.push(body.slice(40));
  expect(rest.map((m) => m.event)).toEqual(["context", "token", "token", "verification", "done"]);
  expect(p.flush()).toEqual([]);
});

test("SseParser tolerates CRLF separators and flushes a trailing block", () => {
  const p = new SseParser();
  expect(p.push('event: token\r\ndata: {"text":"a"}\r\n\r\nevent: done\r\ndata: {"answer":"a"}')).toHaveLength(1);
  expect(p.flush()).toEqual([{ event: "done", data: '{"answer":"a"}' }]);
});

test("toReasoningEvent parses payloads and rejects unknown kinds", () => {
  const ev = toReasoningEvent({ event: "token", data: '{"text":"x"}' });
  expect(ev).toEqual({ kind: "token", payload: { text: "x" } });
  expect(() => toReasoningEvent({ event: "bogus", data: "{}" })).toThrow(/unknown/i);
});

function streamingResponse(text: string, chunk = 7): Response {
  const enc = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i >= text.length) return controller.close();
      controller.enqueue(enc.encode(text.slice(i, i + chunk)));
      i += chunk;
    },
  });
  return new Response(stream, { status: 200, headers: { "content-type": "text/event-stream" } });
}

test("streamReverse posts the request and emits events in order", async () => {
  const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ node_type: "case", node_id: 100, framework: "common_law" });
    return streamingResponse(body);
  });
  vi.stubGlobal("fetch", fetchMock);
  const seen: ReasoningEvent[] = [];
  await streamReverse({ node_type: "case", node_id: 100 }, (ev) => seen.push(ev));
  expect(seen.map((e) => e.kind)).toEqual(["context", "token", "token", "verification", "done"]);
  expect(fetchMock.mock.calls[0][0]).toBe("/api/reason/reverse");
});

test("streamReverse throws ApiError on a non-2xx response", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response('{"detail":"node not found"}', { status: 404 })));
  await expect(streamReverse({ node_type: "case", node_id: 1 }, () => {})).rejects.toMatchObject({ status: 404 });
});
