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
