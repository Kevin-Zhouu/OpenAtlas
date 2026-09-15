import { render, screen, cleanup, fireEvent } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { DebugInspector } from "./DebugInspector";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows agent actions and renders untrusted output as text", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          status: "running",
          progress: "Building",
          request: { provider: "codex", model: "gpt-6-astra" },
        },
        updated_at: new Date().toISOString(),
        containers: [
          {
            id: "abc",
            role: "agent",
            status: "running",
            processes: [["1", "codex"]],
            agent_log: JSON.stringify({
              type: "item.started",
              item: {
                type: "command_execution",
                command: "<script>alert(1)</script>",
                status: "in_progress",
              },
            }),
          },
        ],
      }),
    }),
  );
  render(<DebugInspector jobId="test" onClose={() => {}} />);
  expect(
    (await screen.findAllByText("<script>alert(1)</script>"))[0],
  ).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(screen.getByText("Codex agent")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Pause live updates" }),
  ).toBeInTheDocument();
});
it("explains demo jobs have no container", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          status: "succeeded",
          progress: "Done",
          request: { provider: "demo" },
        },
        containers: [],
        updated_at: null,
      }),
    }),
  );
  render(<DebugInspector jobId="demo" onClose={() => {}} />);
  expect(
    await screen.findByText(/Demo generation uses no Codex container/),
  ).toBeInTheDocument();
  expect(screen.getByText(/Retained snapshot/)).toBeInTheDocument();
});
it("shows connection failures", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  render(<DebugInspector jobId="test" onClose={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Could not load diagnostics",
  );
});

it("keeps activity and instructions scoped to the selected stage", async () => {
  const request = {
    prompt: "Inside LLM inference",
    provider: "codex",
    model: "builder-model",
    planner_model: "planner-model",
    planning_enabled: true,
    build_prompt: "Saved creative brief",
  };
  const container = (id: string, stage: string, message: string) => ({
    id,
    stage,
    role: "agent",
    status: "running",
    processes: [],
    agent_log: JSON.stringify({
      type: "item.completed",
      item: { type: "agent_message", text: message },
    }),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          stage: "building",
          status: "running",
          progress: "Building the Notebook",
          request,
        },
        containers: [
          container("plan", "planning", "Planner inspected token resources"),
          container(
            "build",
            "building",
            "Builder is implementing the GPU view",
          ),
        ],
        generation: {
          request,
          job: {},
          prompt: "Builder prompt",
          prompt_source: "captured",
          skills: [],
          invocations: [
            {
              phase: "planning",
              captured_at: "2026-01-01",
              prompt: "Exact planner instructions",
              command: ["python", "planner"],
              model: "planner-model",
            },
            {
              phase: "generate",
              captured_at: "2026-01-01",
              prompt: "Exact builder instructions",
              command: ["codex", "exec"],
              model: "builder-model",
            },
          ],
        },
      }),
    }),
  );
  render(<DebugInspector jobId="staged" onClose={() => {}} />);
  expect(
    await screen.findByText("Builder is implementing the GPU view"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Planner inspected token resources"),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /^Planning/ }));
  expect(
    screen.getByText("Planner inspected token resources"),
  ).toBeInTheDocument();
  expect(
    screen.queryByText("Builder is implementing the GPU view"),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Generation details" }));
  expect(screen.getByLabelText("Full planner instructions")).toHaveValue(
    "Exact planner instructions",
  );
  expect(
    screen.queryByText("Exact builder instructions"),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /^Validating/ }));
  expect(screen.getByText("Validating hasn’t started yet")).toBeInTheDocument();
  expect(
    screen.queryByText("Builder is implementing the GPU view"),
  ).not.toBeInTheDocument();
});

