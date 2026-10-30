// Builds the-useful-hour.pptx from outputs/deck_numbers.json, which the notebook writes.
// Every figure on a slide comes from that file, so the deck cannot drift from the analysis.
//
//   NODE_PATH=<dir with pptxgenjs>/node_modules node build_deck.js
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");

const N = JSON.parse(fs.readFileSync(path.join(__dirname, "outputs", "deck_numbers.json"), "utf8"));
const OUT = path.join(__dirname, "the-useful-hour.pptx");

const THEME = {
  name: "Useful Hour",
  headFontFace: "Arial",
  bodyFontFace: "Arial",
  colors: {
    dk1: "0B0B0B", lt1: "FFFFFF", dk2: "0D3B2C", lt2: "F4F4F2",
    accent1: "00863A", accent2: "35C46F", accent3: "EB6834", accent4: "6F6E6A",
    accent5: "8A8A84", accent6: "C3D2C7", hlink: "00863A", folHlink: "0D3B2C",
  },
};
// Platform colours, hex because chart colours are hex-only. Same as the notebook's charts.
const PC = { mainframe: "0D3B2C", distributed: "8A8A84", cloud: "35C46F" };
const HEX = THEME.colors;

// ── number formatting ─────────────────────────────────────────────────────────
const m = (v, d = 2) => `£${(v / 1e6).toFixed(d)}M`;
const k = (v) => `£${Math.round(v / 1e3).toLocaleString("en-GB")}k`;
const pct = (v, d = 0) => `${(v * 100).toFixed(d)}%`;
const x1 = (v) => `${v.toFixed(1)}×`;
const P = N.platform;

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 × 5.625 in
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "The Useful Hour — Challenge 03, Beyond the Mainframe";
pres.subject = "Innovation Forum × R1X hackathon entry";
const C = pres.SchemeColor || pptxgen.SchemeColor;

const FOOTER = "The Useful Hour · Challenge 03 · all figures from the synthetic challenge estate";

// ── layouts ───────────────────────────────────────────────────────────────────
pres.defineSlideMaster({
  title: "UH_TITLE",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 1.05, w: 8.8, h: 0.35, fontSize: 12, bold: true, color: C.accent2, charSpacing: 3, margin: 0, valign: "top" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.45, w: 8.8, h: 1.1, fontSize: 54, bold: true, color: C.background1, margin: 0, valign: "top", align: "left" }, text: "" } },
    { placeholder: { options: { name: "body", type: "body", x: 0.6, y: 2.6, w: 8.8, h: 0.6, fontSize: 22, color: C.accent6, margin: 0, valign: "top" }, text: "" } },
  ],
});
pres.defineSlideMaster({
  title: "UH_CONTENT",
  background: { color: C.background1 },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: 0.5, y: 0.3, w: 9, h: 0.28, fontSize: 11, bold: true, color: C.accent1, charSpacing: 2, margin: 0, valign: "top" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.5, y: 0.6, w: 9, h: 0.9, fontSize: 26, bold: true, color: C.text2, margin: 0, valign: "top", align: "left" }, text: "" } },
    { text: { text: FOOTER, options: { x: 0.5, y: 5.22, w: 8, h: 0.22, fontSize: 9, color: C.accent4, margin: 0 } } },
  ],
  slideNumber: { x: 9.1, y: 5.22, w: 0.4, h: 0.22, fontSize: 9, color: C.accent4, align: "right" },
});
pres.defineSlideMaster({
  title: "UH_STATEMENT",
  background: { color: C.text2 },
  objects: [
    { placeholder: { options: { name: "kicker", type: "body", x: 0.6, y: 1.0, w: 8.8, h: 0.3, fontSize: 12, bold: true, color: C.accent2, charSpacing: 3, margin: 0, valign: "top" }, text: "" } },
    { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 1.4, w: 8.8, h: 1.6, fontSize: 36, bold: true, color: C.background1, margin: 0, valign: "top", align: "left" }, text: "" } },
    { text: { text: FOOTER, options: { x: 0.6, y: 5.22, w: 8, h: 0.22, fontSize: 9, color: C.accent6, margin: 0 } } },
  ],
  slideNumber: { x: 9.0, y: 5.22, w: 0.4, h: 0.22, fontSize: 9, color: C.accent6, align: "right" },
});

// ── helpers ───────────────────────────────────────────────────────────────────
const text = (s, t, o) => s.addText(t, { isTextBox: true, margin: 0, valign: "top", color: C.text1, fontSize: 14, ...o });
const card = (s, x, y, w, h, name, fill = C.background2) =>
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: fill, width: 0 }, objectName: name });
// The motif: three platform chips, one per generation of the estate.
const chips = (s, x, y, size = 0.22, gap = 0.08, onDark = false) =>
  ["mainframe", "distributed", "cloud"].forEach((p, i) =>
    s.addShape(pres.shapes.RECTANGLE, { x: x + i * (size + gap), y, w: size, h: size, fill: { color: PC[p] },
      line: onDark && p === "mainframe" ? { color: HEX.accent6, width: 1.25 } : { color: PC[p], width: 0 }, objectName: `chip-${p}` }));
