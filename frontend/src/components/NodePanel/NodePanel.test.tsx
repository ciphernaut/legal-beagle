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
