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
  fireEvent.click(screen.getByRole("button", { name: "Inspect generation" }));
  expect(inspect).toHaveBeenCalledWith("1");
  expect(document.querySelector("details")).not.toHaveAttribute("open");
});
it('continues a failed job with saved work and shows the queued attempt', async () => {
  const retry = vi.fn().mockResolvedValue(undefined);
  render(<JobsDropdown onInspect={vi.fn()} onRetry={retry} jobs={[{
    id:'failed', status:'failed', can_continue:true, progress:'Failed', error:'No credits',
    created_at:'2026-09-14', request:{prompt:'Learn memory',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  fireEvent.click(screen.getByRole('button', {name:'Continue'}));
  expect(retry).toHaveBeenCalledWith('failed','continue');
  expect(await screen.findByText('No queued jobs.')).toBeInTheDocument();
});
it('offers rerun but disables continue when older work was not retained', () => {
  render(<JobsDropdown onInspect={vi.fn()} onRetry={vi.fn()} jobs={[{
    id:'failed', status:'failed', can_continue:false, progress:'Failed', created_at:'2026-09-14',
    request:{prompt:'Learn memory',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  expect(screen.getByRole('button', {name:'Continue'})).toBeDisabled();
  expect(screen.getByRole('button', {name:'Re-run'})).toBeEnabled();
});
