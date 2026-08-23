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
