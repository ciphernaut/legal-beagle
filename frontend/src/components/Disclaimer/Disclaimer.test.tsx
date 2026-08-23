import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Disclaimer, { ACK_KEY, DISCLAIMER_TEXT } from "./Disclaimer";

test("shows the banner and the first-visit modal; acknowledging hides the modal and persists", async () => {
  render(<Disclaimer />);
  expect(screen.getByRole("note")).toHaveTextContent(DISCLAIMER_TEXT);
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "I understand" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(window.localStorage.getItem(ACK_KEY)).toBe("1");
  expect(screen.getByRole("note")).toBeInTheDocument(); // banner never goes away
});

test("does not show the modal once acknowledged", () => {
  window.localStorage.setItem(ACK_KEY, "1");
  render(<Disclaimer />);
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  expect(screen.getByRole("note")).toBeInTheDocument();
});
