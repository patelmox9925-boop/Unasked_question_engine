import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FindingRow } from "../components/FindingRow";
import { Markdown } from "../components/Markdown";
import { ResultsView } from "../components/ResultsView";
import { Workspace } from "../components/Workspace";
import { FINDINGS, makeConfig, makeFinding, makeResult } from "./fixtures";

describe("Markdown", () => {
  it("renders formatting instead of raw syntax", () => {
    const { container } = render(<Markdown>{"**bold** and a list:\n\n- one\n- two"}</Markdown>);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.textContent).not.toContain("**");
  });

  it("never renders scripts, raw HTML, images or javascript: links", () => {
    const evil = [
      "<script>window.__pwned = 1</script>",
      '<img src=x onerror="window.__pwned = 2">',
      "![pic](http://example.com/a.png)",
      "[click](javascript:alert(1))",
      '<a href="javascript:alert(2)" onclick="alert(3)">raw</a>',
    ].join("\n\n");
    const { container } = render(<Markdown>{evil}</Markdown>);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.innerHTML).not.toMatch(/onerror|onclick|javascript:/i);
    expect((window as unknown as { __pwned?: number }).__pwned).toBeUndefined();
  });

  it("opens links safely", () => {
    render(<Markdown>{"[docs](https://example.com)"}</Markdown>);
    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(link).toHaveAttribute("target", "_blank");
  });
});

const rowProps = {
  rank: 1,
  selected: false,
  flash: false,
  triage: undefined,
  onSelect: () => {},
  onTriage: () => {},
  onEvidence: () => {},
  onCopyQuestion: () => {},
  onCopyFinding: () => {},
  onAsk: () => {},
};