const chart = () => ({
  catAxisLabelColor: "52514E", valAxisLabelColor: "52514E",
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
  valGridLine: { color: "E3E3DF", size: 0.5 }, catGridLine: { style: "none" },
  dataLabelFontFace: "+mn-lt", dataLabelFontSize: 10, dataLabelColor: "0B0B0B",
  legendFontFace: "+mn-lt", legendFontSize: 10, legendColor: "52514E",
  titleFontFace: "+mn-lt", titleFontSize: 11, titleColor: "52514E",
  catAxisLineShow: true, valAxisLineShow: false,
});
let section = "";
const slide = (master, sec) => {
  if (sec !== section) { pres.addSection({ title: sec }); section = sec; }
  return pres.addSlide({ masterName: master, sectionTitle: sec });
};

// ── 1 · title ─────────────────────────────────────────────────────────────────
{
  const s = slide("UH_TITLE", "Opening");
  s.addText("CHALLENGE 03 · BEYOND THE MAINFRAME", { placeholder: "kicker" });
  s.addText("The Useful Hour", { placeholder: "title" });
  s.addText("One unit of cost for a three-generation estate", { placeholder: "body" });
  chips(s, 0.6, 3.55, 0.3, 0.1, true);
  text(s, "→  one comparable number", { x: 1.75, y: 3.55, w: 4, h: 0.3, fontSize: 14, color: C.accent6, valign: "middle" });
  text(s, "[Team name]  ·  Innovation Forum × R1X  ·  Hatfield, 30 October 2026", { x: 0.6, y: 4.55, w: 8.8, h: 0.3, fontSize: 13, color: C.background1 });
  s.addNotes(
    "Hi, we're [team name]. Challenge 03 asked: how can an organisation see what its computing actually costs, " +
    "when the estate spans mainframe, distributed and cloud — three generations that each count cost their own way? " +
    "Our answer is a single unit we call the useful hour. Everything you'll see comes from the challenge's synthetic estate, " +
    "and every number is reproducible from our notebook.");
}

