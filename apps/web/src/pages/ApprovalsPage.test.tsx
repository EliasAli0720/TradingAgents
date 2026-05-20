import { render, screen } from "@testing-library/react";
import { ApprovalsPage } from "./ApprovalsPage";

it("renders approvals heading and confirmation hint", () => {
  render(<ApprovalsPage />);
  expect(screen.getByRole("heading", { name: "Approvals" })).toBeInTheDocument();
  expect(screen.getByText(/APPROVE/)).toBeInTheDocument();
});
