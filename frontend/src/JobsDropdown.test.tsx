import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { afterEach, it, expect, vi } from "vitest";
import { JobsDropdown } from "./JobsDropdown";
afterEach(cleanup);
it("filters failed jobs and opens their debug inspector", () => {
  const inspect = vi.fn();
  render(
    <JobsDropdown
      jobs={[
        {
          id: "1",
          status: "failed",
          progress: "Failed",
          error: "Interaction check 9 failed",
          created_at: "2026-09-14",
          request: { prompt: "vLLM", provider: "codex" },
        },
        {
          id: "2",
          status: "running",
          progress: "Building",
          created_at: "2026-09-14",
          request: { prompt: "Trees", provider: "codex" },
        },
      ]}
      onInspect={inspect}
    />,
  );
  fireEvent.click(screen.getByText("Jobs"));
  fireEvent.change(screen.getByLabelText("Filter jobs"), {
    target: { value: "failed" },
  });
  expect(screen.queryByText("Trees")).not.toBeInTheDocument();
  expect(screen.getByText("Interaction check 9 failed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Debug failed job" }));
  expect(inspect).toHaveBeenCalledWith("1");
  expect(document.querySelector("details")).not.toHaveAttribute("open");
});
