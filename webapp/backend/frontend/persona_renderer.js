/* Canonical, deterministic persona-image renderer.
 *
 * Groq (the backend) already decided WHAT a persona contains - this module
 * only decides HOW it looks, applied identically to every persona, every
 * time. It draws straight onto a fixed 1600x880 canvas via the Canvas 2D
 * API rather than screenshotting the DOM (no html2canvas dependency, no
 * remote image fetch), so the exported PNG is always exactly 1600x880 and
 * never blocked by a tainted-canvas/CORS error on download.
 *
 * The renderer never invents content: it only lays out fields already
 * present on the validated persona object returned by
 * /api/figjam/generate-personas (the same object the FigJam push and the
 * existing persona-card preview already use) - no second LLM call, no new
 * facts, no fabricated photo, no placeholder demographic lines for fields
 * the research doesn't support.
 */

const PERSONA_CANVAS_WIDTH = 1600;
const PERSONA_CANVAS_HEIGHT = 880;
const PERSONA_LEFT_WIDTH = 560;
const PERSONA_RIGHT_WIDTH = 1040;
const PERSONA_PHOTO_HEIGHT = 550;
const PERSONA_PANEL_HEIGHT = PERSONA_CANVAS_HEIGHT - PERSONA_PHOTO_HEIGHT;
const PERSONA_CONTENT_X = PERSONA_LEFT_WIDTH + 55;
const PERSONA_CONTENT_WIDTH = 900;
const PERSONA_TOP_PADDING = 55;
const PERSONA_BOTTOM_PADDING = 45;
const PERSONA_PANEL_PAD_X = 40;

const PERSONA_FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
const PERSONA_INK = "#14171c";
const PERSONA_MUTED = "#6b7178";
const PERSONA_LINE = "#D9D9D9";
const PERSONA_PANEL_BG = "#111111";
const PERSONA_PHOTO_BG = "#E8E8E8";
const PERSONA_RIGHT_BG = "#f7f8f9";
const PERSONA_ACCENT = "#1f6f4a";

// Largest tier that fits real content is used; smaller tiers only kick in
// for an unusually long persona - still fully legible, never "unreadable",
// and text is NEVER truncated at any tier (see computeLayout/drawLayout:
// every wrapped line is always drawn in full).
const SIZE_TIERS = [
  { quote: 30, heading: 20, body: 15.5, gridHeading: 15, gridBody: 14, lineHeight: 1.5, gridLineHeight: 1.4, blockGap: 26, itemGap: 8 },
  { quote: 27, heading: 19, body: 14.5, gridHeading: 14, gridBody: 13.5, lineHeight: 1.45, gridLineHeight: 1.35, blockGap: 20, itemGap: 7 },
  { quote: 24, heading: 18, body: 13.5, gridHeading: 13.5, gridBody: 13, lineHeight: 1.4, gridLineHeight: 1.3, blockGap: 16, itemGap: 6 },
];

