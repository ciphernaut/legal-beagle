# Phase 1 Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Vite + React + TypeScript web UI that lets a user browse the authority tree (Constitution → provisions → interpreting cases), inspect any node, and run the Reverse Engineering reasoning mode with streamed output where every citation carries a verification badge — behind a persistent "not legal advice" disclaimer.

**Architecture:** A single-page app in `frontend/` talking to the existing FastAPI backend through a Vite dev proxy (`/api/*` → `http://127.0.0.1:8000/*`, so no CORS change is needed). Three thin API modules (typed client, SSE stream parser, types), three feature areas (Tree, NodePanel, Reasoning) plus the Disclaimer, composed in `App.tsx`. No state library — React state + small hooks. Tests are Vitest + React Testing Library with `fetch` stubbed; the SSE parser is pure and unit-tested with hand-built streams.

**Tech Stack:** Node 22 LTS, npm, Vite 6, React 19, TypeScript 5 (strict), Vitest 3, @testing-library/react, jsdom. Plain CSS (one stylesheet per component, no framework).

**Spec:** `docs/superpowers/specs/2026-08-22-legal-introspection-tool-design.md` — §6 (Visualisation Layer: Interactive Tree is the v1 view; Layered Map and Timeline are later phases), plus the three non-negotiable constraints (citation grounding, not-legal-advice disclaimer, provenance). The backend API contract this plan consumes is the one shipped on `main` at `bd2d447`.

## Global Constraints

- Frontend lives in `frontend/`; all commands run from there with `npm`. Node `>=22`.
- TypeScript `strict: true`; `npm run typecheck` (`tsc --noEmit`) must pass; `npm test` (Vitest) must pass with no console errors/warnings in test output.
- API base path is `/api` in the browser; the Vite dev server proxies `/api` → `http://127.0.0.1:8000` and strips the prefix. Never hard-code `localhost:8000` in app code.
- Node type strings: `jurisdiction | court | act | provision | case | principle`. Citation statuses: `resolved | resolved_outside_context | unresolved | unverifiable`. SSE event kinds: `context | token | verification | done | error`.
- Disclaimer copy (verbatim, used in banner and modal): **"Legal Beagle is a research and education tool. It is not legal advice and may be wrong. Every citation is checked against the corpus; treat anything marked unresolved as unverified."**
- Token text streamed from the model is **unverified until the `verification` event arrives**; the UI must say so visibly while streaming.
- Badge semantics (fixed): `resolved` = ✅ "Verified (in context)"; `resolved_outside_context` = ⚠️ "Real, but not in the provided context"; `unresolved` = ❌ "Not found in corpus — treat as unverified"; `unverifiable` = ❔ "Cannot be checked (reported citation)".
- No session/agent identifier trailers in commit messages. Conventional-commit subjects.
- Do not modify `backend/` except where a task explicitly says so (only Task 9 touches CI and README).

---

## File Structure

```
frontend/
├── package.json
├── tsconfig.json
├── tsconfig.node.json
├── vite.config.ts              # dev proxy /api → :8000; vitest config
├── index.html
├── src/
│   ├── main.tsx                # React root
│   ├── App.tsx                 # layout: Disclaimer, Tree (left), NodePanel + ReasoningPanel (right)
│   ├── App.css
│   ├── api/
│   │   ├── types.ts            # NodeRef, TreeNode, NodeDetail, ReasoningEvent payloads
│   │   ├── client.ts           # getTree, getNode, getFrameworks
│   │   └── sse.ts              # parseSse (pure) + streamReverse (fetch + ReadableStream)
│   ├── components/
│   │   ├── Disclaimer/
│   │   │   ├── Disclaimer.tsx   # banner + first-visit modal (localStorage ack)
│   │   │   ├── Disclaimer.css
│   │   │   └── Disclaimer.test.tsx
│   │   ├── Tree/
│   │   │   ├── TreeView.tsx     # loads /tree, owns expand state, emits selection
│   │   │   ├── TreeNode.tsx     # one row: toggle, label, edge badge
│   │   │   ├── Tree.css
│   │   │   └── TreeView.test.tsx
│   │   ├── NodePanel/
│   │   │   ├── NodePanel.tsx    # /nodes detail + neighbours with provenance badges
│   │   │   ├── NodePanel.css
│   │   │   └── NodePanel.test.tsx
│   │   ├── Reasoning/
│   │   │   ├── ReasoningPanel.tsx   # run button, context chips, streamed answer, verification
│   │   │   ├── CitationBadge.tsx    # status → icon + label + tooltip
│   │   │   ├── useReverseReasoning.ts
│   │   │   ├── Reasoning.css
│   │   │   ├── CitationBadge.test.tsx
│   │   │   └── ReasoningPanel.test.tsx
│   │   └── ProvenanceBadge.tsx  # extraction + confidence chip (shared by Tree and NodePanel)
│   └── test/
│       ├── setup.ts             # @testing-library/jest-dom, localStorage reset
│       ├── fixtures.ts          # sample tree/node/SSE data used across tests
│       └── fetchMock.ts         # stubFetch helper
├── src/api/client.test.ts
├── src/api/sse.test.ts
└── src/App.test.tsx
.github/workflows/ci.yml        # + frontend job (Task 9)
README.md                       # + Frontend section (Task 9)
```

---