describe("FindingRow", () => {
  it("shows the unanswered question collapsed and details when expanded", async () => {
    const user = userEvent.setup();
    let open = false;
    const ui = () => <FindingRow {...rowProps} finding={FINDINGS[0]} open={open} onToggle={() => (open = !open)} />;
    const { rerender } = render(ui());
    expect(screen.getByText("How will access be revoked when someone leaves?")).toBeInTheDocument();
    const toggle = screen.getByRole("button", { name: /Shared password/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Recommended action")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Priority Critical, score 71 out of 100/)).toBeInTheDocument();

    await user.click(toggle);
    rerender(ui());
    expect(screen.getByRole("button", { name: /Shared password/ })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Introduce individual accounts.")).toBeInTheDocument();
    expect(screen.getByText("Exact quote verified in source")).toBeInTheDocument();
    expect(screen.getByText(/Project description, section "Plan", line 4/)).toBeInTheDocument();
  });

  it("is honest when there is no evidence, a quote is unverified, or a passage is only related", () => {
    const { rerender } = render(<FindingRow {...rowProps} finding={FINDINGS[2]} open onToggle={() => {}} />);
    expect(screen.getByText(/No passage in your material directly supports this item/)).toBeInTheDocument();
    expect(screen.getByText(/treat it as unverified/)).toBeInTheDocument();
    expect(screen.getByText("Unverified hypothesis")).toBeInTheDocument();

    const unverified = makeFinding({
      evidence: [{ kind: "cited", chunk_id: "c", source_label: "x.md, line 1", filename: "x.md", excerpt: "Start of the section", quote_verified: false }],
    });
    rerender(<FindingRow {...rowProps} finding={unverified} open onToggle={() => {}} />);
    expect(screen.getByText(/could not be verified/)).toBeInTheDocument();
    expect(screen.queryByText("Exact quote verified in source")).not.toBeInTheDocument();

    const related = makeFinding({
      evidence: [{ kind: "related", chunk_id: "c", source_label: "x.md, line 1", filename: "x.md", excerpt: "Nearby text", quote_verified: false }],
    });
    rerender(<FindingRow {...rowProps} finding={related} open onToggle={() => {}} />);
    expect(screen.getByText(/The model did not cite it/)).toBeInTheDocument();
  });

  it("shows model disagreement, demo marking and saves a decision", async () => {
    const user = userEvent.setup();
    const onTriage = vi.fn();
    render(
      <FindingRow {...rowProps} onTriage={onTriage} finding={makeFinding({ disagreement_note: "Scored differently.", origin: "demo" })} open onToggle={() => {}} />,
    );
    expect(screen.getByText(/Models disagreed/)).toBeInTheDocument();
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Accept, needs action" }));
    expect(onTriage).toHaveBeenCalledWith({ status: "accepted", note: "" });
  });
});

describe("Workspace", () => {
  const noop = () => {};
  const base = { configError: null, busy: false, error: null, onRetryConfig: noop };

  it("blocks submission until there is input, then submits description and files", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Workspace {...base} config={makeConfig(true)} onSubmit={onSubmit} />);
    const button = screen.getByRole("button", { name: "Analyze project" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Add a description or at least one file.")).toBeInTheDocument();

    await user.type(screen.getByLabelText(/What are you building/), "A small tool");
    expect(button).toBeEnabled();

    const file = new File(["hello"], "notes.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("Choose documents to upload"), file);
    expect(screen.getByText("notes.txt")).toBeInTheDocument();

    await user.click(button);
    expect(onSubmit).toHaveBeenCalledWith("A small tool", [file]);
  });

  it("explains unsupported files and lets people remove a file", async () => {
    const user = userEvent.setup({ applyAccept: false });
    render(<Workspace {...base} config={makeConfig(true)} onSubmit={noop} />);
    const input = screen.getByLabelText("Choose documents to upload");
    await user.upload(input, [new File(["x"], "malware.exe"), new File(["ok"], "good.md")]);
    expect(screen.getByRole("alert")).toHaveTextContent("malware.exe: unsupported type");
    await user.click(screen.getByRole("button", { name: "Remove good.md" }));
    expect(screen.queryByText("good.md")).not.toBeInTheDocument();
  });

  it("flags an over-long description", async () => {
    const user = userEvent.setup();
    render(<Workspace {...base} config={makeConfig(true)} onSubmit={noop} />);
    await user.click(screen.getByLabelText(/What are you building/));
    await user.paste("x".repeat(101));
    expect(screen.getByText(/101 \/ 100 characters/)).toHaveClass("counter--over");
    expect(screen.getByRole("button", { name: "Analyze project" })).toBeDisabled();
  });

  it("disables analysis and says why when no model is configured", () => {
    render(<Workspace {...base} config={makeConfig(false)} onSubmit={noop} />);
    expect(screen.getByRole("button", { name: "Analyze project" })).toBeDisabled();
    expect(screen.getByText("Analysis is unavailable")).toBeInTheDocument();
    expect(screen.getByText("Add an API key under Models to analyze.")).toBeInTheDocument();
  });

  it("shows server errors with a retry", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<Workspace {...base} config={null} configError="Could not reach the server." onRetryConfig={retry} onSubmit={noop} error="Upload failed" />);
    expect(screen.getAllByRole("alert").map((a) => a.textContent).join(" ")).toMatch(/Upload failed/);
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalled();
  });
});

describe("ResultsView", () => {
  it("shows summary, warnings, failed models and ranked findings", () => {
    render(<ResultsView result={makeResult()} />);
    expect(screen.getByText("Access control and cost are the main blind spots.")).toBeInTheDocument();
    expect(screen.getByText(/Independent critique \(Model B\) was unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Model B: deepseek\/model-b failed, not consulted/)).toBeInTheDocument();
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(FINDINGS.map((f) => f.title));
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
  });

  it("filters by severity and offers a way back from an empty result", async () => {
    const user = userEvent.setup();
    render(<ResultsView result={makeResult()} />);
    await user.click(screen.getByRole("button", { name: /^Low/ }));
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Shared password/ })).not.toBeInTheDocument();

    await user.type(screen.getByRole("searchbox"), "zzz-no-match");
    expect(screen.getByText("No findings match these filters")).toBeInTheDocument();
    await user.click(within(screen.getByText("No findings match these filters").closest("div")!).getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
  });

  it("expands a card and switches tabs with the keyboard", async () => {
    const user = userEvent.setup();
    render(<ResultsView result={makeResult()} />);
    await user.click(screen.getByRole("button", { name: /Hosting cost is capped/ }));
    expect(screen.getByText(/Not directly evidenced/)).toBeInTheDocument();

    const tab = screen.getByRole("tab", { name: /Findings/ });
    tab.focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: /Unanswered questions/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Who is on call after launch?")).toBeInTheDocument();
    await user.click(screen.getAllByRole("button", { name: "View finding" })[0]);
    expect(screen.getByRole("tab", { name: /Findings/ })).toHaveAttribute("aria-selected", "true");
  });

  it("handles a result with no findings", () => {
    render(<ResultsView result={makeResult({ findings: [], unanswered_questions: [], risk_summary: null, warnings: [] })} />);
    expect(screen.getByText("Nothing to show")).toBeInTheDocument();
  });

  it("labels demo results clearly, keeps export (labelled in the file) and hides chat", async () => {
    const user = userEvent.setup();
    render(<ResultsView result={makeResult({ origin: "demo" })} />);
    expect(screen.getByText(/predefined sample results, not an analysis of your project/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Ask a follow-up/ }));
    expect(screen.getByText(/need a live model/)).toBeInTheDocument();
  });

  it("filters by risk matrix square and clears with Escape", async () => {
    const user = userEvent.setup();
    render(<ResultsView result={makeResult()} />);
    await user.click(screen.getByRole("button", { name: /Impact 9-10, likelihood 7-8: 1 finding/ }));
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.getByText("Showing 3 of 3")).toBeInTheDocument();
  });

  it("supports keyboard shortcuts: move, open, and show help", async () => {
    const user = userEvent.setup();
    render(<ResultsView result={makeResult()} />);
    await user.keyboard("j");
    await user.keyboard("o");
    expect(screen.getByRole("button", { name: /Hosting cost is capped/ })).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("?");
    expect(screen.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeInTheDocument();
  });
});
