import { applyFilters, emptyFilters, isFiltering, toggled } from "../lib/filters";
import { validateFiles } from "../lib/format";
import { FINDINGS } from "./fixtures";

describe("applyFilters", () => {
  it("returns everything, best priority first, with no filters", () => {
    expect(applyFilters(FINDINGS, emptyFilters()).map((f) => f.id)).toEqual(["f1", "f2", "f3"]);
  });

  it("filters by severity, category, support and text", () => {
    const f = emptyFilters();
    expect(applyFilters(FINDINGS, { ...f, levels: new Set(["low"]) }).map((x) => x.id)).toEqual(["f3"]);
    expect(applyFilters(FINDINGS, { ...f, categories: new Set(["risk"]) }).map((x) => x.id)).toEqual(["f1"]);
    expect(applyFilters(FINDINGS, { ...f, statuses: new Set(["reasonable_inference"]) }).map((x) => x.id)).toEqual(["f2"]);
    expect(applyFilters(FINDINGS, { ...f, query: "  TRAFFIC " }).map((x) => x.id)).toEqual(["f2"]);
    expect(applyFilters(FINDINGS, { ...f, query: "no such thing" })).toEqual([]);
  });

  it("combines filters with AND", () => {
    const f = { ...emptyFilters(), levels: new Set(["critical", "high"] as const), categories: new Set(["missing_assumption"] as const) };
    expect(applyFilters(FINDINGS, f as never).map((x) => x.id)).toEqual(["f2"]);
  });

  it("sorts by another dimension and does not mutate its input", () => {
    const copy = [...FINDINGS];
    const sorted = applyFilters(FINDINGS, { ...emptyFilters(), sort: "urgency" });
    expect(sorted.map((x) => x.id)).toEqual(["f1", "f2", "f3"]);
    expect(applyFilters([FINDINGS[2], FINDINGS[0]], { ...emptyFilters(), sort: "likelihood" })[0].id).toBe("f1");
    expect(FINDINGS).toEqual(copy);
  });

  it("knows when filtering is active and toggles sets immutably", () => {
    expect(isFiltering(emptyFilters())).toBe(false);
    expect(isFiltering({ ...emptyFilters(), query: "x" })).toBe(true);
    const a = new Set(["x"]);
    const b = toggled(a, "y");
    expect([...a]).toEqual(["x"]);
    expect([...b].sort()).toEqual(["x", "y"]);
    expect([...toggled(b, "x")]).toEqual(["y"]);
  });
});

describe("validateFiles", () => {
  const limits = { max_upload_mb: 1, max_files: 2 };
  const file = (name: string, size = 10) => new File([new Uint8Array(size)], name);

  it("accepts supported types and explains rejections", () => {
    const { accepted, problems } = validateFiles(
      [file("a.pdf"), file("b.exe"), file("c.csv", 2 * 1024 * 1024), file("d.txt", 0), file("e.MD"), file("f.docx")],
      limits,
    );
    expect(accepted.map((f) => f.name)).toEqual(["a.pdf", "e.MD"]);
    expect(problems.join("\n")).toMatch(/b\.exe: unsupported type/);
    expect(problems.join("\n")).toMatch(/c\.csv: larger than 1 MB/);
    expect(problems.join("\n")).toMatch(/d\.txt: the file is empty/);
    expect(problems.join("\n")).toMatch(/f\.docx: only 2 files/);
  });
});
