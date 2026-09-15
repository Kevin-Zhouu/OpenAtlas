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
  render(<JobsDropdown onInspect={vi.fn()} onResume={retry} jobs={[{
    id:'failed', status:'failed', resume_stage:'building', can_continue:true, progress:'Failed', error:'No credits',
    created_at:'2026-09-14', request:{prompt:'Learn memory',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  fireEvent.click(screen.getByRole('button', {name:'Resume'}));
  expect(retry).toHaveBeenCalledWith('failed');
  expect(await screen.findByText('No queued jobs.')).toBeInTheDocument();
});
it('offers rerun but disables continue when older work was not retained', () => {
  render(<JobsDropdown onInspect={vi.fn()} onRetry={vi.fn()} onResume={vi.fn()} jobs={[{
    id:'failed', status:'failed', can_continue:false, progress:'Failed', created_at:'2026-09-14',
    request:{prompt:'Learn memory',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  expect(screen.getByRole('button', {name:'Resume'})).toBeDisabled();
  expect(screen.getByRole('button', {name:'Re-run'})).toBeEnabled();
});

it('resumes validation separately from editing', async () => {
  const resume = vi.fn().mockResolvedValue(undefined);
  const retry = vi.fn();
  render(<JobsDropdown onInspect={vi.fn()} onRetry={retry} onResume={resume} jobs={[{
    id:'saved', status:'failed', stopped_stage:'validating', can_continue:true,
    resume_stage:'validating', resume_stages:['building','validating'], progress:'Stopped', created_at:'2026-09-15',
    request:{prompt:'Saved Notebook',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  expect(screen.getByText('Stopped during validation')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'Resume'}));
  expect(resume).toHaveBeenCalledWith('saved');
  expect(screen.queryByRole('button',{name:'Resume implementation'})).not.toBeInTheDocument();
  expect(retry).not.toHaveBeenCalled();
  expect(await screen.findByText('No queued jobs.')).toBeInTheDocument();
});

it('keeps a failed resume visible with its error', async () => {
  render(<JobsDropdown onInspect={vi.fn()} onResume={vi.fn().mockRejectedValue(new Error('Saved evidence changed'))} jobs={[{
    id:'saved', status:'failed', resume_stage:'publishing', resume_stages:['publishing'], progress:'Stopped', created_at:'2026-09-15',
    request:{prompt:'Saved Notebook',provider:'codex'},
  }]} />);
  fireEvent.click(screen.getByText('Jobs'));
  fireEvent.click(screen.getByRole('button', {name:'Resume'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved evidence changed');
  expect(screen.getByRole('button', {name:'Resume'})).toBeEnabled();
});