function personaInitialsFor(name) {
  return (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
}

function wrapLines(ctx, text, maxWidth) {
  const paragraphs = String(text || "").split("\n");
  const lines = [];
  for (const para of paragraphs) {
    const words = para.split(/\s+/).filter(Boolean);
    if (words.length === 0) { lines.push(""); continue; }
    let current = words[0];
    for (let i = 1; i < words.length; i++) {
      const attempt = `${current} ${words[i]}`;
      if (ctx.measureText(attempt).width <= maxWidth) {
        current = attempt;
      } else {
        lines.push(current);
        current = words[i];
      }
    }
    lines.push(current);
  }
  return lines;
}

// Conservative de-duplication only: drops an item that's a near-exact
// repeat of one already kept (case/whitespace-insensitive equality, or one
// fully contains the other). Never drops a distinct finding - the explicit
// rule is "remove repetition, not information".
function dedupeItems(items) {
  const kept = [];
  const seenNormalized = [];
  (items || []).forEach((raw) => {
    const item = (raw || "").trim();
    if (!item) return;
    const norm = item.toLowerCase();
    const isDuplicate = seenNormalized.some((s) => s === norm || s.includes(norm) || norm.includes(s));
    if (!isDuplicate) { kept.push(item); seenNormalized.push(norm); }
  });
  return kept;
}

function measureBulletsHeight(ctx, items, width, fontSize, lineHeightRatio, itemGap) {
  ctx.font = `400 ${fontSize}px ${PERSONA_FONT_FAMILY}`;
  let total = 0;
  items.forEach((item) => {
    total += wrapLines(ctx, `•  ${item}`, width).length * fontSize * lineHeightRatio;
  });
  total += Math.max(0, items.length - 1) * itemGap;
  return total;
}

function buildPersonaSections(persona) {
  const quote = persona.representative_quote || {};
  const quoteText = quote.text && quote.text.trim() ? quote.text.trim() : null;
  const evidenceIds = persona.evidence || [];
  const evidenceCount = persona.evidence_count ?? evidenceIds.length;
  const participants = persona.participant_coverage || [];

  const categories = [
    { label: "GOALS & AMBITIONS", items: dedupeItems(persona.goals) },
    { label: "FRUSTRATIONS", items: dedupeItems(persona.pain_points) },
    { label: "BEHAVIOURS", items: dedupeItems(persona.behaviours) },
    { label: "NEEDS", items: dedupeItems(persona.needs) },
    { label: "MOTIVATIONS", items: dedupeItems(persona.motivations) },
  ].filter((c) => c.items.length > 0);

  const background = (persona.short_description || "").trim();
  const fallbackLead = evidenceIds.length
    ? `Behavioural summary based on ${evidenceCount} research finding${evidenceCount === 1 ? "" : "s"}` +
      `${participants.length ? ` from ${participants.length} participant${participants.length === 1 ? "" : "s"}` : ""}.`
    : "No representative statement identified in research.";

  // A short, human line establishing the persona is research-backed -
  // never the raw evidence ids/confidence label themselves, which belong
  // in the app's "View Research Evidence" panel, not a presentation-ready
  // export.
  const provenanceText = participants.length > 0
    ? `Research-backed · Based on ${participants.length} participant${participants.length === 1 ? "" : "s"}`
    : (evidenceIds.length > 0 ? "Research-backed" : null);

  return {
    quoteText, isVerbatim: !!quote.is_verbatim, background, fallbackLead,
    evidenceIds, participants, confidence: persona.confidence, evidenceCount, categories, provenanceText,
  };
}

// Single source of truth for vertical position shared by both the fit
// check (does this tier fit in 880px?) and the actual drawing pass, so
// measuring and painting can never drift apart.
function computeLayout(ctx, sections, tier) {
  const items = [];
  let cursorY = PERSONA_TOP_PADDING;

  const isQuote = !!sections.quoteText;
  const leadWidth = isQuote ? PERSONA_CONTENT_WIDTH - 40 : PERSONA_CONTENT_WIDTH;
  const leadText = sections.quoteText || sections.fallbackLead;
  ctx.font = `700 ${tier.quote}px ${PERSONA_FONT_FAMILY}`;
  const leadLines = wrapLines(ctx, leadText, leadWidth);
  const leadHeight = leadLines.length * tier.quote * 1.25;
  const tag = isQuote
    ? (sections.isVerbatim ? null : "Synthesized statement, not a direct quote")
    : "Evidence-based summary";
  items.push({ type: "lead", lines: leadLines, y: cursorY, fontSize: tier.quote, isQuote, tag, x: isQuote ? 40 : 0 });
  cursorY += leadHeight;
  if (tag) cursorY += 22;
  cursorY += tier.blockGap;

  items.push({ type: "divider", y: cursorY });
  cursorY += 1 + tier.blockGap;

  if (sections.background) {
    ctx.font = `700 ${tier.heading}px ${PERSONA_FONT_FAMILY}`;
    items.push({ type: "heading", text: "BACKGROUND", y: cursorY, fontSize: tier.heading });
    cursorY += tier.heading * 1.2 + 10;

    ctx.font = `400 ${tier.body}px ${PERSONA_FONT_FAMILY}`;
    const bgLines = wrapLines(ctx, sections.background, PERSONA_CONTENT_WIDTH);
    items.push({ type: "paragraph", lines: bgLines, y: cursorY, fontSize: tier.body, lineHeight: tier.lineHeight });
    cursorY += bgLines.length * tier.body * tier.lineHeight;
    cursorY += tier.blockGap + 6;
  }

  const cols = 3;
  const colGap = 32;
  const colWidth = (PERSONA_CONTENT_WIDTH - colGap * (cols - 1)) / cols;
  for (let i = 0; i < sections.categories.length; i += cols) {
    const rowCats = sections.categories.slice(i, i + cols);
    const headingHeight = tier.gridHeading * 1.2;
    const colHeights = rowCats.map((cat) =>
      measureBulletsHeight(ctx, cat.items, colWidth, tier.gridBody, tier.gridLineHeight, tier.itemGap));
    const rowHeight = Math.max(...colHeights);
    items.push({
      type: "grid-row", cats: rowCats, y: cursorY, colWidth, colGap, headingHeight,
      fontSize: tier.gridBody, headingFontSize: tier.gridHeading, lineHeight: tier.gridLineHeight, itemGap: tier.itemGap,
    });
    cursorY += headingHeight + 10 + rowHeight + tier.blockGap;
  }

  // Deliberately no raw evidence ids, participant id lists, or confidence
  // labels in the exported image - those are research-traceability detail
  // (available in the app's "View Research Evidence" panel), not part of
  // a clean, presentation-ready persona. Only a short, human provenance
  // line survives here, and only when the pipeline actually attached real
  // evidence to this persona - never invented.
  cursorY += 4;
  if (sections.provenanceText) {
    items.push({ type: "provenance", text: sections.provenanceText, y: cursorY, fontSize: 13 });
    cursorY += 13 * 1.4;
  }

  return { items, totalHeight: cursorY + PERSONA_BOTTOM_PADDING };
}

function drawLayout(ctx, layout) {
  const x0 = PERSONA_CONTENT_X;
  layout.items.forEach((item) => {
    if (item.type === "lead") {
      if (item.isQuote) {
        ctx.font = `700 ${Math.round(item.fontSize * 1.6)}px Georgia, serif`;
        ctx.fillStyle = PERSONA_ACCENT;
        ctx.fillText("“", x0 - 6, item.y + item.fontSize * 0.9);
      }
      ctx.font = `700 ${item.fontSize}px ${PERSONA_FONT_FAMILY}`;
      ctx.fillStyle = PERSONA_INK;
      item.lines.forEach((line, i) =>
        ctx.fillText(line, x0 + item.x, item.y + (i + 1) * item.fontSize * 1.25 - item.fontSize * 0.25));
      if (item.tag) {
        const leadHeight = item.lines.length * item.fontSize * 1.25;
        ctx.font = `600 13px ${PERSONA_FONT_FAMILY}`;
        ctx.fillStyle = PERSONA_MUTED;
        ctx.fillText(item.tag.toUpperCase(), x0, item.y + leadHeight + 16);
      }
    } else if (item.type === "divider") {
      ctx.strokeStyle = PERSONA_LINE;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, item.y);
      ctx.lineTo(x0 + PERSONA_CONTENT_WIDTH, item.y);
      ctx.stroke();
    } else if (item.type === "heading") {
      ctx.font = `700 ${item.fontSize}px ${PERSONA_FONT_FAMILY}`;
      ctx.fillStyle = PERSONA_INK;
      ctx.fillText(item.text, x0, item.y + item.fontSize);
    } else if (item.type === "paragraph") {
      ctx.font = `400 ${item.fontSize}px ${PERSONA_FONT_FAMILY}`;
      ctx.fillStyle = PERSONA_INK;
      item.lines.forEach((line, i) =>
        ctx.fillText(line, x0, item.y + (i + 1) * item.fontSize * item.lineHeight - item.fontSize * 0.3));
    } else if (item.type === "grid-row") {
      item.cats.forEach((cat, colIndex) => {
        const cx = x0 + colIndex * (item.colWidth + item.colGap);
        ctx.font = `700 ${item.headingFontSize}px ${PERSONA_FONT_FAMILY}`;
        ctx.fillStyle = PERSONA_INK;
        ctx.fillText(cat.label, cx, item.y + item.headingFontSize);

        let cy = item.y + item.headingHeight + 10;
        ctx.font = `400 ${item.fontSize}px ${PERSONA_FONT_FAMILY}`;
        cat.items.forEach((bullet) => {
          const lines = wrapLines(ctx, `•  ${bullet}`, item.colWidth);
          lines.forEach((line, li) =>
            ctx.fillText(line, cx, cy + (li + 1) * item.fontSize * item.lineHeight - item.fontSize * 0.3));
          cy += lines.length * item.fontSize * item.lineHeight + item.itemGap;
        });
      });
    } else if (item.type === "provenance") {
      ctx.font = `400 ${item.fontSize}px ${PERSONA_FONT_FAMILY}`;
      ctx.fillStyle = PERSONA_MUTED;
      ctx.fillText(item.text, x0, item.y + item.fontSize);
    }
  });
}

