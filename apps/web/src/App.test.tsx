import { render, screen } from "@testing-library/react";
import { App } from "./App";

it("renders the TradingAgents shell", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "TradingAgents" })).toBeInTheDocument();
});
