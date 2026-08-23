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
