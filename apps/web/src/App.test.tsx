import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { App } from "./App";

it("renders login when no token exists", () => {
  localStorage.clear();
  render(
    <MemoryRouter future={{ v7_relativeSplatPath: true, v7_startTransition: true }}>
      <App />
    </MemoryRouter>,
  );
  expect(screen.getByRole("heading", { name: "TradingAgents" })).toBeInTheDocument();
  expect(screen.getByLabelText("Access Token")).toBeInTheDocument();
});
