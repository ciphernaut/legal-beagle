import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";
import { ACK_KEY } from "./components/Disclaimer/Disclaimer";
import { stubFetch } from "./test/fetchMock";
import { nodeFixture, treeFixture } from "./test/fixtures";

test("tree selection drives the node panel and enables reasoning", async () => {
  window.localStorage.setItem(ACK_KEY, "1");
  stubFetch({
    "GET /api/tree?root=constitution": { body: treeFixture },
    "GET /api/nodes/case/100": { body: nodeFixture },
  });
  render(<App />);
  expect(screen.getByRole("heading", { name: "Legal Beagle" })).toBeInTheDocument();
  expect(screen.getByRole("note")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Explain/ })).toBeDisabled();

  const s109Label = await screen.findByRole("button", { name: /s109$/ });
  const s109Row = s109Label.closest("li") as HTMLElement;
  await userEvent.click(within(s109Row).getByRole("button", { name: "Expand" }));
  await userEvent.click(screen.getByRole("button", { name: /Mabo/ }));

  expect(await screen.findByRole("heading", { level: 2, name: /Mabo v Queensland/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Explain/ })).toBeEnabled();
});
