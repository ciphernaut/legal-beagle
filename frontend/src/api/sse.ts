import { API_BASE, ApiError } from "./client";
import type { NodeType, ReasoningEvent } from "./types";

export interface SseMessage { event: string; data: string }

const KINDS = new Set(["context", "token", "verification", "done", "error"]);

export class SseParser {
  private buffer = "";

  push(chunk: string): SseMessage[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const out: SseMessage[] = [];
    let idx: number;
    while ((idx = this.buffer.indexOf("\n\n")) >= 0) {
      const block = this.buffer.slice(0, idx);
      this.buffer = this.buffer.slice(idx + 2);
      const msg = parseBlock(block);
      if (msg) out.push(msg);
    }
    return out;
  }

  flush(): SseMessage[] {
    const block = this.buffer;
    this.buffer = "";
    const msg = block.trim() ? parseBlock(block) : null;
    return msg ? [msg] : [];
  }
}

function parseBlock(block: string): SseMessage | null {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
  }
  return data.length ? { event, data: data.join("\n") } : null;
}

export function toReasoningEvent(msg: SseMessage): ReasoningEvent {
  if (!KINDS.has(msg.event)) throw new Error(`unknown reasoning event kind: ${msg.event}`);
  return { kind: msg.event, payload: JSON.parse(msg.data) } as ReasoningEvent;
}

export interface ReverseRequest { node_type: NodeType; node_id: number; framework?: string }

export async function streamReverse(
  req: ReverseRequest,
  onEvent: (ev: ReasoningEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE}/reason/reverse`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "text/event-stream" },
    body: JSON.stringify({ framework: "common_law", ...req }),
    signal,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }
  if (!res.body) throw new Error("response has no body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SseParser();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const msg of parser.push(decoder.decode(value, { stream: true }))) onEvent(toReasoningEvent(msg));
  }
  for (const msg of parser.flush()) onEvent(toReasoningEvent(msg));
}
