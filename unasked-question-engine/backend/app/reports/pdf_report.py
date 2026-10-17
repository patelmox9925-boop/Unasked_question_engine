"""PDF report built with reportlab. Uses the bundled Vera TrueType font so no network or system fonts are needed."""

from __future__ import annotations

import io
import os
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..schemas import AnalysisResult, Finding
from . import common as c

_FONT_DIR = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
_REGISTERED = False
_REPLACEMENTS = {"→": "->", "←": "<-", "✓": "[ok]", "✗": "[x]", "•": "-", "≥": ">=", "≤": "<=", "…": "...",
                 " ": " ", "​": ""}


def _register_fonts() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    for name, file in (("Vera", "Vera.ttf"), ("Vera-Bold", "VeraBd.ttf"), ("Vera-Italic", "VeraIt.ttf"),
                       ("Vera-BoldItalic", "VeraBI.ttf")):
        pdfmetrics.registerFont(TTFont(name, os.path.join(_FONT_DIR, file)))
    pdfmetrics.registerFontFamily("Vera", normal="Vera", bold="Vera-Bold", italic="Vera-Italic",
                                  boldItalic="Vera-BoldItalic")
    _REGISTERED = True


def _glyphs():
    return pdfmetrics.getFont("Vera").face.charToGlyph


def clean(text: str | None) -> str:
    """Escape for reportlab markup and replace characters the font cannot draw (never crash on them)."""
    glyphs = _glyphs()
    out = []
    for ch in text or "":
        ch = _REPLACEMENTS.get(ch, ch)
        for sub in ch:
            if sub in "\n\t" or sub == " " or ord(sub) in glyphs:
                out.append(sub)
            elif ord(sub) >= 32:
                out.append("?")
    return escape("".join(out))


def _styles():
    base = dict(fontName="Vera", fontSize=9.5, leading=13.5, alignment=TA_LEFT, textColor=colors.HexColor("#1d2330"))
    s = {
        "body": ParagraphStyle("body", **base),
        "small": ParagraphStyle("small", **{**base, "fontSize": 8, "leading": 11, "textColor": colors.HexColor("#4a5163")}),
        "h1": ParagraphStyle("h1", **{**base, "fontName": "Vera-Bold", "fontSize": 20, "leading": 24, "spaceAfter": 6}),
        "h2": ParagraphStyle("h2", **{**base, "fontName": "Vera-Bold", "fontSize": 13, "leading": 17, "spaceBefore": 14, "spaceAfter": 6}),
        "h3": ParagraphStyle("h3", **{**base, "fontName": "Vera-Bold", "fontSize": 11, "leading": 14.5, "spaceBefore": 10, "spaceAfter": 3}),
        "quote": ParagraphStyle("quote", **{**base, "fontName": "Vera-Italic", "fontSize": 9, "leftIndent": 10, "textColor": colors.HexColor("#33394a")}),
        "demo": ParagraphStyle("demo", **{**base, "fontName": "Vera-Bold", "backColor": colors.HexColor("#fff1c2"),
                                          "borderPadding": 6, "spaceAfter": 10}),
    }
    return s


LEVEL_COLORS = {"critical": "#9b1c1c", "high": "#b45309", "medium": "#8a6d00", "low": "#3a5a40"}


def _finding_block(rank: int, f: Finding, st, triage=None) -> list:
    level = f.priority_level.value if f.priority_level else "low"
    head = (f"{rank}. {clean(c.one_line(f.title))}")
    meta = (f'<font color="{LEVEL_COLORS[level]}"><b>{clean(c.level_label(f))}</b></font> | {clean(c.category_label(f))} | '
            f"{clean(c.STATUS_LABELS[f.epistemic_status])}" + (" | demo data" if f.origin == "demo" else ""))
    items: list = [Paragraph(head, st["h3"]), Paragraph(meta, st["small"]), Spacer(1, 4),
                   Paragraph(clean(f.explanation), st["body"]), Spacer(1, 3),
                   Paragraph(f"<b>Why it matters.</b> {clean(f.why_it_matters)}", st["body"]), Spacer(1, 3),
                   *([Paragraph(f"<b>Why it is easy to miss.</b> {clean(f.why_overlooked)}", st["body"]), Spacer(1, 3)]
                     if f.why_overlooked else []),
                   Paragraph(f"<b>Recommended action.</b> {clean(f.recommended_action)}", st["body"]), Spacer(1, 3),
                   Paragraph(f"<b>Question to answer:</b> {clean(f.critical_question)}", st["body"]), Spacer(1, 3),
                   Paragraph(f"Impact {f.impact}/10, likelihood {f.likelihood}/10, urgency {f.urgency}/10. "
                             f"{clean(f.score_explanation)}", st["small"])]
    if f.disagreement_note:
        items += [Spacer(1, 3), Paragraph(f"<b>Models disagreed.</b> {clean(f.disagreement_note)}", st["body"])]
    decision = c.triage_line((triage or {}).get(f.id))
    if decision:
        items += [Spacer(1, 3), Paragraph(f"<b>Your decision:</b> {clean(decision)}", st["body"])]
    items.append(Spacer(1, 4))
    if f.evidence:
        for ev in f.evidence:
            items += [Paragraph(f"&ldquo;{clean(ev.excerpt)}&rdquo;", st["quote"]),
                      Paragraph(f"{clean(c.evidence_location(ev))} ({clean(c.evidence_check(ev))})", st["small"]),
                      Spacer(1, 3)]
    else:
        items.append(Paragraph(f"<i>No document evidence.</i> {clean(f.evidence_note or 'Nothing in the material directly supports this.')}",
                               st["small"]))
    # Keep the heading with the first lines, but let long findings flow across pages.
    return [KeepTogether(items[:4])] + items[4:]