// ── 2 · problem ───────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "The problem");
  s.addText("THE PROBLEM", { placeholder: "kicker" });
  s.addText("Three generations of systems, three ways of counting — and no common unit", { placeholder: "title" });
  const cols = [
    ["mainframe", "Mainframe", "MIPS-equivalent hours"],
    ["distributed", "Distributed", "virtual-machine hours"],
    ["cloud", "Cloud", "instance hours"],
  ];
  const w = 2.8, gap = 0.3, y = 1.7, h = 2.45;
  cols.forEach(([p, label, unit], i) => {
    const x = 0.5 + i * (w + gap);
    card(s, x, y, w, h, `card-${p}`);
    s.addShape(pres.shapes.RECTANGLE, { x: x + 0.25, y: y + 0.28, w: 0.22, h: 0.22, fill: { color: PC[p] }, line: { color: PC[p], width: 0 }, objectName: `chip-${p}` });
    text(s, label, { x: x + 0.6, y: y + 0.22, w: w - 0.8, h: 0.34, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
    text(s, pct(P[p].share), { x: x + 0.25, y: y + 0.7, w: w - 0.5, h: 0.75, fontSize: 44, bold: true, color: C.text2 });
    text(s, `of spend · ${m(P[p].spend_gbp, 1)} a year`, { x: x + 0.25, y: y + 1.45, w: w - 0.5, h: 0.3, fontSize: 13, color: C.accent4 });
    text(s, [{ text: "Counts in ", options: { color: C.accent4 } }, { text: unit, options: { bold: true, color: C.text1 } }],
      { x: x + 0.25, y: y + 1.85, w: w - 0.5, h: 0.4, fontSize: 13 });
  });
  text(s, [
    { text: `${m(N.total_spend_gbp, 1)} a year across ${N.workloads.toLocaleString("en-GB")} workloads — `, options: { bold: true, color: C.text2 } },
    { text: "but no single number that adds up across all three, so every migration debate starts from the bill rather than the work." },
  ], { x: 0.5, y: 4.4, w: 9, h: 0.6, fontSize: 14, color: C.accent4 });
  s.addNotes(
    `The estate costs ${m(N.total_spend_gbp, 1)} a year. ${pct(P.mainframe.share)} of it is mainframe. ` +
    "But the mainframe reports MIPS-equivalent hours, the data centre reports VM hours, and the cloud reports instance hours. " +
    "There is no unit you can add up across all three — so the conversation defaults to 'the mainframe is the expensive bit, move it'.");
}

// ── 3 · the idea ──────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Our idea");
  s.addText("OUR IDEA", { placeholder: "kicker" });
  s.addText("Divide cost by the work actually done, not the hours billed", { placeholder: "title" });
  const y = 1.75, h = 1.0;
  const box = (x, w, top, bottom, fill, fg) => {
    card(s, x, y, w, h, `formula-${top}`, fill);
    text(s, top, { x: x + 0.15, y: y + 0.18, w: w - 0.3, h: 0.36, fontSize: 16, bold: true, color: fg, align: "center" });
    text(s, bottom, { x: x + 0.15, y: y + 0.58, w: w - 0.3, h: 0.3, fontSize: 11, color: fg, align: "center" });
  };
  box(0.5, 1.75, "Cost", "£ billed", C.background2, C.text2);
  text(s, "÷", { x: 2.3, y: y + 0.2, w: 0.5, h: 0.6, fontSize: 30, bold: true, color: C.accent1, align: "center" });
  box(2.85, 3.45, "vCPU-hours × utilisation", "work actually done", C.background2, C.text2);
  text(s, "=", { x: 6.33, y: y + 0.2, w: 0.5, h: 0.6, fontSize: 30, bold: true, color: C.accent1, align: "center" });
  box(6.85, 2.65, "£ per useful hour", "one unit, every platform", C.text2, C.background1);
  const pts = [
    ["Already in the lake", "Three columns the data lake holds today: cost, vCPU-hours, utilisation. No new data feed."],
    ["Works everywhere", "An idle hour is billed like a busy one, on every platform. Counting only busy hours puts them on one scale."],
    ["Anyone can check it", "One division. IT, finance and the board can all recompute it — and argue about the inputs, not the method."],
  ];
  pts.forEach(([h1, b], i) => {
    const x = 0.5 + i * 3.1;
    s.addShape(pres.shapes.OVAL, { x, y: 3.2, w: 0.36, h: 0.36, fill: { color: C.accent2 }, line: { color: C.accent2, width: 0 }, objectName: `num-${i + 1}` });
    text(s, String(i + 1), { x, y: 3.2, w: 0.36, h: 0.36, fontSize: 13, bold: true, color: C.text2, align: "center", valign: "middle" });
    text(s, h1, { x: x + 0.5, y: 3.2, w: 2.35, h: 0.36, fontSize: 14, bold: true, color: C.text2, valign: "middle" });
    text(s, b, { x, y: 3.7, w: 2.85, h: 1.3, fontSize: 12, color: C.accent4 });
  });
  s.addNotes(
    "Our idea is deliberately simple. In this estate you pay for a vCPU-hour whether the machine is busy or idle. " +
    "So multiply billed hours by utilisation to get the hours that did real work, and divide cost by that. " +
    "A cloud VM billed for ten hours at twenty percent busy did two useful hours. It needs nothing the data lake doesn't already hold.");
}

// ── 4 · finding 1 ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Findings");
  s.addText("FINDING 1 · THE PRICE GAP", { placeholder: "kicker" });
  s.addText(`Per billed hour the mainframe costs ${x1(N.gap_billed)} cloud. Per useful hour, ${x1(N.gap_useful)}`, { placeholder: "title" });
  const labels = ["Mainframe", "Distributed", "Cloud"];
  const keys = ["mainframe", "distributed", "cloud"];
  s.addChart(pres.charts.BAR, [
    { name: "£ per billed vCPU-hour", labels, values: keys.map((p) => +P[p].gbp_per_billed.toFixed(3)) },
    { name: "£ per useful vCPU-hour", labels, values: keys.map((p) => +P[p].gbp_per_useful.toFixed(3)) },
  ], {
    ...chart(), x: 0.4, y: 1.55, w: 5.6, h: 3.55, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
    chartColors: ["8A8A84", HEX.accent1], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '"£"0.00',
    valAxisLabelFormatCode: '"£"0.00', valAxisMinVal: 0, valAxisMaxVal: 0.8, valAxisMajorUnit: 0.2,
    showLegend: true, legendPos: "t", showTitle: false, objectName: "chart-unit-cost",
  });
  card(s, 6.3, 1.6, 3.2, 1.25, "stat-gap");
  text(s, `${x1(N.gap_billed)} → ${x1(N.gap_useful)}`, { x: 6.5, y: 1.72, w: 2.9, h: 0.6, fontSize: 32, bold: true, color: C.accent1 });
  text(s, "mainframe vs cloud, once only the work done is counted", { x: 6.5, y: 2.32, w: 2.9, h: 0.45, fontSize: 11, color: C.accent4 });
  text(s, [
    { text: `Cloud runs at ${pct(P.cloud.utilisation)} utilisation`, options: { bold: true, color: C.text2, breakLine: true } },
    { text: "— it pays for almost four idle hours for every busy one.", options: { color: C.accent4 } },
  ], { x: 6.3, y: 3.05, w: 3.2, h: 0.85, fontSize: 13 });
  text(s, [
    { text: "Distributed is the cheapest place to do a unit of work", options: { bold: true, color: C.text2, breakLine: true } },
    { text: `£${P.distributed.gbp_per_useful.toFixed(2)} per useful hour, below cloud's £${P.cloud.gbp_per_useful.toFixed(2)}.`, options: { color: C.accent4 } },
  ], { x: 6.3, y: 4.0, w: 3.2, h: 0.95, fontSize: 13 });
  s.addNotes(
    `On the bill, a mainframe vCPU-hour costs ${x1(N.gap_billed)} a cloud one — that's the number behind every 'leave the mainframe' slide. ` +
    `But the mainframe runs at ${pct(P.mainframe.utilisation)} utilisation and the cloud at ${pct(P.cloud.utilisation)}. ` +
    `Count only useful hours and the gap closes to ${x1(N.gap_useful)}. And the cheapest place to do a unit of work is actually the distributed estate, not the cloud. ` +
    "Most of the famous price gap is a statement about cloud utilisation, not about the mainframe.");
}

