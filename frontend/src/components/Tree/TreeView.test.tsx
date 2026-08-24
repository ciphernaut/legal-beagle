import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import TreeView from "./TreeView";
import { stubFetch } from "../../test/fetchMock";
import { treeFixture } from "../../test/fixtures";

/** The row (`<li>`) that owns the label button with this accessible name. */
function rowFor(name: RegExp): HTMLElement {
  const li = screen.getByRole("button", { name }).closest("li");
  if (!li) throw new Error(`no row for ${String(name)}`);
  return li as HTMLElement;
}

test("loads the tree, expands provisions to cases, and reports selection", async () => {
  stubFetch({ "GET /api/tree?root=constitution": { body: treeFixture } });
  const onSelect = vi.fn();
  render(<TreeView root="constitution" onSelect={onSelect} />);
  expect(screen.getByText(/Loading/)).toBeInTheDocument();

  const root = await screen.findByRole("button", { name: /Constitution Act$/ });
  expect(within(rowFor(/Constitution Act$/)).getByRole("button", { name: "Collapse" }))
    .toHaveAttribute("aria-expanded", "true"); // root starts expanded
  expect(root).toBeInTheDocument();
  expect(screen.getByRole("list", { name: "Authority tree" })).toBeInTheDocument();
  expect(screen.getByText(/s109$/)).toBeInTheDocument();
  expect(screen.queryByText(/Mabo/)).not.toBeInTheDocument(); // provisions start collapsed

  const s109 = rowFor(/s109$/);
  const toggle = within(s109).getByRole("button", { name: "Expand" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(toggle);
  expect(screen.getByText(/Mabo/)).toBeInTheDocument();
  expect(within(rowFor(/Mabo/)).getByText(/parsed/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Mabo/ }));
  expect(onSelect).toHaveBeenCalledWith({ type: "case", id: 100, label: "Mabo v Queensland (No 2) [1992] HCA 23" });
});

test("leaf rows have no toggle button", async () => {
  stubFetch({ "GET /api/tree?root=constitution": { body: treeFixture } });
  render(<TreeView root="constitution" onSelect={() => {}} />);
  await screen.findByRole("button", { name: /Constitution Act$/ });
  const s51 = rowFor(/s51$/);
  expect(within(s51).queryByRole("button", { name: /Expand|Collapse/ })).not.toBeInTheDocument();
});

test("shows an error when the tree cannot be loaded", async () => {
  stubFetch({ "GET /api/tree?root=constitution": { status: 404, body: { detail: "root not found" } } });
  render(<TreeView root="constitution" onSelect={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/root not found/);
});
