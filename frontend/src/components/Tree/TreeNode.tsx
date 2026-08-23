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
