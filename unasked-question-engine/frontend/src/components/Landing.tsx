import { RiskMatrix } from "./RiskMatrix";

interface Props {
  onStart: () => void;
  onDemo: () => void;
  busy?: boolean;
}

export function Landing({ onStart, onDemo, busy = false }: Props) {
  return (
    <div className="page">
      <section className="hero" aria-labelledby="hero-title">
        <div>
          <h1 id="hero-title">Find the questions your project forgot to ask.</h1>
          <p>
            Upload plans, specs or datasets. The engine reads them, looks for what is assumed but never stated, and
            ranks each gap by impact, likelihood and urgency, with the passage that led to it.
          </p>
          <ul className="hero__points">
            <li>Evidence is quote-checked against your files</li>
            <li>Works with Gemini, Groq and DeepSeek keys</li>
            <li>Triage findings and export a report</li>
          </ul>
          <div className="hero__actions">
            <button type="button" className="btn" onClick={onStart}>
              Analyze a project
            </button>
            <button type="button" className="btn btn--quiet" onClick={onDemo} disabled={busy}>
              {busy ? "Loading sample…" : "Try the sample project"}
            </button>
            <a className="btn btn--quiet" href="#how-it-works">
              How it works
            </a>
          </div>
        </div>

        <div className="sample" role="group" aria-label="Illustrative example of a finding">
          <span className="sample__tag">Illustrative example, not output from your project</span>
          <article className="finding finding--high">
            <div className="finding__meta">
              <span className="badge badge--high">High 38</span>
              <span>Missing assumption</span>
              <span>Inferred from your material</span>
            </div>
            <h2 className="finding__title">Hosting cost is capped, but expected traffic is not stated</h2>
            <p className="question" style={{ marginLeft: 0 }}>
              At what monthly usage does the 500 dollar cap stop being enough?
            </p>
            <div className="evidence" style={{ marginTop: 12 }}>
              <figure>
                <blockquote>Hosting budget is capped at 500 dollars per month.</blockquote>
                <figcaption>
                  <span>plan.md, section &quot;Budget&quot;, line 4</span>
                  <span className="tag-ok">Exact quote verified in source</span>
                </figcaption>
              </figure>
            </div>
          </article>
          <div className="sample__matrix">
            <RiskMatrix findings={[]} selected={null} decorative />
          </div>
        </div>
      </section>

      <section className="band" id="how-it-works" aria-labelledby="how-title">
        <h2 id="how-title">How it works</h2>
        <ol className="steps">
          <li>
            <h3>Add your material</h3>
            <p>Paste a description of the project or workflow, or upload PDF, Word, text, Markdown and CSV files.</p>
          </li>
          <li>
            <h3>Models review it</h3>
            <p>
              One model analyses the material, a second critiques that work independently, and a third checks the
              evidence and merges duplicates. Which ones run depends on how you configure them.
            </p>
          </li>
          <li>
            <h3>Read the ranked findings</h3>
            <p>Each finding shows where it came from, how well supported it is, and the question nobody has answered.</p>
          </li>
        </ol>
      </section>

      <section className="band" aria-labelledby="trust-title">
        <h2 id="trust-title">What you can rely on</h2>
        <div className="trust">
          <div>
            <h3>Evidence is checked, not invented</h3>
            <p>Quotes are verified against your files. Anything unsupported is labelled as an inference or hypothesis.</p>
          </div>
          <div>
            <h3>Scores are judgements</h3>
            <p>Impact, likelihood and urgency come from the models. The formula that ranks them is shown with every result.</p>
          </div>
          <div>
            <h3>Your documents are data</h3>
            <p>Text that tries to give instructions to an AI is flagged and never followed.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