### Task 1: Frontend scaffold, test harness, dev proxy

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/tsconfig.node.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/test/setup.ts`, `frontend/src/App.test.tsx`, `frontend/.gitignore`

**Interfaces:**
- Produces: `npm run dev` (Vite on 5173 with `/api` proxy), `npm test` (Vitest, jsdom), `npm run typecheck`, `npm run build`.
- Produces: `App` renders an `<h1>Legal Beagle</h1>`.

- [ ] **Step 0: Ensure Node 22 is available**

Run: `node --version || true`. If missing (this dev box has no Node), install user-locally without sudo:
```bash
mkdir -p ~/.local/node && cd ~/.local/node
curl -fsSL https://nodejs.org/dist/v22.12.0/node-v22.12.0-linux-x64.tar.xz | tar -xJ --strip-components=1
mkdir -p ~/.local/bin && ln -sf ~/.local/node/bin/node ~/.local/bin/node && ln -sf ~/.local/node/bin/npm ~/.local/bin/npm && ln -sf ~/.local/node/bin/npx ~/.local/bin/npx
export PATH=~/.local/bin:$PATH; node --version   # v22.12.0
```
(macOS: `brew install node@22`.) Every later command assumes `node`/`npm` on `PATH`.

- [ ] **Step 1: Write package.json and configs**

`frontend/package.json`:
```json
{
  "name": "legal-beagle-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.6.0",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.4",
    "jsdom": "^25.0.1",
    "typescript": "^5.7.2",
    "vite": "^6.0.5",
    "vitest": "^3.0.0"
  }
}
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "vite.config.ts"]
}
```

`frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["vite.config.ts"]
}
```

`frontend/vite.config.ts`:
```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["src/test/setup.ts"],
    css: false,
  },
});
```

`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Legal Beagle</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`frontend/.gitignore`:
```
node_modules/
dist/
```

- [ ] **Step 2: Write main.tsx, App.tsx, App.css, test setup**

`frontend/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./App.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx` (placeholder; replaced in Task 8):
```tsx
export default function App() {
  return (
    <main className="app">
      <h1>Legal Beagle</h1>
    </main>
  );
}
```

`frontend/src/App.css`:
```css
:root { font-family: system-ui, sans-serif; color: #1a1a1a; background: #fafafa; }
body { margin: 0; }
.app { padding: 1rem; }
```

`frontend/src/test/setup.ts`:
```ts
import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});
```

- [ ] **Step 3: Write the failing smoke test**

`frontend/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders the app title", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Legal Beagle" })).toBeInTheDocument();
});
```

- [ ] **Step 4: Install and run**

Run: `cd frontend && npm install && npm test && npm run typecheck`
Expected: 1 test passed; typecheck clean. (First `npm install` downloads ~150 MB.)

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "feat(frontend): Vite + React + TypeScript scaffold with Vitest and API proxy"
```

---

### Task 2: API types and client

**Files:**
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/test/fetchMock.ts`, `frontend/src/test/fixtures.ts`, `frontend/src/api/client.test.ts`

**Interfaces:**
- Produces (types.ts):
  ```ts
  export type NodeType = "jurisdiction" | "court" | "act" | "provision" | "case" | "principle";
  export type Extraction = "curated" | "parsed" | "llm_extracted";
  export interface NodeRef { type: NodeType; id: number; label: string }
  export interface EdgeInfo { kind: string; extraction: Extraction; confidence: number }
  export interface TreeNode { node: NodeRef; edge: EdgeInfo | null; children: TreeNode[] }
  export interface Neighbour { kind: string; direction: "in" | "out"; treatment: string | null; extraction: Extraction; confidence: number; node: NodeRef }
  export interface NodeDetail { type: NodeType; id: number; label: string; text: string; neighbours: Neighbour[] }
  export type CitationStatus = "resolved" | "resolved_outside_context" | "unresolved" | "unverifiable";
  export interface ContextNode extends NodeRef { via: string }
  export interface Citation { raw: string; status: CitationStatus; node: NodeRef | null }
  export type ReasoningEvent =
    | { kind: "context"; payload: { nodes: ContextNode[] } }
    | { kind: "token"; payload: { text: string } }
    | { kind: "verification"; payload: { precision: number; citations: Citation[] } }
    | { kind: "done"; payload: { answer: string } }
    | { kind: "error"; payload: { message: string; verified: false } };
  ```
- Produces (client.ts): `getTree(root: string): Promise<TreeNode>`, `getNode(type: NodeType, id: number): Promise<NodeDetail>`, `getFrameworks(): Promise<string[]>`; all throw `ApiError` (`class ApiError extends Error { status: number }`) on non-2xx. Base path constant `API_BASE = "/api"`.
- Produces (test helpers): `stubFetch(routes: Record<string, { status?: number; body: unknown }>)` — installs `vi.fn` on `globalThis.fetch` keyed by `"METHOD /path"`; returns the mock for assertions. `fixtures.ts` exports `treeFixture: TreeNode`, `nodeFixture: NodeDetail`.

- [ ] **Step 1: Write types.ts** (exactly the block above) and the fixtures/helper

`frontend/src/test/fixtures.ts`:
```ts
import type { NodeDetail, TreeNode } from "../api/types";

export const treeFixture: TreeNode = {
  node: { type: "act", id: 1, label: "Commonwealth of Australia Constitution Act" },
  edge: null,
  children: [
    {
      node: { type: "provision", id: 10, label: "Commonwealth of Australia Constitution Act s51" },
      edge: null,
      children: [],
    },
    {
      node: { type: "provision", id: 12, label: "Commonwealth of Australia Constitution Act s109" },
      edge: null,
      children: [
        {
          node: { type: "case", id: 100, label: "Mabo v Queensland (No 2) [1992] HCA 23" },
          edge: { kind: "INTERPRETS", extraction: "parsed", confidence: 1.0 },
          children: [],
        },
      ],
    },
  ],
};

export const nodeFixture: NodeDetail = {
  type: "case",
  id: 100,
  label: "Mabo v Queensland (No 2) [1992] HCA 23",
  text: "",
  neighbours: [
    { kind: "DECIDED_BY", direction: "out", treatment: null, extraction: "parsed", confidence: 1.0,
      node: { type: "court", id: 1, label: "High Court of Australia" } },
    { kind: "INTERPRETS", direction: "out", treatment: null, extraction: "parsed", confidence: 1.0,
      node: { type: "provision", id: 12, label: "Commonwealth of Australia Constitution Act s109" } },
  ],
};
```

