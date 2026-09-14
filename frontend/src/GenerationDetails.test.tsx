import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { GenerationDetails } from "./GenerationDetails";
afterEach(cleanup);
const base = {
  request: {
    prompt: "Learn TLS",
    model: "gpt-6-astra",
    instructions: "Draw packets",
  },
  job: { id: "job" },
  prompt: "Reconstructed text",
  prompt_source: "reconstructed",
  skills: [
    {
      id: "local:visual",
      name: "visual",
      version: "1",
      sha256: "abc",
      sandbox_path: "/workspace/skills/local--visual/SKILL.md",
    },
  ],
  invocations: [],
};
it("shows saved inputs, skill provenance and the historical prompt caveat", () => {
  render(<GenerationDetails data={base} />);
  expect(screen.getByText("Learn TLS")).toBeVisible();
  expect(screen.getByText("Draw packets")).toBeVisible();
  expect(screen.getByText(/Reconstructed from saved/)).toBeVisible();
  expect(screen.getByLabelText("Full Codex prompt")).toHaveValue(
    "Reconstructed text",
  );
  fireEvent.click(screen.getByText("visual"));
  expect(
    screen.getByText("/workspace/skills/local--visual/SKILL.md"),
  ).toBeVisible();
});
it("shows the captured prompt for each repair invocation", () => {
  render(
    <GenerationDetails
      data={{
        ...base,
        prompt_source: "captured",
        invocations: [
          {
            captured_at: "2026-09-14",
            phase: "generate",
            prompt: "Actual initial prompt",
            command: ["codex", "exec", "Actual initial prompt"],
          },
          {
            captured_at: "2026-09-14",
            phase: "repair",
            prompt: "Actual repair prompt",
            command: ["codex", "exec", "Actual repair prompt"],
          },
        ],
      }}
    />,
  );
  expect(screen.getByLabelText("Full Codex prompt")).toHaveValue(
    "Actual initial prompt",
  );
  fireEvent.change(screen.getByLabelText("Agent invocation"), {
    target: { value: "1" },
  });
  expect(screen.getByLabelText("Full Codex prompt")).toHaveValue(
    "Actual repair prompt",
  );
});
