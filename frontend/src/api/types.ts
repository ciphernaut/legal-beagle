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