// ── 5 · finding 2 ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Findings");
  s.addText("FINDING 2 · THE MIGRATION CASE", { placeholder: "kicker" });
  s.addText(`The ${pct(N.naive_saving)} migration saving is really ${pct(N.aware_saving)} — and it can become a loss`, { placeholder: "title" });
  const curve = N.exchange_curve;
  const labels = curve.today.map(([r]) => r.toFixed(1));
  s.addChart(pres.charts.LINE, [
    { name: `Cloud at today's ${pct(P.cloud.utilisation)}`, labels, values: curve.today.map(([, v]) => +v.toFixed(3)) },
    { name: "Cloud at 40%", labels, values: curve["40%"].map(([, v]) => +v.toFixed(3)) },
    { name: "Cloud at 60%", labels, values: curve["60%"].map(([, v]) => +v.toFixed(3)) },
  ], {
    ...chart(), x: 0.4, y: 1.55, w: 5.8, h: 3.55, chartColors: [HEX.accent3, HEX.dk2, "8A8A84"], lineSize: 2.5, lineDataSymbol: "none",
    valAxisLabelFormatCode: "0%", valAxisMinVal: -1, valAxisMaxVal: 1, valAxisMajorUnit: 0.5, catAxisLabelPos: "low",
    showCatAxisTitle: true, catAxisTitle: "Cloud vCPU-hours needed per mainframe hour of work", catAxisTitleFontSize: 10, catAxisTitleColor: "52514E",
    showValAxisTitle: true, valAxisTitle: "Saving vs staying", valAxisTitleFontSize: 10, valAxisTitleColor: "52514E",
    showLegend: true, legendPos: "t", showTitle: false, objectName: "chart-exchange-rate",
  });
  card(s, 6.5, 1.6, 3.0, 1.35, "stat-breakeven");
  text(s, `${N.breakeven_cloud.toFixed(1)} : 1`, { x: 6.7, y: 1.72, w: 2.6, h: 0.6, fontSize: 32, bold: true, color: C.accent3 });
  text(s, "break-even exchange rate at today's cloud utilisation", { x: 6.7, y: 2.32, w: 2.6, h: 0.5, fontSize: 11, color: C.accent4 });
  text(s, [
    { text: "Nobody has measured that ratio.", options: { bold: true, color: C.text2, breakLine: true } },
    { text: `If one mainframe hour needs more than ${N.breakeven_cloud.toFixed(1)} cloud vCPU-hours to replace, migration costs money.`, options: { color: C.accent4 } },
  ], { x: 6.5, y: 3.1, w: 3.0, h: 1.1, fontSize: 13 });
  text(s, "Upper bound: excludes migration cost, dual running and risk.", { x: 6.5, y: 4.4, w: 3.0, h: 0.5, fontSize: 11, italic: true, color: C.accent4 });
  s.addNotes(
    `Compare unit prices and moving the whole mainframe to cloud saves ${pct(N.naive_saving)}. ` +
    `Do the same useful work at the cloud estate's real utilisation and it's ${pct(N.aware_saving)} — before any migration cost. ` +
    `And it hinges on an exchange rate nobody measures: how many cloud vCPU-hours replace one mainframe hour. ` +
    `Above ${N.breakeven_cloud.toFixed(1)} to 1, the orange line goes negative and migration costs money. ` +
    "Raise cloud utilisation and the case improves. So the answer is decided by numbers you can fix or measure before anything moves.");
}

