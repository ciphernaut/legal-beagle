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