`frontend/src/test/fetchMock.ts`:
```ts
import { vi } from "vitest";

export interface Route { status?: number; body: unknown }

export function stubFetch(routes: Record<string, Route>) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const route = routes[`${method} ${path}`];
    if (!route) return new Response("not found", { status: 404 });
    return new Response(JSON.stringify(route.body), {
      status: route.status ?? 200,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/api/client.test.ts`:
```ts
import { ApiError, getFrameworks, getNode, getTree } from "./client";
import { stubFetch } from "../test/fetchMock";
import { nodeFixture, treeFixture } from "../test/fixtures";

test("getTree hits /api/tree?root=… and returns the tree", async () => {
  const mock = stubFetch({ "GET /api/tree?root=constitution": { body: treeFixture } });
  const tree = await getTree("constitution");
  expect(tree.node.label).toMatch(/Constitution/);
  expect(mock).toHaveBeenCalledTimes(1);
});

test("getNode encodes type and id in the path", async () => {
  stubFetch({ "GET /api/nodes/case/100": { body: nodeFixture } });
  const node = await getNode("case", 100);
  expect(node.neighbours).toHaveLength(2);
});

test("getFrameworks returns the list", async () => {
  stubFetch({ "GET /api/reason/frameworks": { body: ["common_law"] } });
  expect(await getFrameworks()).toEqual(["common_law"]);
});

test("non-2xx raises ApiError with the status", async () => {
  stubFetch({ "GET /api/nodes/case/999": { status: 404, body: { detail: "node not found" } } });
  await expect(getNode("case", 999)).rejects.toMatchObject({ status: 404 });
  await expect(getNode("case", 999)).rejects.toBeInstanceOf(ApiError);
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: FAIL — cannot resolve `./client`.

- [ ] **Step 4: Write client.ts**

`frontend/src/api/client.ts`:
```ts
import type { NodeDetail, NodeType, TreeNode } from "./types";

export const API_BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: { accept: "application/json" } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export function getTree(root: string): Promise<TreeNode> {
  return getJson<TreeNode>(`/tree?root=${encodeURIComponent(root)}`);
}

export function getNode(type: NodeType, id: number): Promise<NodeDetail> {
  return getJson<NodeDetail>(`/nodes/${type}/${id}`);
}

