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