function drawLeftColumn(ctx, persona, canvasHeight) {
  ctx.fillStyle = PERSONA_PHOTO_BG;
  ctx.fillRect(0, 0, PERSONA_LEFT_WIDTH, PERSONA_PHOTO_HEIGHT);

  // No real participant photograph exists for a behavioural archetype - a
  // neutral, abstract placeholder (initials on a flat tint) fills the box
  // instead of a fabricated realistic face.
  ctx.fillStyle = "#8a8a8a";
  ctx.font = `700 96px ${PERSONA_FONT_FAMILY}`;
  ctx.textAlign = "center";
  ctx.fillText(personaInitialsFor(persona.name), PERSONA_LEFT_WIDTH / 2, PERSONA_PHOTO_HEIGHT / 2 + 34);
  ctx.textAlign = "left";

  ctx.fillStyle = PERSONA_PANEL_BG;
  ctx.fillRect(0, PERSONA_PHOTO_HEIGHT, PERSONA_LEFT_WIDTH, canvasHeight - PERSONA_PHOTO_HEIGHT);

  const panelInnerWidth = PERSONA_LEFT_WIDTH - PERSONA_PANEL_PAD_X * 2;
  let panelY = PERSONA_PHOTO_HEIGHT + 70;

  ctx.fillStyle = "#ffffff";
  ctx.font = `700 34px ${PERSONA_FONT_FAMILY}`;
  const nameLines = wrapLines(ctx, persona.name || "Unnamed persona", panelInnerWidth);
  nameLines.forEach((line, i) => ctx.fillText(line, PERSONA_PANEL_PAD_X, panelY + i * 40));
  panelY += nameLines.length * 40 + 14;

  const archetype = (persona.archetype || "").trim();
  if (archetype) {
    ctx.fillStyle = "#cfcfcf";
    ctx.font = `600 20px ${PERSONA_FONT_FAMILY}`;
    const roleLines = wrapLines(ctx, archetype, panelInnerWidth);
    roleLines.forEach((line, i) => ctx.fillText(line, PERSONA_PANEL_PAD_X, panelY + i * 26));
    panelY += roleLines.length * 26 + 18;
  }

  const participants = persona.participant_coverage || [];
  if (participants.length) {
    ctx.fillStyle = "#8a8a8a";
    ctx.font = `500 15px ${PERSONA_FONT_FAMILY}`;
    ctx.fillText(`Participants: ${participants.join(" · ")}`, PERSONA_PANEL_PAD_X, panelY);
  }
}

