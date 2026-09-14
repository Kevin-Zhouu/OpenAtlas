import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { PromptEditor, SkillsManager } from "./GenerationStudio";
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("shows default teaching prompt, edits, restores and previews the complete prompt", async () => {
  const fetcher = vi.fn(async (url: string) => ({
    ok: true,
    json: async () =>
      url.endsWith("/preview")
        ? { prompt: "Full immutable contract" }
        : { default: "Teach for {{reading_minutes}} minutes" },
  }));
  vi.stubGlobal("fetch", fetcher);
  const change = vi.fn();
  render(<PromptEditor onChange={change} />);
  await waitFor(() =>
    expect(screen.getByLabelText("Teaching and design prompt")).toHaveValue(
      "Teach for {{reading_minutes}} minutes",
    ),
  );
  fireEvent.change(screen.getByLabelText("Teaching and design prompt"), {
    target: { value: "Custom teaching" },
  });
  expect(change).toHaveBeenCalledWith("Custom teaching");
  fireEvent.click(screen.getByText("Restore default"));
  expect(change).toHaveBeenCalledWith(null);
  fireEvent.click(screen.getByText("Preview full Codex prompt"));
  expect(
    await screen.findByText("Full immutable contract"),
  ).toBeInTheDocument();
});
it("lists skills, edits files with a revision token and creates a skill", async () => {
  const fetcher = vi.fn(async (url: string, options?: RequestInit) => ({
    ok: true,
    json: async () => {
      if (url.endsWith("skills"))
        return [
          {
            id: "local:sample",
            name: "sample",
            description: "Sample",
            valid: true,
          },
        ];
      if (url.endsWith("skills/create")) return { id: "local:sample" };
      if (url.includes("&path="))
        return { content: "Original", revision: "abc" };
      if (options?.method === "PUT")
        return { content: "Edited", revision: "def" };
      return { files: ["SKILL.md"] };
    },
  }));
  vi.stubGlobal("fetch", fetcher);
  render(<SkillsManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "sample Installed" }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Skill file contents")).toHaveValue(
      "Original",
    ),
  );
  fireEvent.change(screen.getByLabelText("Skill file contents"), {
    target: { value: "Edited" },
  });
  expect(
    screen.getByRole("button", { name: "sample Installed" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByText("Save file"));
  await screen.findByText(
    "File saved. Future generations will use this version.",
  );
  expect(fetcher).toHaveBeenCalledWith(
    "/api/skill-files",
    expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({
        skill_id: "local:sample",
        path: "SKILL.md",
        content: "Edited",
        revision: "abc",
      }),
    }),
  );
  fireEvent.change(screen.getByLabelText("New skill name"), {
    target: { value: "sample" },
  });
  fireEvent.click(screen.getByText("Create skill"));
  expect(await screen.findByText("Skill created")).toBeInTheDocument();
});
it("shows installation errors without replacing installed skills", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: !url.endsWith("install"),
      json: async () =>
        url.endsWith("install")
          ? { detail: "ZIP contains links or special files" }
          : [],
    })),
  );
  render(<SkillsManager />);
  fireEvent.change(screen.getByLabelText("Install skill ZIP"), {
    target: { files: [new File(["bad"], "skill.zip")] },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "ZIP contains links",
  );
});