export function getFrameworks(): Promise<string[]> {
  return getJson<string[]>("/reason/frameworks");
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- src/api/client.test.ts && npm run typecheck`
Expected: 4 passed; typecheck clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api frontend/src/test
git commit -m "feat(frontend): typed API client for tree, nodes and frameworks"
```

---

### Task 3: SSE parser and reverse-reasoning stream

**Files:**
- Create: `frontend/src/api/sse.ts`, `frontend/src/api/sse.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export interface SseMessage { event: string; data: string }
  export class SseParser { push(chunk: string): SseMessage[]; flush(): SseMessage[] }   // handles partial chunks; blocks separated by "\n\n" (also tolerates "\r\n")
  export function toReasoningEvent(msg: SseMessage): ReasoningEvent            // JSON-parses data; throws on unknown kind
  export interface ReverseRequest { node_type: NodeType; node_id: number; framework?: string }
  export async function streamReverse(req: ReverseRequest, onEvent: (ev: ReasoningEvent) => void, signal?: AbortSignal): Promise<void>
  ```
  `streamReverse` POSTs JSON to `/api/reason/reverse`, throws `ApiError` on non-2xx (before streaming), reads `res.body` with a `TextDecoder`, feeds the parser, calls `onEvent` per message in order, resolves when the stream ends. An `AbortSignal` abort rejects with the abort error.

- [ ] **Step 1: Write the failing tests**

`frontend/src/api/sse.test.ts`:
```ts
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- src/api/sse.test.ts`
Expected: FAIL — cannot resolve `./sse`.

- [ ] **Step 3: Write sse.ts**

`frontend/src/api/sse.ts`:
```ts
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- src/api/sse.test.ts && npm run typecheck`
Expected: 5 passed; typecheck clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/sse.ts frontend/src/api/sse.test.ts
git commit -m "feat(frontend): SSE parser and streamed reverse-reasoning client"
```

---

### Task 4: Disclaimer (banner + first-visit acknowledgement)

**Files:**
- Create: `frontend/src/components/Disclaimer/Disclaimer.tsx`, `frontend/src/components/Disclaimer/Disclaimer.css`, `frontend/src/components/Disclaimer/Disclaimer.test.tsx`

**Interfaces:**
- Produces: `export const DISCLAIMER_TEXT` (the verbatim Global Constraints copy); `export const ACK_KEY = "lb.disclaimerAck"`; `export default function Disclaimer(): JSX.Element` — always renders a `<div role="note" class="disclaimer-banner">` with the text; additionally renders a modal `<dialog open role="alertdialog">` with an "I understand" button until `localStorage[ACK_KEY] === "1"`. Reads/writes localStorage inside try/catch.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/Disclaimer/Disclaimer.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Disclaimer, { ACK_KEY, DISCLAIMER_TEXT } from "./Disclaimer";

test("shows the banner and the first-visit modal; acknowledging hides the modal and persists", async () => {
  render(<Disclaimer />);
  expect(screen.getByRole("note")).toHaveTextContent(DISCLAIMER_TEXT);
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "I understand" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(window.localStorage.getItem(ACK_KEY)).toBe("1");
  expect(screen.getByRole("note")).toBeInTheDocument(); // banner never goes away
});

test("does not show the modal once acknowledged", () => {
  window.localStorage.setItem(ACK_KEY, "1");
  render(<Disclaimer />);
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.getByRole("note")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/Disclaimer`
Expected: FAIL — cannot resolve `./Disclaimer`.

- [ ] **Step 3: Write the component**

`frontend/src/components/Disclaimer/Disclaimer.tsx`:
```tsx
import { useState } from "react";
import "./Disclaimer.css";

export const DISCLAIMER_TEXT =
  "Legal Beagle is a research and education tool. It is not legal advice and may be wrong. " +
  "Every citation is checked against the corpus; treat anything marked unresolved as unverified.";

export const ACK_KEY = "lb.disclaimerAck";

function readAck(): boolean {
  try {
    return window.localStorage.getItem(ACK_KEY) === "1";
  } catch {
    return false;
  }
}

export default function Disclaimer() {
  const [acked, setAcked] = useState<boolean>(readAck);

  function acknowledge() {
    try {
      window.localStorage.setItem(ACK_KEY, "1");
    } catch {
      /* storage unavailable: still dismiss for this session */
    }
    setAcked(true);
  }

  return (
    <>
      <div role="note" className="disclaimer-banner">{DISCLAIMER_TEXT}</div>
      {!acked && (
        <dialog open role="alertdialog" aria-labelledby="disclaimer-title" className="disclaimer-modal">
          <h2 id="disclaimer-title">Before you start</h2>
          <p>{DISCLAIMER_TEXT}</p>
          <button type="button" onClick={acknowledge}>I understand</button>
        </dialog>
      )}
    </>
  );
}
```

`frontend/src/components/Disclaimer/Disclaimer.css`:
```css
.disclaimer-banner { background: #fff4d6; border-bottom: 1px solid #e0b84a; padding: 0.5rem 1rem; font-size: 0.9rem; }
.disclaimer-modal { position: fixed; top: 20%; left: 50%; transform: translateX(-50%); max-width: 32rem; padding: 1.5rem; border: 1px solid #999; border-radius: 6px; background: #fff; box-shadow: 0 8px 24px rgba(0,0,0,0.2); z-index: 10; }
.disclaimer-modal button { margin-top: 1rem; padding: 0.5rem 1rem; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/components/Disclaimer && npm run typecheck`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Disclaimer
git commit -m "feat(frontend): persistent not-legal-advice disclaimer with first-visit acknowledgement"
```

---

### Task 5: Provenance badge and Tree view

**Files:**
- Create: `frontend/src/components/ProvenanceBadge.tsx`, `frontend/src/components/Tree/TreeNode.tsx`, `frontend/src/components/Tree/TreeView.tsx`, `frontend/src/components/Tree/Tree.css`, `frontend/src/components/Tree/TreeView.test.tsx`

**Interfaces:**
- Produces: `ProvenanceBadge({ extraction, confidence }: { extraction: Extraction; confidence: number })` → `<span class="prov prov-<extraction>" title="…">parsed · 1.00</span>`.
- Produces: `TreeView({ root, onSelect, selected }: { root: string; onSelect: (ref: NodeRef) => void; selected?: NodeRef | null })` — fetches `getTree(root)` on mount, shows "Loading…", an error message on failure (`role="alert"`), and a `<ul role="tree">` of `TreeNode`s. Expand/collapse per node (all collapsed except the root by default); clicking a label selects it. `TreeNode({ node, depth, expanded, onToggle, onSelect, selected })` renders `<li role="treeitem" aria-expanded>` with a toggle button (`aria-label="Expand"` / `"Collapse"`, hidden when no children), the label as a `<button class="tree-label">`, and a `ProvenanceBadge` when `edge` is non-null.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/Tree/TreeView.test.tsx`:
```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import TreeView from "./TreeView";
import { stubFetch } from "../../test/fetchMock";
import { treeFixture } from "../../test/fixtures";

test("loads the tree, expands provisions to cases, and reports selection", async () => {
  stubFetch({ "GET /api/tree?root=constitution": { body: treeFixture } });
  const onSelect = vi.fn();
  render(<TreeView root="constitution" onSelect={onSelect} />);
  expect(screen.getByText(/Loading/)).toBeInTheDocument();

  const root = await screen.findByRole("treeitem", { name: /Constitution Act$/ });
  expect(root).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText(/s109$/)).toBeInTheDocument();
  expect(screen.queryByText(/Mabo/)).not.toBeInTheDocument(); // provisions start collapsed

  const s109 = screen.getByRole("treeitem", { name: /s109/ });
  await userEvent.click(within(s109).getByRole("button", { name: "Expand" }));
  expect(screen.getByText(/Mabo/)).toBeInTheDocument();
  expect(within(screen.getByRole("treeitem", { name: /Mabo/ })).getByText(/parsed/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Mabo/ }));
  expect(onSelect).toHaveBeenCalledWith({ type: "case", id: 100, label: "Mabo v Queensland (No 2) [1992] HCA 23" });
});

test("shows an error when the tree cannot be loaded", async () => {
  stubFetch({ "GET /api/tree?root=constitution": { status: 404, body: { detail: "root not found" } } });
  render(<TreeView root="constitution" onSelect={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/root not found/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/Tree`
Expected: FAIL — cannot resolve `./TreeView`.

- [ ] **Step 3: Write ProvenanceBadge, TreeNode, TreeView, CSS**

`frontend/src/components/ProvenanceBadge.tsx`:
```tsx
import type { Extraction } from "../api/types";

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
```

`frontend/src/components/Tree/TreeNode.tsx`:
```tsx
import type { NodeRef, TreeNode as TreeNodeData } from "../../api/types";
import ProvenanceBadge from "../ProvenanceBadge";

interface Props {
  node: TreeNodeData;
  depth: number;
  expanded: Set<string>;
  onToggle: (key: string) => void;
  onSelect: (ref: NodeRef) => void;
  selected?: NodeRef | null;
}

export function keyOf(ref: NodeRef): string {
  return `${ref.type}:${ref.id}`;
}

export default function TreeNode({ node, depth, expanded, onToggle, onSelect, selected }: Props) {
  const key = keyOf(node.node);
  const isOpen = expanded.has(key);
  const hasChildren = node.children.length > 0;
  const isSelected = selected ? keyOf(selected) === key : false;
  return (
    <li role="treeitem" aria-expanded={hasChildren ? isOpen : undefined} aria-selected={isSelected}
        aria-label={node.node.label} className={`tree-item depth-${depth}`}>
      <div className="tree-row">
        {hasChildren ? (
          <button type="button" className="tree-toggle" aria-label={isOpen ? "Collapse" : "Expand"} onClick={() => onToggle(key)}>
            {isOpen ? "▾" : "▸"}
          </button>
        ) : (
          <span className="tree-toggle tree-toggle-empty" />
        )}
        <button type="button" className={`tree-label ${isSelected ? "selected" : ""}`} onClick={() => onSelect(node.node)}>
          {node.node.label}
        </button>
        {node.edge && <ProvenanceBadge extraction={node.edge.extraction} confidence={node.edge.confidence} />}
      </div>
      {hasChildren && isOpen && (
        <ul role="group">
          {node.children.map((child) => (
            <TreeNode key={keyOf(child.node)} node={child} depth={depth + 1} expanded={expanded}
                      onToggle={onToggle} onSelect={onSelect} selected={selected} />
          ))}
        </ul>
      )}
    </li>
  );
}
```

`frontend/src/components/Tree/TreeView.tsx`:
```tsx
import { useEffect, useState } from "react";
import { getTree } from "../../api/client";
import type { NodeRef, TreeNode as TreeNodeData } from "../../api/types";
import TreeNode, { keyOf } from "./TreeNode";
import "./Tree.css";

interface Props { root: string; onSelect: (ref: NodeRef) => void; selected?: NodeRef | null }

export default function TreeView({ root, onSelect, selected }: Props) {
  const [tree, setTree] = useState<TreeNodeData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    setTree(null);
    setError(null);
    getTree(root)
      .then((t) => {
        if (cancelled) return;
        setTree(t);
        setExpanded(new Set([keyOf(t.node)]));
      })
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [root]);

  function toggle(key: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  }

  if (error) return <p role="alert" className="tree-error">Could not load tree: {error}</p>;
  if (!tree) return <p className="tree-loading">Loading authority tree…</p>;
  return (
    <ul role="tree" className="tree" aria-label="Authority tree">
      <TreeNode node={tree} depth={0} expanded={expanded} onToggle={toggle} onSelect={onSelect} selected={selected} />
    </ul>
  );
}
```

`frontend/src/components/Tree/Tree.css`:
```css
.tree, .tree ul { list-style: none; margin: 0; padding-left: 0; }
.tree ul { padding-left: 1.25rem; }
.tree-row { display: flex; align-items: center; gap: 0.4rem; padding: 0.15rem 0; }
.tree-toggle { width: 1.4rem; border: none; background: none; cursor: pointer; font-size: 0.9rem; }
.tree-toggle-empty { display: inline-block; }
.tree-label { border: none; background: none; cursor: pointer; text-align: left; padding: 0.1rem 0.3rem; border-radius: 3px; }
.tree-label:hover { background: #eef; }
.tree-label.selected { background: #dde6ff; font-weight: 600; }
.prov { font-size: 0.7rem; padding: 0 0.35rem; border-radius: 999px; border: 1px solid #bbb; color: #444; }
.prov-curated { background: #e3f7e3; }
.prov-parsed { background: #eef; }
.prov-llm_extracted { background: #fde9d9; }
.tree-error { color: #a00; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/components/Tree && npm run typecheck`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ProvenanceBadge.tsx frontend/src/components/Tree
git commit -m "feat(frontend): interactive authority tree with provenance badges"
```

---

### Task 6: Node panel

**Files:**
- Create: `frontend/src/components/NodePanel/NodePanel.tsx`, `frontend/src/components/NodePanel/NodePanel.css`, `frontend/src/components/NodePanel/NodePanel.test.tsx`

**Interfaces:**
- Produces: `NodePanel({ selected, onNavigate }: { selected: NodeRef | null; onNavigate: (ref: NodeRef) => void })` — when `selected` is null shows "Select a node in the tree."; otherwise fetches `getNode(selected.type, selected.id)` (re-fetches when selection changes), shows `<h2>` label, a `<pre class="node-text">` with `text` (omitted when empty), and a `<ul class="neighbours">` where each item shows direction arrow (`→` out / `←` in), `kind`, the neighbour label as a button calling `onNavigate(neighbour.node)`, a `ProvenanceBadge`, and `treatment` when non-null. Errors render in `role="alert"`.

- [ ] **Step 1: Write the failing test**

`frontend/src/components/NodePanel/NodePanel.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import NodePanel from "./NodePanel";
import { stubFetch } from "../../test/fetchMock";
import { nodeFixture } from "../../test/fixtures";

test("prompts when nothing is selected", () => {
  render(<NodePanel selected={null} onNavigate={() => {}} />);
  expect(screen.getByText(/Select a node/)).toBeInTheDocument();
});

test("loads details and lets the user navigate to a neighbour", async () => {
  stubFetch({ "GET /api/nodes/case/100": { body: nodeFixture } });
  const onNavigate = vi.fn();
  render(<NodePanel selected={{ type: "case", id: 100, label: "Mabo" }} onNavigate={onNavigate} />);
  expect(await screen.findByRole("heading", { name: /Mabo v Queensland/ })).toBeInTheDocument();
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("→");
  expect(items[0]).toHaveTextContent("DECIDED_BY");
  expect(items[1]).toHaveTextContent("parsed · 1.00");
  await userEvent.click(screen.getByRole("button", { name: /s109/ }));
  expect(onNavigate).toHaveBeenCalledWith({ type: "provision", id: 12, label: "Commonwealth of Australia Constitution Act s109" });
});

test("shows an error for an unknown node", async () => {
  stubFetch({ "GET /api/nodes/case/999": { status: 404, body: { detail: "node not found" } } });
  render(<NodePanel selected={{ type: "case", id: 999, label: "x" }} onNavigate={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/node not found/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/NodePanel`
Expected: FAIL — cannot resolve `./NodePanel`.

- [ ] **Step 3: Write the component**

`frontend/src/components/NodePanel/NodePanel.tsx`:
```tsx
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
```

`frontend/src/components/NodePanel/NodePanel.css`:
```css
.node-panel h2 { margin: 0 0 0.25rem; font-size: 1.15rem; }
.node-meta { color: #666; font-size: 0.8rem; margin: 0 0 0.75rem; }
.node-text { white-space: pre-wrap; background: #fff; border: 1px solid #ddd; padding: 0.75rem; max-height: 18rem; overflow: auto; font-size: 0.85rem; }
.neighbours { list-style: none; padding: 0; margin: 0; }
.neighbours li { display: flex; gap: 0.5rem; align-items: center; padding: 0.2rem 0; flex-wrap: wrap; }
.nb-kind { font-family: monospace; font-size: 0.8rem; color: #355; }
.nb-treatment { font-size: 0.8rem; color: #777; }
.nb-label { border: none; background: none; cursor: pointer; text-align: left; color: #1a3fa0; text-decoration: underline; padding: 0; }
.node-error { color: #a00; }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/components/NodePanel && npm run typecheck`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/NodePanel
git commit -m "feat(frontend): node detail panel with navigable relationships"
```

---

### Task 7: Reasoning panel with citation badges

**Files:**
- Create: `frontend/src/components/Reasoning/CitationBadge.tsx`, `frontend/src/components/Reasoning/useReverseReasoning.ts`, `frontend/src/components/Reasoning/ReasoningPanel.tsx`, `frontend/src/components/Reasoning/Reasoning.css`, `frontend/src/components/Reasoning/CitationBadge.test.tsx`, `frontend/src/components/Reasoning/ReasoningPanel.test.tsx`

**Interfaces:**
- Produces: `CitationBadge({ citation }: { citation: Citation })` → `<span class="cite cite-<status>" title="<semantics>">` containing the icon, the `raw` citation, and (when `node`) the node label in a `<small>`. `export const STATUS_META: Record<CitationStatus, { icon: string; label: string }>` with exactly: resolved `✅ Verified (in context)`; resolved_outside_context `⚠️ Real, but not in the provided context`; unresolved `❌ Not found in corpus — treat as unverified`; unverifiable `❔ Cannot be checked (reported citation)`.
- Produces: hook `useReverseReasoning()` returning `{ state, run, cancel }` where
  ```ts
  type Phase = "idle" | "streaming" | "verified" | "error";
  interface ReasoningState { phase: Phase; context: ContextNode[]; answer: string; verification: { precision: number; citations: Citation[] } | null; error: string | null }
  run(ref: NodeRef): void   // aborts any previous run, resets state, streams; token payloads append to answer; verification sets it; done sets phase "verified" (or keeps "error" if an error event arrived); error event or thrown ApiError → phase "error" with message
  cancel(): void
  ```
- Produces: `ReasoningPanel({ selected }: { selected: NodeRef | null })` — "Explain the chain of authority" button (disabled when nothing selected or while streaming); a Cancel button while streaming; context chips (`<ul class="context">`, each `label · via`); the answer in `<div class="answer" aria-live="polite">` (plain text with preserved newlines); **while `phase === "streaming"` a visible `<p role="status" class="unverified">Streaming — citations not yet verified</p>`**; after verification, a summary `Citation precision: 67% (2 of 3 checkable)` and one `CitationBadge` per citation; on error, `<p role="alert">`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/Reasoning/CitationBadge.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import CitationBadge, { STATUS_META } from "./CitationBadge";

test.each([
  ["resolved", "✅"],
  ["resolved_outside_context", "⚠️"],
  ["unresolved", "❌"],
  ["unverifiable", "❔"],
] as const)("%s renders its icon and label", (status, icon) => {
  render(<CitationBadge citation={{ raw: "[1992] HCA 23", status, node: null }} />);
  const el = screen.getByText(/\[1992\] HCA 23/);
  expect(el.closest(".cite")).toHaveClass(`cite-${status}`);
  expect(el.closest(".cite")).toHaveAttribute("title", STATUS_META[status].label);
  expect(el.closest(".cite")).toHaveTextContent(icon);
});

test("shows the resolved node label", () => {
  render(<CitationBadge citation={{ raw: "[1992] HCA 23", status: "resolved", node: { type: "case", id: 100, label: "Mabo v Queensland (No 2) [1992] HCA 23" } }} />);
  expect(screen.getByText(/Mabo v Queensland/)).toBeInTheDocument();
});
```

`frontend/src/components/Reasoning/ReasoningPanel.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ReasoningPanel from "./ReasoningPanel";

const okStream = [
  'event: context\ndata: {"nodes":[{"type":"case","id":100,"label":"Mabo [1992] HCA 23","via":"root"},{"type":"provision","id":12,"label":"Constitution s109","via":"graph"}]}\n\n',
  'event: token\ndata: {"text":"## Precedent\\n[1992] HCA 23 applied "}\n\n',
  'event: token\ndata: {"text":"s 109 of the Constitution. See [1950] HCA 99 and (1992) 175 CLR 1."}\n\n',
  'event: verification\ndata: {"precision":0.6666666666666666,"citations":[{"raw":"[1992] HCA 23","status":"resolved","node":{"type":"case","id":100,"label":"Mabo [1992] HCA 23"}},{"raw":"s 109 of the Constitution","status":"resolved","node":{"type":"provision","id":12,"label":"Constitution s109"}},{"raw":"[1950] HCA 99","status":"unresolved","node":null},{"raw":"(1992) 175 CLR 1","status":"unverifiable","node":null}]}\n\n',
  'event: done\ndata: {"answer":"## Precedent\\n[1992] HCA 23 applied s 109 of the Constitution. See [1950] HCA 99 and (1992) 175 CLR 1."}\n\n',
].join("");

const errorStream = 'event: token\ndata: {"text":"partial"}\n\nevent: error\ndata: {"message":"reasoning failed before verification completed","verified":false}\n\n';

function sse(text: string): Response {
  return new Response(new TextEncoder().encode(text), { status: 200, headers: { "content-type": "text/event-stream" } });
}

test("button is disabled without a selection", () => {
  render(<ReasoningPanel selected={null} />);
  expect(screen.getByRole("button", { name: /Explain/ })).toBeDisabled();
});

test("streams tokens, flags them unverified, then shows verification badges", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => sse(okStream)));
  render(<ReasoningPanel selected={{ type: "case", id: 100, label: "Mabo" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByText(/Citation precision: 67%/)).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument(); // streaming notice gone after verification
  expect(screen.getByText(/applied s 109/)).toBeInTheDocument();
  expect(screen.getAllByText(/· root|· graph/)).toHaveLength(2);
  expect(document.querySelectorAll(".cite-resolved")).toHaveLength(2);
  expect(document.querySelectorAll(".cite-unresolved")).toHaveLength(1);
  expect(document.querySelectorAll(".cite-unverifiable")).toHaveLength(1);
});

test("an error event ends the run with an alert and no precision summary", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => sse(errorStream)));
  render(<ReasoningPanel selected={{ type: "case", id: 100, label: "Mabo" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/reasoning failed/);
  expect(screen.queryByText(/Citation precision/)).not.toBeInTheDocument();
  expect(screen.getByText(/partial/)).toBeInTheDocument(); // partial text stays visible but marked
  expect(screen.getByText(/not verified/i)).toBeInTheDocument();
});

test("a 404 from the API is shown as an error", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response('{"detail":"node not found"}', { status: 404 })));
  render(<ReasoningPanel selected={{ type: "case", id: 1, label: "x" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/node not found/);
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- src/components/Reasoning`
Expected: FAIL — cannot resolve modules.

- [ ] **Step 3: Write CitationBadge, the hook, the panel, CSS**

`frontend/src/components/Reasoning/CitationBadge.tsx`:
```tsx
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
```

`frontend/src/components/Reasoning/useReverseReasoning.ts`:
```ts
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
```

`frontend/src/components/Reasoning/ReasoningPanel.tsx`:
```tsx
import type { NodeRef } from "../../api/types";
import CitationBadge from "./CitationBadge";
import { useReverseReasoning } from "./useReverseReasoning";
import "./Reasoning.css";

export default function ReasoningPanel({ selected }: { selected: NodeRef | null }) {
  const { state, run, cancel } = useReverseReasoning();
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

      {state.answer && <div className="answer" aria-live="polite">{state.answer}</div>}

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
```

`frontend/src/components/Reasoning/Reasoning.css`:
```css
.reasoning-controls { display: flex; gap: 0.5rem; margin-bottom: 0.75rem; }
.reasoning-controls button { padding: 0.45rem 0.9rem; }
.context { display: flex; flex-wrap: wrap; gap: 0.35rem; list-style: none; padding: 0; margin: 0 0 0.75rem; }
.ctx { font-size: 0.75rem; border: 1px solid #bbb; border-radius: 999px; padding: 0.1rem 0.5rem; background: #f3f3f3; }
.ctx-root { background: #dde6ff; }
.unverified { color: #8a5a00; background: #fff4d6; padding: 0.35rem 0.6rem; border-radius: 4px; font-size: 0.85rem; }
.answer { white-space: pre-wrap; background: #fff; border: 1px solid #ddd; padding: 0.75rem; margin: 0.5rem 0; font-size: 0.9rem; }
.reasoning-error { color: #a00; }
.citations { list-style: none; padding: 0; display: flex; flex-direction: column; gap: 0.3rem; }
.cite { display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; border: 1px solid #ccc; font-size: 0.85rem; }
.cite-resolved { background: #e3f7e3; border-color: #7bc47b; }
.cite-resolved_outside_context { background: #fff4d6; border-color: #e0b84a; }
.cite-unresolved { background: #fde3e3; border-color: #e07a7a; }
.cite-unverifiable { background: #eee; }
.precision { font-weight: 600; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- src/components/Reasoning && npm run typecheck`
Expected: 9 passed (5 badge + 4 panel); typecheck clean; no `act(...)` warnings in output.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Reasoning
git commit -m "feat(frontend): streamed reverse-reasoning panel with citation verification badges"
```

---

### Task 8: App composition and layout

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/App.css`, `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: `App` renders `Disclaimer`, a header with the title, a two-column layout: `<aside>` with `TreeView root="constitution"`, `<main>` with `NodePanel` and `ReasoningPanel`. Selection state lives in `App` (`useState<NodeRef | null>`); `TreeView.onSelect` and `NodePanel.onNavigate` both set it.

- [ ] **Step 1: Replace the smoke test with an integration test**

`frontend/src/App.test.tsx`:
```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { ACK_KEY } from "./components/Disclaimer/Disclaimer";
import { stubFetch } from "./test/fetchMock";
import { nodeFixture, treeFixture } from "./test/fixtures";

test("tree selection drives the node panel and enables reasoning", async () => {
  window.localStorage.setItem(ACK_KEY, "1");
  stubFetch({
    "GET /api/tree?root=constitution": { body: treeFixture },
    "GET /api/nodes/case/100": { body: nodeFixture },
  });
  render(<App />);
  expect(screen.getByRole("heading", { name: "Legal Beagle" })).toBeInTheDocument();
  expect(screen.getByRole("note")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Explain/ })).toBeDisabled();

  const s109 = await screen.findByRole("treeitem", { name: /s109/ });
  await userEvent.click(within(s109).getByRole("button", { name: "Expand" }));
  await userEvent.click(screen.getByRole("button", { name: /Mabo/ }));

  expect(await screen.findByRole("heading", { level: 2, name: /Mabo v Queensland/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Explain/ })).toBeEnabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/App.test.tsx`
Expected: FAIL — no tree rendered / Explain button missing.

- [ ] **Step 3: Write App.tsx and App.css**

`frontend/src/App.tsx`:
```tsx
import { useState } from "react";
import Disclaimer from "./components/Disclaimer/Disclaimer";
import NodePanel from "./components/NodePanel/NodePanel";
import ReasoningPanel from "./components/Reasoning/ReasoningPanel";
import TreeView from "./components/Tree/TreeView";
import type { NodeRef } from "./api/types";

export default function App() {
  const [selected, setSelected] = useState<NodeRef | null>(null);
  return (
    <div className="app">
      <Disclaimer />
      <header className="app-header">
        <h1>Legal Beagle</h1>
        <p className="tagline">Australian authority, traced and verified.</p>
      </header>
      <div className="layout">
        <aside className="sidebar" aria-label="Authority tree">
          <TreeView root="constitution" onSelect={setSelected} selected={selected} />
        </aside>
        <main className="content">
          <NodePanel selected={selected} onNavigate={setSelected} />
          <ReasoningPanel selected={selected} />
        </main>
      </div>
    </div>
  );
}
```

`frontend/src/App.css`:
```css
:root { font-family: system-ui, sans-serif; color: #1a1a1a; background: #fafafa; }
body { margin: 0; }
.app-header { padding: 0.75rem 1rem 0.25rem; }
.app-header h1 { margin: 0; font-size: 1.5rem; }
.tagline { margin: 0.1rem 0 0; color: #666; font-size: 0.9rem; }
.layout { display: grid; grid-template-columns: minmax(18rem, 28rem) 1fr; gap: 1rem; padding: 1rem; }
.sidebar { border-right: 1px solid #e3e3e3; padding-right: 1rem; max-height: calc(100vh - 9rem); overflow: auto; }
.content { display: flex; flex-direction: column; gap: 1.5rem; min-width: 0; }
@media (max-width: 60rem) { .layout { grid-template-columns: 1fr; } .sidebar { border-right: none; max-height: 20rem; } }
```

- [ ] **Step 4: Run the full frontend suite**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: all tests pass (≈22), typecheck clean, `dist/` built.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.css frontend/src/App.test.tsx
git commit -m "feat(frontend): compose tree, node panel and reasoning panel into the app"
```

---

### Task 9: CI job and README

**Files:**
- Modify: `.github/workflows/ci.yml` (add a `frontend` job), `README.md` (Frontend section)

- [ ] **Step 1: Add the CI job**

Append to `.github/workflows/ci.yml` under `jobs:` (keep existing jobs unchanged):
```yaml
  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
```

- [ ] **Step 2: README section**

Insert after the "### Try it with the tiny fixture corpus" block in `README.md`:
```markdown
### Frontend

```bash
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173 — proxies /api to the backend on :8000
npm test               # Vitest + Testing Library
```

The UI shows the authority tree on the left (Constitution → provisions → interpreting cases),
node details on the right, and an "Explain the chain of authority" button that streams the
model's reasoning. Streamed text is flagged as unverified until the citation check arrives;
each citation then gets a badge: ✅ verified in context · ⚠️ real but outside the supplied
context · ❌ not found in the corpus · ❔ cannot be checked (reported citation).
```

- [ ] **Step 3: Verify YAML and commit**

Run: `python3 -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))" && echo ok` (use `backend/.venv/bin/python` if `yaml` is missing).
Expected: ok.

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: frontend job; docs: frontend quick start"
```

---

### Task 10: Live integration check against the backend

**Files:** none created; this task produces a verified checklist in the task report.

Prerequisites: backend running on `:8000` against a database that contains at least the fixture corpus (`cd backend && uv run fastapi dev src/main.py`); for the reasoning step, an LLM reachable at `LLM_API_BASE` (or start the backend with `LLM="fake:## Precedent\n[1992] HCA 23 applied s 109 of the Constitution. See [1950] HCA 99." EMBEDDER=fake` to use the fake client).

- [ ] **Step 1: Start the frontend dev server**

Run: `cd frontend && npm run dev` (background), then `curl -s http://127.0.0.1:5173/api/health` → `{"status":"ok"}` proves the proxy.

- [ ] **Step 2: Exercise the UI in a browser (or headless via Playwright if available)**

Check each and record the result:
1. First visit shows the modal; "I understand" dismisses it; reload does not show it again; the banner is always visible.
2. Tree loads with the Constitution root expanded; `s109` expands to show interpreting cases with `parsed · 1.00` badges.
3. Clicking a case fills the node panel with relationships; clicking a relationship navigates.
4. "Explain the chain of authority" streams text under a visible "not yet verified" notice, then shows a precision line and one badge per citation with the right colours.
5. Stop the backend mid-stream (or use a node id that fails) and confirm the error alert appears and the partial text is marked unverified.

- [ ] **Step 3: Record**

Write the results (pass/fail per item, screenshots if taken) to the task report. No commit unless a defect was found and fixed (then commit the fix with its test).

---

## Self-Review

**Spec coverage (§6, Phase 1):** Interactive Tree (Task 5), clicking a node opens Reverse Engineering (Tasks 7–8), disclaimer persistent and not dismissable on first visit without acknowledgement (Task 4), reasoning panel streams output with citation verification badges (Task 7), provenance shown on edges (Tasks 5–6 via `ProvenanceBadge`). Layered Map and Timeline are Phase 2/3 by the spec and intentionally absent. Filtering by jurisdiction/date/court tier (spec "filterable by…") is **not** in this plan — only Commonwealth/HCA data exists in Phase 1 — noted as a gap for the next frontend plan. Spec's `hooks/useNeo4jQueries` etc. are superseded by the Postgres API; no Neo4j.

**Placeholder scan:** none; every task has full code and tests.

**Type consistency:** `NodeRef {type,id,label}`, `TreeNode {node,edge,children}`, `NodeDetail.neighbours[].node`, `ReasoningEvent` kinds/payloads, `CitationStatus` values, `ContextNode.via` are identical across Tasks 2, 3, 5, 6, 7, 8 and match the backend (`src/api/tree.py`, `nodes.py`, `reason.py`, `reverse_engineering.py`, `verifier.py`). `keyOf` is exported from `TreeNode.tsx` and used by `TreeView.tsx`. `ACK_KEY` is exported from `Disclaimer.tsx` and used in `App.test.tsx`.