it("shows a failed validation at its recorded stage", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        job: {
          stage: "failed",
          status: "failed",
          progress: "Failed",
          error: "Interaction check failed",
          request: { prompt: "Mechanics", provider: "codex" },
        },
        containers: [],
        events: [
          {
            stage: "validating",
            message: "Interaction check failed",
            created_at: "2026-01-01",
          },
        ],
      }),
    }),
  );
  render(<DebugInspector jobId="failed" onClose={() => {}} />);
  const stage = await screen.findByRole("button", { name: /^Validating/ });
  expect(stage).toHaveAttribute("aria-current", "step");
  expect(stage).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("button", { name: /^Publishing/ })).toHaveTextContent(
    "Up next",
  );
});

it("retains validation failures while implementation repairs are running", async () => {
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>({
  job:{status:'running',stage:'building',progress:'Repairing browser issues',request:{provider:'codex'}},
  updated_at:null,containers:[],events:[{stage:'validating',message:'Checking in browser',created_at:new Date().toISOString()}],
  validation:[{round:1,status:'failed',reason:'Interaction check 1 failed',checks:[{id:'interaction-1',title:'Interaction 1',status:'failed',expected:'Feedback is visible',reason:'Feedback remained hidden'}]}]
 })}));
 render(<DebugInspector jobId="test" onClose={()=>{}} />);
 fireEvent.click(await screen.findByRole('button', {name:/Validating/}));
 expect(screen.queryByText('Validating hasn’t started yet')).not.toBeInTheDocument();
 expect(screen.getByText('Round 1')).toBeVisible();
 expect(screen.getByText('Feedback remained hidden')).toBeVisible();
});

it('offers downloads for the selected stage and the entire attempt', async () => {
 vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async()=>({job:{status:'succeeded',stage:'completed',progress:'Ready',request:{provider:'codex'}},updated_at:null,containers:[]})}));
 render(<DebugInspector jobId="test-job" onClose={()=>{}} />);
 expect(await screen.findByRole('link',{name:'Download all stage traces'})).toHaveAttribute('href','/api/jobs/test-job/trace');
 fireEvent.click(screen.getByRole('button',{name:/Validating/}));
 expect(screen.getByRole('link',{name:'Download validating trace'})).toHaveAttribute('href','/api/jobs/test-job/trace?stage=validating');
 expect(screen.getByRole('link',{name:'Download validating trace'})).toHaveAttribute('download');
});

it('keeps the reviewer activity visible alongside validation checks', async () => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({
    job:{status:'running',stage:'validating',progress:'Reviewing',request:{provider:'codex'}},
    containers:[{id:'review',role:'agent',stage:'validating',status:'running',agent_log:JSON.stringify({type:'item.completed',item:{id:'item',type:'agent_message',text:'Reviewing the phone layout'}})}],
    validation:[{round:1,status:'running',checks:[]}],
  })}));
  render(<DebugInspector jobId="job" onClose={()=>{}} />);
  expect(await screen.findByText('Reviewing the phone layout')).toBeInTheDocument();
  expect(screen.getByRole('log',{name:'Agent activity'})).toBeInTheDocument();
});

it('resumes the selected stopped stage in a new attempt', async () => {
  const fetcher = vi.fn().mockImplementation(async (url: string, options?: RequestInit) => {
    if (url.endsWith('/resume')) return {ok:true,json:async()=>({id:'resumed'})};
    if (url.endsWith('/controls')) return {ok:true,json:async()=>({messages:[],preview:null})};
    return {ok:true,json:async()=>({
      job:{status:url.includes('/resumed/')?'queued':'failed', stage:'failed', stopped_stage:'validating',
        resume_stages:['validating'], request:{provider:'demo',resume_stage:url.includes('/resumed/')?'validating':undefined}},
      containers:[], events:[], updated_at:null,
    })};
  });
  vi.stubGlobal('fetch',fetcher);
  render(<DebugInspector jobId="stopped" onClose={()=>{}} />);
  fireEvent.click(await screen.findByRole('button',{name:'Resume validation'}));
  expect(fetcher).toHaveBeenCalledWith('/api/jobs/stopped/resume',expect.objectContaining({
    method:'POST',body:JSON.stringify({stage:'validating'}),
  }));
  await screen.findByRole('button',{name:'Pause live updates'});
});
