import {
  render,
  screen,
  fireEvent,
  cleanup,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Notifications } from "./Notifications";
const job = {
  id: "one",
  status: "failed",
  error: "Build failed",
  created_at: "2026-09-14T00:00:00Z",
  request: { prompt: "Learn caching" },
};
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
it("keeps historical failures quiet and remembers read status", () => {
  const props = { jobs: [job], ready: true, error: "", onInspect: vi.fn() };
  const view = render(<Notifications {...props} />);
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "Notifications, 1 unread" }),
  );
  expect(screen.getByText("Build failed")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Mark all as read"));
  view.unmount();
  render(<Notifications {...props} />);
  expect(
    screen.getByRole("button", { name: "Notifications" }),
  ).toBeInTheDocument();
});
it("toasts new failures once, expires the popup, and retains an inspect action", () => {
  vi.useFakeTimers();
  const onInspect = vi.fn();
  const view = render(
    <Notifications jobs={[]} ready={false} error="" onInspect={onInspect} />,
  );
  view.rerender(
    <Notifications
      jobs={[{ ...job, status: "running" }]}
      ready
      error=""
      onInspect={onInspect}
    />,
  );
  view.rerender(
    <Notifications jobs={[job]} ready error="" onInspect={onInspect} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Build failed");
  act(() => vi.advanceTimersByTime(8000));
  view.rerender(
    <Notifications jobs={[{ ...job }]} ready error="" onInspect={onInspect} />,
  );
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Notifications/ }));
  fireEvent.click(screen.getByText("Inspect job ↗"));
  expect(onInspect).toHaveBeenCalledWith("one");
});
it("deduplicates repeated request errors and supports Escape", () => {
  const props = {
    jobs: [],
    ready: true,
    error: "Connection lost",
    onInspect: vi.fn(),
  };
  const view = render(<Notifications {...props} />);
  fireEvent.click(screen.getByLabelText("Dismiss notification"));
  view.rerender(<Notifications {...props} jobs={[]} />);
  expect(screen.queryByRole("alert")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Notifications/ }));
  expect(screen.getAllByText("Connection lost")).toHaveLength(1);
  fireEvent.keyDown(document, { key: "Escape" });
  expect(screen.queryByRole("region")).toBeNull();
});
it("does not notify for failures recovered through revalidation", () => {
  render(
    <Notifications
      jobs={[
        job,
        {
          ...job,
          id: "two",
          status: "succeeded",
          request: { prompt: "Learn caching", revalidate_job: "one" },
        },
      ]}
      ready
      error=""
      onInspect={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
  expect(screen.getByText(/All quiet here/)).toBeInTheDocument();
});
