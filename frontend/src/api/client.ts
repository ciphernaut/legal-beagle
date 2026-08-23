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