// ── 6 · reframe ───────────────────────────────────────────────────────────────
{
  const s = slide("UH_STATEMENT", "Findings");
  s.addText("SO", { placeholder: "kicker" });
  s.addText("“Should we leave the mainframe?” is the wrong first question", { placeholder: "title" });
  text(s, "Ask what a useful hour costs, wherever it runs — and who owns it.", { x: 0.6, y: 3.15, w: 8.8, h: 0.5, fontSize: 20, color: C.accent2 });
  chips(s, 0.6, 4.1, 0.3, 0.1, true);
  s.addNotes(
    "Which brings us to the reframe in the challenge title. Leaving the mainframe is the wrong first question. " +
    "The right one is what a useful hour costs wherever it runs, and who owns it. The next two findings act on that without moving anything.");
}

// ── 7 · finding 3 ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Findings");
  s.addText("FINDING 3 · NO-REGRET SAVINGS", { placeholder: "kicker" });
  s.addText(`${m(N.save_now_gbp, 1)} a year is available without moving a single workload`, { placeholder: "title" });
  card(s, 0.5, 1.6, 3.0, 2.1, "stat-save-now");
  text(s, m(N.save_now_gbp, 2), { x: 0.7, y: 1.75, w: 2.6, h: 0.75, fontSize: 40, bold: true, color: C.accent1 });
  text(s, `a year — ${pct(N.save_now_gbp / N.payg_spend_gbp)} of cloud and distributed spend, banked as soon as it's done`, { x: 0.7, y: 2.55, w: 2.6, h: 1.0, fontSize: 12, color: C.accent4 });
  const lv = N.levers;
  const lab = ["Right-size to 60% utilisation", "Decommission: idle all year", "Weekend off: dev and test"];
  const val = [lv["Right-size to 60%"], lv["Idle (cloud + distributed)"], lv["Weekend off, non-prod"]];
  s.addChart(pres.charts.BAR, [{ name: "Annual saving", labels: lab, values: val.map((v) => Math.round(v)) }], {
    ...chart(), x: 3.75, y: 1.5, w: 5.8, h: 2.3, barDir: "bar", catAxisOrientation: "maxMin", barGapWidthPct: 45,
    chartColors: [HEX.accent3], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: '"£"#,##0,"k"',
    valAxisHidden: true, valGridLine: { style: "none" }, valAxisMaxVal: 1100000, showLegend: false, showTitle: false, objectName: "chart-levers",
  });
  card(s, 0.5, 3.95, 9.0, 1.05, "note-mainframe");
  text(s, [
    { text: `+ ${m(N.mf_reclaim_gbp, 2)} of mainframe capacity sits idle in ${N.mf_idle_workloads} workloads. `, options: { bold: true, color: C.text2 } },
    { text: "Real, but banking it needs a capacity or contract change, so we don't count it above. Every lever lands in a ranked savings queue — a workload, an owner and a value per action.", options: { color: C.accent4 } },
  ], { x: 0.7, y: 4.07, w: 8.6, h: 0.85, fontSize: 12.5 });
  s.addNotes(
    `Three levers on the pay-as-you-go platforms, applied in sequence so nothing is double-counted: right-size to sixty percent utilisation, ` +
    `decommission what's been idle all year, and switch dev and test off at weekends. Together ${m(N.save_now_gbp, 2)} a year. ` +
    `On the mainframe there's another ${m(N.mf_reclaim_gbp, 2)} sitting idle, but turning that into cash needs a contract change, so we report it separately rather than claim it. ` +
    "The notebook exports all of this as a savings queue — each action has a workload, an owner and a value.");
}