/** Renders `persona` onto `canvas` at the canonical 1600x880 design, using
 * the one design for every persona. Returns the same canvas so callers can
 * chain straight into toBlob()/toDataURL() for the PNG download.
 *
 * Width is always exactly 1600px, matching the fixed canonical canvas size.
 * Height is 880px for the overwhelming majority of personas (typical
 * evidence-backed content comfortably fits within the size-tier system
 * below); it only grows taller, as a last-resort safety net, for the rare
 * persona whose complete content doesn't fit even at the smallest still-
 * legible tier - guaranteeing content is never invisibly clipped off the
 * bottom of the canvas, which "no truncation, no clipping" would otherwise
 * be unable to promise for a truly hard-fixed height. */
function renderPersonaToCanvas(persona, canvas) {
  canvas.width = PERSONA_CANVAS_WIDTH;
  canvas.height = PERSONA_CANVAS_HEIGHT;
  const ctx = canvas.getContext("2d");
  ctx.textBaseline = "alphabetic";

  const sections = buildPersonaSections(persona);
  let layout = null;
  for (const tier of SIZE_TIERS) {
    const candidate = computeLayout(ctx, sections, tier);
    if (candidate.totalHeight <= PERSONA_CANVAS_HEIGHT) { layout = candidate; break; }
  }
  if (!layout) {
    layout = computeLayout(ctx, sections, SIZE_TIERS[SIZE_TIERS.length - 1]);
  }

  const canvasHeight = Math.max(PERSONA_CANVAS_HEIGHT, Math.ceil(layout.totalHeight));
  if (canvasHeight !== canvas.height) {
    canvas.height = canvasHeight; // resizing clears the canvas - nothing has been drawn yet
  }

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, PERSONA_CANVAS_WIDTH, canvasHeight);
  ctx.fillStyle = PERSONA_RIGHT_BG;
  ctx.fillRect(PERSONA_LEFT_WIDTH, 0, PERSONA_RIGHT_WIDTH, canvasHeight);

  drawLeftColumn(ctx, persona, canvasHeight);
  drawLayout(ctx, layout);

  return canvas;
}

function sanitizePersonaFilename(name) {
  const slug = (name || "persona")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "") || "persona";
  return `researchmate-persona-${slug}.png`;
}
