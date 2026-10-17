import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";
import type { AnalysisStatus, AnalysisStep, StepStatus } from "../types";
import { makeConfig, makeResult } from "./fixtures";

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function mockFetch(handler: Handler) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init));
  vi.stubGlobal("fetch", spy);
  return spy;
}

const steps = (statuses: string[]): AnalysisStep[] =>
  ["extract", "context", "analysis", "critique", "synthesis", "prioritize"].map((key, i) => ({
    key,
    label: `Step ${key}`,
    status: (statuses[i] ?? "pending") as StepStatus,
    detail: null,
  }));

const project = {
  project_id: "p1",
  created_at: "2026-10-17T08:00:00Z",
  has_description: true,
  documents: [],
  rejected: [{ filename: "x.exe", code: "unsupported_type", message: "Unsupported file type." }],
  total_chunks: 2,
};

async function startAnalysisFlow(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Analyze a project" }));
  await user.type(await screen.findByLabelText(/What are you building/), "A small tool");
  await screen.findByText("Model A: ready");
  await user.click(screen.getByRole("button", { name: "Analyze project" }));
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("shows the landing page with a clearly labelled example", () => {
    mockFetch(() => json(makeConfig()));
    render(<App />);
    expect(screen.getByRole("heading", { level: 1, name: /Find the questions your project forgot to ask/ })).toBeInTheDocument();
    expect(screen.getByText(/Illustrative example, not output from your project/)).toBeInTheDocument();
  });

  it("runs the whole flow: upload, progress, results", async () => {
    const user = userEvent.setup();
    let polls = 0;
    const spy = mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig());
      if (url === "/api/projects" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analyze") {
        return json({ project_id: "p1", state: "running", steps: steps(["done", "done", "running"]), result: null, error: null }, 202);
      }
      if (url === "/api/projects/p1/analysis") {
        polls += 1;
        const done = polls >= 2;
        const body: AnalysisStatus = {
          project_id: "p1",
          state: done ? "done" : "running",
          steps: steps(done ? Array(6).fill("done") : ["done", "done", "done", "running"]),
          result: done ? makeResult() : null,
          error: null,
        };
        return json(body);
      }
      return json({ error: { code: "not_found", message: "?" } }, 404);
    });
    render(<App />);
    await startAnalysisFlow(user);

    expect(await screen.findByRole("heading", { name: "Analyzing your project" })).toBeInTheDocument();
    expect(screen.getByText(/x\.exe: Unsupported file type/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Analysis results" }, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Shared password is the only login control" })).toBeInTheDocument();

    const post = spy.mock.calls.find(([u, i]) => u === "/api/projects" && i?.method === "POST")!;
    expect((post[1]!.body as FormData).get("description")).toBe("A small tool");
  });

  it("explains a failed analysis and offers to run it again", async () => {
    const user = userEvent.setup();
    let analyses = 0;
    mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig());
      if (url === "/api/projects" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analyze") {
        analyses += 1;
        return json({ project_id: "p1", state: "running", steps: steps([]), result: null, error: null }, 202);
      }
      if (url === "/api/projects/p1/analysis") {
        return json({
          project_id: "p1",
          state: "failed",
          steps: steps(["done", "done", "failed", "skipped", "skipped", "skipped"]),
          result: null,
          error: "Model A failed on every configured provider (groq/model-a: auth). No analysis was produced.",
        });
      }
      return json({}, 404);
    });
    render(<App />);
    await startAnalysisFlow(user);

    expect(await screen.findByRole("heading", { name: "The analysis stopped" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("No analysis was produced");
    await user.click(screen.getByRole("button", { name: "Run the analysis again" }));
    await waitFor(() => expect(analyses).toBe(2));
  });

  it("shows the server's reason when the project cannot be created", async () => {
    const user = userEvent.setup();
    mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig());
      if (url === "/api/projects" && init?.method === "POST") {
        return json({ error: { code: "empty_input", message: "Provide a project description or at least one readable file." } }, 422);
      }
      return json({}, 404);
    });
    render(<App />);
    await startAnalysisFlow(user);
    expect(await screen.findByRole("alert")).toHaveTextContent("Provide a project description or at least one readable file.");
    expect(screen.getByRole("heading", { name: "Analyze a project" })).toBeInTheDocument();
  });

  it("copes with an unreachable server", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Analyze a project" }));
    expect(await screen.findByText("Server unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Analyze project" })).toBeDisabled();
  });

  it("answers follow-up questions with evidence and grounding", async () => {
    const user = userEvent.setup();
    mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig());
      if (url === "/api/projects" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analyze") return json({ project_id: "p1", state: "running", steps: steps([]), result: null, error: null }, 202);
      if (url === "/api/projects/p1/analysis") return json({ project_id: "p1", state: "done", steps: steps(Array(6).fill("done")), result: makeResult(), error: null });
      if (url === "/api/projects/p1/chat") {
        expect(JSON.parse(String(init!.body)).question).toBe("What is the budget?");
        return json({
          answer: "The budget is **capped** at 500 dollars.\n\n<script>window.__x=1</script>",
          grounding: "grounded",
          evidence: [{ chunk_id: "desc-c1", source_label: "Project description, line 2", filename: "Project description", excerpt: "capped at 500 dollars", quote_verified: true }],
          finding_ids: ["f2"],
          model: { role: "C", provider: "gemini", model: "model-c", succeeded: true, used_as_fallback: false },
          warnings: [],
        });
      }
      return json({}, 404);
    });
    render(<App />);
    await startAnalysisFlow(user);
    await user.click(await screen.findByRole("tab", { name: /Ask a follow-up/ }, { timeout: 4000 }));
    await user.type(screen.getByLabelText("Ask a follow-up question"), "What is the budget?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("capped", { selector: "strong" })).toBeInTheDocument();
    expect(screen.getByText("Grounded in your material")).toBeInTheDocument();
    expect(screen.getByText("Exact quote verified in source")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    await user.click(screen.getByRole("button", { name: /Related finding: Hosting cost is capped/ }));
    expect(screen.getByRole("tab", { name: /Findings/ })).toHaveAttribute("aria-selected", "true");
  });

  const analysedFetch = (exportResponse: () => Response) =>
    mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig());
      if (url === "/api/projects" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analyze") return json({ project_id: "p1", state: "running", steps: steps([]), result: null, error: null }, 202);
      if (url === "/api/projects/p1/analysis") return json({ project_id: "p1", state: "done", steps: steps(Array(6).fill("done")), result: makeResult(), error: null });
      if (url.startsWith("/api/projects/p1/export.")) return exportResponse();
      return json({ error: { code: "not_found", message: "Not Found" } }, 404);
    });

  it("downloads the PDF and Markdown reports", async () => {
    const user = userEvent.setup();
    const created = vi.fn(() => "blob:report");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    const spy = analysedFetch(() => new Response("%PDF-1.4", { status: 200 }));
    render(<App />);
    await startAnalysisFlow(user);
    await user.click(await screen.findByRole("button", { name: "Download PDF" }, { timeout: 4000 }));
    expect(await screen.findByText("Downloaded the PDF report.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(await screen.findByText("Downloaded the Markdown report.")).toBeInTheDocument();
    expect(created).toHaveBeenCalledTimes(2);
    expect(spy.mock.calls.map((c) => String(c[0]))).toEqual(
      expect.arrayContaining(["/api/projects/p1/export.pdf", "/api/projects/p1/export.md"]),
    );
  });

  it("explains export failures instead of failing silently", async () => {
    const user = userEvent.setup();
    analysedFetch(() => json({ error: { code: "no_analysis", message: "x" } }, 409));
    render(<App />);
    await startAnalysisFlow(user);
    await user.click(await screen.findByRole("button", { name: "Download PDF" }, { timeout: 4000 }));
    expect(await screen.findByText("The report could not be generated.")).toBeInTheDocument();
  });

  it("opens the labelled sample project without any model configured", async () => {
    const user = userEvent.setup();
    const spy = mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig(false));
      if (url === "/api/demo" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analysis") {
        return json({ project_id: "p1", state: "done", steps: [], result: makeResult({ origin: "demo" }), error: null });
      }
      return json({ error: { code: "not_found", message: "Not Found" } }, 404);
    });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Try the sample project" }));
    expect(await screen.findByRole("heading", { name: "Analysis results" })).toBeInTheDocument();
    expect(screen.getByText(/Demo data: these are predefined sample results/)).toBeInTheDocument();
    expect(spy.mock.calls.some((c) => String(c[0]).endsWith("/analyze"))).toBe(false);
  });

  it("offers the sample project from the workspace when no model is configured", async () => {
    const user = userEvent.setup();
    mockFetch((url, init) => {
      if (url === "/api/config/status") return json(makeConfig(false));
      if (url === "/api/demo" && init?.method === "POST") return json(project, 201);
      if (url === "/api/projects/p1/analysis") {
        return json({ project_id: "p1", state: "done", steps: [], result: makeResult({ origin: "demo" }), error: null });
      }
      return json({ error: { code: "not_found", message: "Not Found" } }, 404);
    });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Analyze a project" }));
    await screen.findByText("Analysis is unavailable");
    await user.click(screen.getAllByRole("button", { name: "Try the sample project" })[0]);
    expect(await screen.findByText(/Demo data: these are predefined sample results/)).toBeInTheDocument();
  });

  it("shows an error and returns to the workspace if the sample cannot load", async () => {
    const user = userEvent.setup();
    mockFetch((url) => {
      if (url === "/api/config/status") return json(makeConfig(false));
      return json({ error: { code: "boom", message: "Sample failed." } }, 500);
    });
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Try the sample project" }));
    expect(await screen.findByText("Sample failed.")).toBeInTheDocument();
  });
});