// ── 8 · finding 4 ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Findings");
  s.addText("FINDING 4 · OWNERSHIP", { placeholder: "kicker" });
  s.addText("The biggest ‘business unit’ in the estate is nobody", { placeholder: "title" });
  const top = N.top_bus;
  const labels = top.map(([b]) => (b === "UNALLOCATED" ? "No owner" : b));
  s.addChart(pres.charts.BAR, [
    { name: "No owner", labels, values: top.map(([b, v]) => (b === "UNALLOCATED" ? Math.round(v) : 0)) },
    { name: "Owned", labels, values: top.map(([b, v]) => (b === "UNALLOCATED" ? 0 : Math.round(v))) },
  ], {
    ...chart(), x: 0.4, y: 1.5, w: 5.2, h: 3.6, barDir: "bar", barGrouping: "stacked", catAxisOrientation: "maxMin", barGapWidthPct: 40,
    chartColors: [HEX.accent3, HEX.dk2], showValue: false, valAxisLabelFormatCode: '"£"0.0,,"M"', valAxisMinVal: 0, valAxisMaxVal: 1200000,
    valAxisMajorUnit: 400000, showLegend: false, showTitle: false, objectName: "chart-owners",
  });
  text(s, [
    { text: `${m(N.unallocated_gbp, 2)} · ${pct(N.unallocated_share, 1)} of spend`, options: { bold: true, color: C.accent3, fontSize: 20, breakLine: true } },
    { text: `${N.unallocated_workloads} workloads with no owner — more than any real business unit spends.`, options: { color: C.accent4, fontSize: 12 } },
  ], { x: 5.9, y: 1.6, w: 3.6, h: 0.95 });
  card(s, 5.9, 2.7, 3.6, 1.45, "ruled-out");
  text(s, [
    { text: "What we ruled out", options: { bold: true, color: C.text2, fontSize: 13, breakLine: true } },
    { text: `A model guessing the owner from service, platform, region, size and utilisation: ${pct(N.owner_model_acc, 1)} accurate vs ${pct(N.owner_chance, 1)} by pure chance. Ownership leaves no technical fingerprint.`, options: { color: C.accent4, fontSize: 11.5 } },
  ], { x: 6.05, y: 2.82, w: 3.3, h: 1.25 });
  text(s, [
    { text: "The fix is process, not a model: ", options: { bold: true, color: C.text2 } },
    { text: "no tag, no deploy — and until then the unallocated line goes on the platform owner's bill.", options: { color: C.accent4 } },
  ], { x: 5.9, y: 4.3, w: 3.6, h: 0.75, fontSize: 12 });
  s.addNotes(
    `Chargeback only changes behaviour if someone gets the bill. ${m(N.unallocated_gbp, 2)}, ${pct(N.unallocated_share, 1)} of spend, has no owner — ` +
    "more than any real business unit. We tried the tempting fix: train a model to guess the owner. " +
    `It scored ${pct(N.owner_model_acc, 1)}, against ${pct(N.owner_chance, 1)} for pure chance. We'd rather tell you that than ship it. ` +
    "So the fix is process: no tag, no deploy, and in the meantime the unallocated line lands on the platform owner's bill.");
}

// ── 9 · finding 5 ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Findings");
  s.addText("FINDING 5 · CARBON", { placeholder: "kicker" });
  s.addText("The same unit turns the carbon ranking the other way round", { placeholder: "title" });
  const labels = ["Mainframe", "Distributed", "Cloud"];
  const keys = ["mainframe", "distributed", "cloud"];
  s.addChart(pres.charts.BAR, [
    { name: "Wh per billed vCPU-hour", labels, values: keys.map((p) => +P[p].wh_per_billed.toFixed(1)) },
    { name: "Wh per useful vCPU-hour", labels, values: keys.map((p) => +P[p].wh_per_useful.toFixed(1)) },
  ], {
    ...chart(), x: 0.4, y: 1.55, w: 5.6, h: 3.55, barDir: "col", barGrouping: "clustered", barGapWidthPct: 60,
    chartColors: ["8A8A84", HEX.accent1], showValue: true, dataLabelPosition: "outEnd", dataLabelFormatCode: "0.0",
    valAxisLabelFormatCode: "0", valAxisMinVal: 0, valAxisMaxVal: 40, valAxisMajorUnit: 10,
    showLegend: true, legendPos: "t", showTitle: false, objectName: "chart-carbon",
  });
  text(s, [
    { text: "Per billed hour, cloud uses least energy.", options: { bold: true, color: C.text2, breakLine: true } },
    { text: `Per useful hour, the busy mainframe does: ${P.mainframe.wh_per_useful.toFixed(1)} Wh against ${P.cloud.wh_per_useful.toFixed(1)} for cloud.`, options: { color: C.accent4 } },
  ], { x: 6.3, y: 1.6, w: 3.2, h: 1.15, fontSize: 13 });
  text(s, [
    { text: `${N.idle_carbon_t.toFixed(1)} tCO₂e — ${pct(N.idle_carbon_share, 1)} of the estate`, options: { bold: true, color: C.text2, breakLine: true } },
    { text: "comes from workloads idle all year: emitted for no work at all.", options: { color: C.accent4 } },
  ], { x: 6.3, y: 2.9, w: 3.2, h: 0.95, fontSize: 13 });
  card(s, 6.3, 4.0, 3.2, 1.0, "caveat-carbon");
  text(s, "Grid intensity in the challenge data is synthetic. This shows the method, not a measurement of any real grid or platform.",
    { x: 6.45, y: 4.1, w: 2.9, h: 0.8, fontSize: 11, italic: true, color: C.accent4 });
  s.addNotes(
    "The same unit works as a fourth dimension. Per billed hour the cloud looks greenest. Per useful hour, the busy mainframe does a unit of work for the least energy. " +
    `And ${N.idle_carbon_t.toFixed(1)} tonnes come from workloads that did nothing all year. ` +
    "Important caveat: the challenge's grid intensity is synthetic, so this demonstrates the method — we are not claiming a real-world carbon finding.");
}

