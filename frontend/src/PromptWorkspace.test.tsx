import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi, it, expect } from "vitest";
import { PromptWorkspace } from "./PromptWorkspace";
it("saves immutable edits before allowing a build and keeps a comparison candidate", async () => {
  let revisions = [
    {
      id: "original",
      content: "Build an explorable token journey with clear GPU diagrams.",
      created_at: "2026-01-01",
    },
  ];
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/edit")) {
      const revision = {
        id: "edited",
        content: JSON.parse(String(init?.body)).content,
        created_at: "2026-01-02",
      };
      revisions = [...revisions, revision];
      return { ok: true, json: async () => revision };
    }
    if (url.endsWith("/build"))
      return { ok: true, json: async () => ({ id: "build-job" }) };
    return {
      ok: true,
      json: async () => [
        {
          id: "attempt",
          status: "succeeded",
          created_at: "2026-01-01",
          revisions,
        },
      ],
    };
  });
  vi.stubGlobal("fetch", fetcher);
  const followJob = vi.fn();
  render(<PromptWorkspace jobId="job" onJobQueued={followJob} />);
  await screen.findByRole("option", { name: /Generated/ });
  fireEvent.change(screen.getByLabelText("Prompt revision"), {
    target: { value: "original" },
  });
  fireEvent.change(screen.getByLabelText("Editable build prompt"), {
    target: {
      value:
        "Build an expanded token journey with keyboard controls and visible GPU execution.",
    },
  });
  expect(
    screen.getByRole("button", { name: "Build from this prompt" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Save new revision" }));
  await screen.findByText("Saved as a new revision");
  fireEvent.change(screen.getByLabelText("Compare with"), {
    target: { value: "original" },
  });
  expect(screen.getByLabelText("Comparison prompt")).toHaveValue(
    revisions[0].content,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Build from this prompt" }),
  );
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/prompts/edited/build",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  expect(followJob).toHaveBeenCalledWith("build-job");
  vi.unstubAllGlobals();
});
