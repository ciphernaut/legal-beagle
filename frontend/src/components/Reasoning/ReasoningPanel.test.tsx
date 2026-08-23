import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import ReasoningPanel from "./ReasoningPanel";

const okStream = [
  'event: context\ndata: {"nodes":[{"type":"case","id":100,"label":"Mabo [1992] HCA 23","via":"root"},{"type":"provision","id":12,"label":"Constitution s109","via":"graph"}]}\n\n',
  'event: token\ndata: {"text":"## Precedent\\n[1992] HCA 23 applied "}\n\n',
  'event: token\ndata: {"text":"s 109 of the Constitution. See [1950] HCA 99 and (1992) 175 CLR 1."}\n\n',
  'event: verification\ndata: {"precision":0.6666666666666666,"citations":[{"raw":"[1992] HCA 23","status":"resolved","node":{"type":"case","id":100,"label":"Mabo [1992] HCA 23"}},{"raw":"s 109 of the Constitution","status":"resolved","node":{"type":"provision","id":12,"label":"Constitution s109"}},{"raw":"[1950] HCA 99","status":"unresolved","node":null},{"raw":"(1992) 175 CLR 1","status":"unverifiable","node":null}]}\n\n',
  'event: done\ndata: {"answer":"## Precedent\\n[1992] HCA 23 applied s 109 of the Constitution. See [1950] HCA 99 and (1992) 175 CLR 1."}\n\n',
].join("");

const errorStream = 'event: token\ndata: {"text":"partial"}\n\nevent: error\ndata: {"message":"reasoning failed before verification completed","verified":false}\n\n';

function sse(text: string): Response {
  return new Response(new TextEncoder().encode(text), { status: 200, headers: { "content-type": "text/event-stream" } });
}

test("button is disabled without a selection", () => {
  render(<ReasoningPanel selected={null} />);
  expect(screen.getByRole("button", { name: /Explain/ })).toBeDisabled();
});

test("streams tokens, flags them unverified, then shows verification badges", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => sse(okStream)));
  render(<ReasoningPanel selected={{ type: "case", id: 100, label: "Mabo" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByText(/Citation precision: 67%/)).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument(); // streaming notice gone after verification
  expect(screen.getByText(/applied s 109/)).toBeInTheDocument();
  expect(screen.getAllByText(/· root|· graph/)).toHaveLength(2);
  expect(document.querySelectorAll(".cite-resolved")).toHaveLength(2);
  expect(document.querySelectorAll(".cite-unresolved")).toHaveLength(1);
  expect(document.querySelectorAll(".cite-unverifiable")).toHaveLength(1);
});

test("an error event ends the run with an alert and no precision summary", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => sse(errorStream)));
  render(<ReasoningPanel selected={{ type: "case", id: 100, label: "Mabo" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/reasoning failed/);
  expect(screen.queryByText(/Citation precision/)).not.toBeInTheDocument();
  expect(screen.getByText(/partial/)).toBeInTheDocument(); // partial text stays visible but marked
  expect(screen.getByText(/not verified/i)).toBeInTheDocument();
});

test("a 404 from the API is shown as an error", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response('{"detail":"node not found"}', { status: 404 })));
  render(<ReasoningPanel selected={{ type: "case", id: 1, label: "x" }} />);
  await userEvent.click(screen.getByRole("button", { name: /Explain/ }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/node not found/);
});