// ── 10 · product ──────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "What we'd build");
  s.addText("WHAT WE'D BUILD", { placeholder: "kicker" });
  s.addText("Estate Lens: four views added to the sponsor's platform", { placeholder: "title" });
  const items = [
    ["Useful-hour unit", "One comparable £ for mainframe, distributed and cloud, beside every existing capacity view.", "For IT and capacity teams"],
    ["Exchange-rate test", "Shows what must be true before a migration pays — and which number to measure first.", "For the architecture board"],
    ["Savings queue", "Every lever as a ranked action: workload, owner, value. Feeds the ticketing tool.", "For engineering"],
    ["Owner scorecard", "Spend, utilisation, savings and carbon per business unit, published with chargeback.", "For finance and the board"],
  ];
  const w = 4.35, h = 1.6, gx = 0.3, gy = 0.25;
  items.forEach(([h1, b, who], i) => {
    const x = 0.5 + (i % 2) * (w + gx), y = 1.6 + Math.floor(i / 2) * (h + gy);
    card(s, x, y, w, h, `module-${i + 1}`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.22, y: y + 0.22, w: 0.4, h: 0.4, fill: { color: C.text2 }, line: { color: C.text2, width: 0 }, objectName: `module-num-${i + 1}` });
    text(s, String(i + 1), { x: x + 0.22, y: y + 0.22, w: 0.4, h: 0.4, fontSize: 14, bold: true, color: C.background1, align: "center", valign: "middle" });
    text(s, h1, { x: x + 0.78, y: y + 0.22, w: w - 1.0, h: 0.4, fontSize: 16, bold: true, color: C.text2, valign: "middle" });
    text(s, b, { x: x + 0.22, y: y + 0.75, w: w - 0.44, h: 0.5, fontSize: 12, color: C.text1 });
    text(s, who, { x: x + 0.22, y: y + 1.25, w: w - 0.44, h: 0.25, fontSize: 11, bold: true, color: C.accent1 });
  });
  s.addNotes(
    "As a product, this extends the sponsor's existing platform rather than replacing it. Four views: the useful-hour unit for capacity teams; " +
    "the exchange-rate test for the architecture board; the savings queue for engineering; and an owner scorecard for finance and the board. " +
    "All four already run end to end in our notebook on the challenge data.");
}

// ── 11 · criteria ─────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "What we'd build");
  s.addText("AGAINST THE FIVE CRITERIA", { placeholder: "kicker" });
  s.addText("Why this moves the sponsor toward leadership", { placeholder: "title" });
  const rows = [
    ["Market impact", "Mainframe expertise becomes the reference unit for the whole estate — the 'legacy niche' sets the standard."],
    ["Feasibility", `Three columns the lake already holds; the notebook runs on all ${N.rows.toLocaleString("en-GB")} rows in seconds. Honest TRL: 3.`],
    ["Clarity", "One number, one sentence: what does a useful hour cost? Readable by IT, finance and the boardroom."],
    ["Integration", `Cost and carbon joined one-to-one on workload × day; chargeback reconciles to source within £${N.recon_diff_gbp.toFixed(2)}.`],
    ["Innovation", "The exchange-rate test turns a migration belief into two numbers you can measure."],
  ];
  rows.forEach(([c, d], i) => {
    const y = 1.55 + i * 0.7;
    s.addShape(pres.shapes.OVAL, { x: 0.5, y: y + 0.08, w: 0.4, h: 0.4, fill: { color: C.accent2 }, line: { color: C.accent2, width: 0 }, objectName: `crit-${i + 1}` });
    text(s, String(i + 1), { x: 0.5, y: y + 0.08, w: 0.4, h: 0.4, fontSize: 14, bold: true, color: C.text2, align: "center", valign: "middle" });
    text(s, c, { x: 1.1, y, w: 2.1, h: 0.56, fontSize: 15, bold: true, color: C.text2, valign: "middle" });
    text(s, d, { x: 3.2, y, w: 6.3, h: 0.56, fontSize: 12.5, color: C.text1, valign: "middle" });
  });
  s.addNotes(
    "Against the five published criteria. Market impact: the sponsor's mainframe expertise becomes the reference unit for the whole estate. " +
    "Feasibility: three columns already in the lake, and we're honest that this is a TRL 3 proof of concept. Clarity: one number, one sentence. " +
    "Integration: cost and carbon join one-to-one and chargeback reconciles to the penny. Innovation: the exchange-rate test.");
}

