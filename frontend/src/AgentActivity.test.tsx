import { render, screen, cleanup } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AgentActivity, parseActivity } from "./AgentActivity";
afterEach(cleanup);
const start = JSON.stringify({
  type: "item.started",
  item: {
    id: "a",
    type: "command_execution",
    command: "npm run build",
    status: "in_progress",
  },
});
const message = JSON.stringify({
  type: "item.completed",
  item: { id: "b", type: "agent_message", text: "The build is ready." },
});
const done = JSON.stringify({
  type: "item.completed",
  item: {
    id: "a",
    type: "command_execution",
    command: "npm run build",
    status: "completed",
    aggregated_output: "Build passed",
  },
});
it("merges task updates without duplicate rows and preserves chronological order", () => {
  const events = parseActivity([start, message, done].join("\n"), "container");
  expect(events).toHaveLength(2);
  expect(events[0]).toMatchObject({
    id: "container:a",
    status: "completed",
    output: "Build passed",
  });
  expect(events[1].text).toBe("The build is ready.");
});
it("ignores partial JSON and keeps item IDs separate between agent runs", () => {
  expect(
    parseActivity("partial}\n" + start + '\n{"type":', "one"),
  ).toHaveLength(1);
  expect(parseActivity(start, "one")[0].id).not.toBe(
    parseActivity(start, "two")[0].id,
  );
});
it("animates running tasks and stops animations on pause or job completion", () => {
  const sources = [{ id: "one", status: "running", agent_log: start }];
  const view = render(
    <AgentActivity
      sources={sources}
      running
      paused={false}
      progress="Building"
    />,
  );
  expect(screen.getByRole("img", { name: "Running" })).toBeInTheDocument();
  view.rerender(
    <AgentActivity sources={sources} running paused progress="Building" />,
  );
  expect(
    screen.queryByRole("img", { name: "Running" }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Paused")).toBeInTheDocument();
  view.rerender(
    <AgentActivity
      sources={sources}
      running={false}
      paused={false}
      progress="Done"
    />,
  );
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  expect(screen.getByText("Ended")).toBeInTheDocument();
});
it("updates an existing task to completed without retaining its spinner", () => {
  const view = render(
    <AgentActivity
      sources={[{ id: "one", status: "running", agent_log: start }]}
      running
      paused={false}
      progress="Building"
    />,
  );
  view.rerender(
    <AgentActivity
      sources={[
        { id: "one", status: "running", agent_log: start + "\n" + done },
      ]}
      running
      paused={false}
      progress="Validating"
    />,
  );
  expect(
    screen.queryByRole("img", { name: "Running" }),
  ).not.toBeInTheDocument();
  expect(document.querySelectorAll(".activity-item")).toHaveLength(1);
  expect(screen.getByText("Build passed")).toBeInTheDocument();
});

it("formats agent prose without enabling HTML, links, or remote images", () => {
  const log = JSON.stringify({
    type: "item.completed",
    item: {
      id: "text",
      type: "agent_message",
      text: '**Build passed** with `npm test`.\n\n[Open](https://example.com) ![Preview](https://example.com/image.png)\n\n<script>alert(1)</script><iframe src="https://example.com"></iframe>',
    },
  });
  render(
    <AgentActivity
      sources={[{ id: "one", status: "removed", agent_log: log }]}
      running={false}
      paused={false}
      progress="Done"
    />,
  );
  expect(screen.getByText("Build passed").tagName).toBe("STRONG");
  expect(screen.getByText("npm test").tagName).toBe("CODE");
  expect(document.querySelector("script, iframe, img, a")).toBeNull();
});

it('shows actual planner resource reads as observable activity', () => {
  const rows = parseActivity(JSON.stringify({type: 'planner.resource_read', path: 'local--anatomy/notes.md', offset: 0, characters: 120}), 'planner');
  expect(rows[0].text).toContain('Read local--anatomy/notes.md');
  expect(rows[0].status).toBe('completed');
});

it('keeps earlier activity when a run grows beyond sixty events', () => {
  const events = Array.from({length:75}, (_,i) => JSON.stringify({type:'item.completed',item:{id:String(i),type:'agent_message',text:`Event ${i}`}}));
  const view = render(<AgentActivity sources={[{id:'one',status:'running',agent_log:events.slice(0,60).join('\n')}]} running paused={false} progress="Reviewing" />);
  view.rerender(<AgentActivity sources={[{id:'one',status:'running',agent_log:events.join('\n')}]} running paused={false} progress="Reviewing" />);
  expect(screen.getByText('Event 0')).toBeInTheDocument();
  expect(screen.getByText('Event 74')).toBeInTheDocument();
  expect(parseActivity(events.join('\n'),'one')).toHaveLength(75);
});