def build_pdf(result: AnalysisResult, triage: dict | None = None) -> bytes:
    _register_fonts()
    st = _styles()
    buffer = io.BytesIO()

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Vera", 7.5)
        canvas.setFillColor(colors.HexColor("#6b7285"))
        label = "Unasked Question Report" + (" - DEMO DATA" if c.is_demo(result) else "")
        canvas.drawString(18 * mm, 10 * mm, label)
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title="Unasked Question Report", author="The Unasked Question Engine")
    story: list = [Paragraph("Unasked Question Report", st["h1"])]
    if c.is_demo(result):
        story.append(Paragraph(clean(c.DEMO_NOTICE), st["demo"]))
    story += [Paragraph(f"Generated {c.timestamp(result.created_at)}", st["small"]), Spacer(1, 3),
              Paragraph(f"<i>{clean(c.GENERAL_NOTICE)}</i>", st["small"])]

    story.append(Paragraph("Summary", st["h2"]))
    story.append(Paragraph(clean(result.overall_summary or "No summary was produced."), st["body"]))
    if result.risk_summary:
        rs = result.risk_summary
        counts = [[k.capitalize(), str(n)] for k, n in rs.counts.items()]
        table = Table([["Level", "Findings"]] + counts, colWidths=[40 * mm, 25 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Vera"), ("FONTNAME", (0, 0), (-1, 0), "Vera-Bold"),
                                   ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey),
                                   ("GRID", (0, 1), (-1, -1), 0.25, colors.lightgrey)]))
        story += [Spacer(1, 6), Paragraph(f"<b>Overall risk level: {clean(rs.overall_level.value.capitalize())}</b>", st["body"]),
                  Paragraph(clean(rs.explanation), st["small"]), Spacer(1, 4), table]

    decided = c.triage_counts(triage or {})
    if decided:
        story += [Spacer(1, 4), Paragraph(f"<b>Your triage so far:</b> {clean(decided)}.", st["body"])]

    if result.warnings:
        story.append(Paragraph("Warnings", st["h2"]))
        story += [Paragraph(f"- {clean(c.one_line(w))}", st["body"]) for w in result.warnings]

    if result.understanding:
        u = result.understanding
        story.append(Paragraph("What the engine understood", st["h2"]))
        story.append(Paragraph(clean(u.summary), st["body"]))
        story += [Paragraph(f"- {clean(c.one_line(x.statement))}", st["small"]) for x in u.facts]
        if u.open_items:
            story.append(Spacer(1, 3))
            story.append(Paragraph("Left open by the material itself:", st["small"]))
            story += [Paragraph(f"- {clean(c.one_line(x))}", st["small"]) for x in u.open_items]

    story.append(Paragraph("Findings, highest priority first", st["h2"]))
    if not result.findings:
        story.append(Paragraph("No findings were produced.", st["body"]))
    for i, f in enumerate(result.findings, 1):
        story += _finding_block(i, f, st, triage)

    story.append(Paragraph("Unanswered questions", st["h2"]))
    if result.unanswered_questions:
        story += [Paragraph(f"{i}. {clean(c.one_line(q))}", st["body"]) for i, q in enumerate(result.unanswered_questions, 1)]
    else:
        story.append(Paragraph("None recorded.", st["body"]))

    story.append(Paragraph("Method", st["h2"]))
    if result.risk_summary:
        story.append(Paragraph(clean(result.risk_summary.formula), st["small"]))
        story.append(Spacer(1, 3))
    if result.perspectives:
        story.append(Paragraph("Perspectives applied: " + clean("; ".join(p.name for p in result.perspectives)) + ".", st["small"]))
        story.append(Spacer(1, 3))
    story += [Paragraph(clean(m), st["small"]) for m in c.models_line(result)]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