// ── 12 · limits ───────────────────────────────────────────────────────────────
{
  const s = slide("UH_CONTENT", "Limits and next steps");
  s.addText("LIMITS AND NEXT STEPS", { placeholder: "kicker" });
  s.addText("Where it breaks first, and what we'd do next", { placeholder: "title" });
  const col = (x, head, items, fill, fg, sub) => {
    card(s, x, 1.6, 4.35, 3.4, `col-${head}`, fill);
    text(s, head, { x: x + 0.25, y: 1.78, w: 3.9, h: 0.35, fontSize: 15, bold: true, color: fg });
    text(s, items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1, paraSpaceAfter: 6 } })),
      { x: x + 0.25, y: 2.25, w: 3.9, h: 2.6, fontSize: 12, color: sub });
  };
  col(0.5, "Where it breaks first", [
    "Utilisation means different things per platform — a shared mainframe partition is not a cloud VM. Needs an agreed definition each.",
    "The exchange rate is unmeasured. We show what it must be; a real estate must benchmark it.",
    "Cost here is linear. Real mainframe software is often priced on peak, so month-end batch (up to ~4× a normal day) would matter more.",
    "Right-sizing is an upper bound: storage doesn't shrink with vCPUs.",
  ], C.background2, C.text2, C.text1);
  col(5.15, "What we'd do next", [
    "Benchmark five representative workloads to pin down the exchange rate.",
    "Add the useful-hour unit to the sponsor's viewer, next to existing capacity views.",
    "Feed the savings queue into the ticketing tool, one ticket per owner.",
    "Publish the owner scorecard every month alongside chargeback.",
  ], C.text2, C.accent2, C.background1);
  s.addNotes(
    "Where it breaks first: utilisation is measured differently on each platform, so a production version needs an agreed definition per platform — that's the biggest risk. " +
    "The exchange rate is unmeasured. And this data prices compute linearly, whereas real mainframe software is often priced on peak, so the month-end batch peaks would matter more. " +
    "Next: benchmark five workloads, add the unit to the viewer, feed the queue into ticketing, and publish the scorecard monthly.");
}

// ── 13 · close ────────────────────────────────────────────────────────────────
{
  const s = slide("UH_STATEMENT", "Close");
  s.addText("THREE NUMBERS TO TAKE AWAY", { placeholder: "kicker" });
  const stats = [
    [x1(N.gap_useful), `what a useful mainframe hour costs against cloud — not the ${x1(N.gap_billed)} the bill suggests`],
    [m(N.save_now_gbp, 1), "a year available now, without moving a single workload"],
    [pct(N.unallocated_share, 1), "of spend has no owner — the largest ‘business unit’ in the estate"],
  ];
  stats.forEach(([big, lab], i) => {
    const x = 0.6 + i * 3.0;
    text(s, big, { x, y: 1.45, w: 2.7, h: 0.9, fontSize: 48, bold: true, color: C.accent2 });
    text(s, lab, { x, y: 2.4, w: 2.6, h: 1.0, fontSize: 13, color: C.background1 });
  });
  text(s, [{ text: "Don't ask whether to leave the mainframe.", options: { breakLine: true } }, { text: "Ask what a useful hour costs.", options: { color: C.accent2 } }],
    { x: 0.6, y: 3.5, w: 8.8, h: 0.75, fontSize: 20, bold: true, color: C.background1 });
  text(s, "Reproduce every number: the-useful-hour.ipynb · synthetic challenge estate (CC0) · no client data", { x: 0.6, y: 4.55, w: 8.8, h: 0.3, fontSize: 11, color: C.accent6 });
  s.addNotes(
    `Three numbers. ${x1(N.gap_useful)}, not ${x1(N.gap_billed)}. ${m(N.save_now_gbp, 1)} a year without moving anything. ` +
    `${pct(N.unallocated_share, 1)} of spend with no owner. Don't ask whether to leave the mainframe — ask what a useful hour costs. Thank you.`);
}

// pptxgenjs writes Office's stock palette into the theme, so scheme colours would render as
// Office blue and orange. Write ours in after saving. jszip ships with pptxgenjs.
async function applyTheme(file, theme) {
  const JSZip = require(require.resolve("jszip", { paths: [require.resolve("pptxgenjs")] }));
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const part = "ppt/theme/theme1.xml";
  const slots = ["dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5", "accent6", "hlink", "folHlink"];
  const scheme = `<a:clrScheme name="${theme.name}">` +
    slots.map((s) => `<a:${s}><a:srgbClr val="${theme.colors[s]}"/></a:${s}>`).join("") + "</a:clrScheme>";
  const xml = (await zip.file(part).async("string"))
    .replace(/<a:clrScheme\b[\s\S]*?<\/a:clrScheme>/, () => scheme)
    .replace(/(<a:(?:theme|fontScheme)\b[^>]*?\bname=")[^"]*"/g, (_, head) => `${head}${theme.name}"`);
  if (!xml.includes(scheme)) throw new Error("no colour scheme found in " + part);
  zip.file(part, xml);
  fs.writeFileSync(file, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
}

(async () => {
  await pres.writeFile({ fileName: OUT });
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
