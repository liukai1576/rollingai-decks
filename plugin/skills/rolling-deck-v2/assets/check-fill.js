/* ════════════════════════════════════════════════════════════════════════
   rolling-deck · check-fill.js
   ────────────────────────────────────────────────────────────────────────
   Browser-side checker that walks every non-cover slide, force-activates
   it, measures how much of the available vertical content area each one
   actually uses, and produces a report.

   Three ways to use:
   1. Load in devtools (paste in console), then call
        RollingDeckCheck.printReport()
      Prints a per-slide fill table and a summary.
   2. Append to your deck temporarily:
        <script src="assets/check-fill.js"></script>
        <script>RollingDeckCheck.printReport();</script>
      Refresh, open devtools → see the report.
   3. Driven from headless Chrome / CDP — use:
        RollingDeckCheck.fillReport()   // returns JSON, no console output

   Targets the rolling-deck `.slide` + `.slide-fit` convention.
   ═════════════════════════════════════════════════════════════════════ */
(function (global) {
  "use strict";

  // Design canvas: 1920×1080. .slide has padding 96 (top) / 110 (bot) so
  // the usable content area inside .slide-fit is 1080 - 96 - 110 = 874px.
  const SLIDE_PAD_TOP = 96;
  const SLIDE_PAD_BOT = 110;
  const SLIDE_H       = 1080;
  const FIT_H         = SLIDE_H - SLIDE_PAD_TOP - SLIDE_PAD_BOT;

  // Thresholds for the verdict column.
  const UNDERFILL_PCT = 80;   // < this = "缺" (sparse)
  const OVERFLOW_PCT  = 105;  // > this = "溢" (overflow into nav-bar safe area)

  const verdict = (pct) => {
    if (pct < UNDERFILL_PCT) return "缺";
    if (pct > OVERFLOW_PCT)  return "溢";
    return "OK";
  };

  // Measure one slide WITHOUT triggering any animation engine.
  // We:
  //   1. force-activate the slide
  //   2. measure its slide-fit's last-child bottom (unscaled offsetTop+H)
  //   3. compute fillPct relative to the 874px usable area
  // Padding-top of .slide adds 96 to offsetTop values, so we subtract it.
  const measureSlide = (sl) => {
    // Force active (preserve current active state to restore later)
    document.querySelectorAll(".slide").forEach(s => s.classList.remove("active"));
    sl.classList.add("active");

    const fit = sl.querySelector(".slide-fit");
    if (!fit) {
      return { key: sl.dataset.slideKey, note: "(no .slide-fit — cover or non-fit slide)" };
    }
    const lastChild = [...fit.children].at(-1);
    if (!lastChild) {
      return { key: sl.dataset.slideKey, note: "(no children)" };
    }
    const lastBotInSlide = lastChild.offsetTop + lastChild.offsetHeight;
    const lastBotInFit   = lastBotInSlide - SLIDE_PAD_TOP;
    const fillPct        = Math.round(lastBotInFit / FIT_H * 100);
    const childTags      = [...fit.children].map(c =>
      c.tagName.toLowerCase() + (c.classList[0] ? "." + c.classList[0] : ""));
    return {
      key: sl.dataset.slideKey,
      screenLabel: sl.dataset.screenLabel,
      fillPct,
      verdict: verdict(fillPct),
      contentBottomPx: lastBotInFit,
      availablePx: FIT_H,
      children: childTags,
    };
  };

  const fillReport = () => {
    const prevActive = document.querySelector(".slide.active");
    const slides = [...document.querySelectorAll(".slide:not(.cover-hero)")];
    const rows = slides.map(measureSlide);
    // Restore previous active state
    document.querySelectorAll(".slide").forEach(s => s.classList.remove("active"));
    if (prevActive) prevActive.classList.add("active");
    return rows;
  };

  const printReport = () => {
    const rows = fillReport();
    const measurable = rows.filter(r => typeof r.fillPct === "number");
    const summary = {
      total: rows.length,
      measurable: measurable.length,
      ok:        measurable.filter(r => r.verdict === "OK").length,
      underfill: measurable.filter(r => r.verdict === "缺").length,
      overflow:  measurable.filter(r => r.verdict === "溢").length,
    };

    // ANSI table for the dev console.
    console.group("%crolling-deck · fill report",
                  "color:#fbbf24;font-weight:bold;font-size:13px;");
    console.table(rows.map(r => ({
      key:         r.key,
      label:       r.screenLabel || "",
      "fill %":    r.fillPct ?? "—",
      verdict:     r.verdict ?? r.note,
      "content px / 874": r.contentBottomPx ?? "—",
      structure:   r.children?.join(" + ") || "",
    })));
    console.log("汇总", summary);
    if (summary.underfill || summary.overflow) {
      console.warn(
        `⚠ ${summary.underfill} 张内容缺 (< ${UNDERFILL_PCT}%) / `
        + `${summary.overflow} 张内容溢 (> ${OVERFLOW_PCT}%)`
      );
    } else {
      console.log("✓ 所有内容页填充率在 " + UNDERFILL_PCT + "-" + OVERFLOW_PCT + "% 之间");
    }
    console.groupEnd();
    return summary;
  };

  global.RollingDeckCheck = {
    fillReport,
    printReport,
    constants: { FIT_H, SLIDE_H, UNDERFILL_PCT, OVERFLOW_PCT },
  };

  // Auto-print if URL has ?check= (any value) — lets users just append
  // `?check` to the deck URL to get a one-shot report.
  if (typeof location !== "undefined" && /[?&]check(=|&|$)/.test(location.search)) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded",
                                () => setTimeout(printReport, 500));
    } else {
      setTimeout(printReport, 500);
    }
  }
})(window);
