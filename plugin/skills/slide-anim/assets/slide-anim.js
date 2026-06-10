/* ════════════════════════════════════════════════════════════════════════════
   slide-anim · GSAP-driven entrance choreography for deck slides

   Drop-in animation engine. After loading GSAP 3 + SplitText, include this
   file and call `RollingSlideAnim.autoHook()` once. The engine then watches
   for any `.slide` element gaining the `active` class and choreographs an
   entrance for it based on what components the slide contains — no per-page
   markup required.

   Public API on `window.RollingSlideAnim`:
     · animate(slideEl)   — choreograph one slide manually
     · autoHook(opts?)    — observe DOM and animate any slide that goes .active
     · finish()           — jump the in-flight timeline to its terminal state
                            (called automatically before print)
     · disable() / enable()
     · config(partial)    — merge overrides into the engine config

   Detects and animates automatically:
     · Titles (.section-head h2, .goals-head h2, .divider-title, .quote-text, h1)
       → SplitText char-by-char rise
     · `.kicker` → fade-from-left
     · `.copy` / `.divider-sub` / `.quote-by` / `.cover-lead` → fade-up
     · `.tenx-mega` / `.divider-num` → slide-in from right
     · Grids (.cards-{2,3,4,6}, .hero-stats, .goals-grid, .agenda-list,
       .media-grid, .timeline-nodes, .team-grid, .logo-wall, .chart-kpis,
       .org-stack, .phase-strip, .incub-milestones, .video-side,
       [data-stagger]) → children stagger up
     · `.media-frame` → scale up; `.media-bg` → Ken Burns
     · `.stat-num`, `[data-count]` → number count-up with prefix/suffix
       preservation (works for "10×", "98%", "-58%", "4.8", "1,200")
     · `.bar-fill` → scaleY grow
     · `.donut-arc` → stroke-dashoffset draw
     · `.timeline-line` → scaleX draw
     · Bands (`.synth-band, .cadence-note, .ceo-core, .coach-band, .goals-foot,
       .cover-note, .band, .end-contact`) → fade-up
     · `[data-anim="rise|fade|left|right|scale|blur"]` + `data-anim-delay="0.4"`
       → manual control for anything custom

   Skip conditions (no animation runs):
     · `prefers-reduced-motion: reduce`
     · `gsap` not loaded
     · Slide has `cover-hero` class (covers usually own their entrance)
     · Body has `static-mode` or `edit-mode` class

   Adapted from RollingAI 2026 Vibe / 0-Template / html-deck-template-single.html
   ──────────────────────────────────────────────────────────────────────────── */
(function (global) {
  "use strict";

  const DEFAULTS = {
    // Selectors — override via RollingSlideAnim.config({titleSel: "..."})
    titleSel:   ".section-head h2, .goals-head h2, .divider-title, .quote-text, h1",
    kickerSel:  ".kicker",
    leadSel:    ".section-head .copy, .goals-head .copy, .divider-sub, .quote-by, .quote-mark, .divider-line, .cover-lead",
    megaSel:    ".tenx-mega, .divider-num",
    groupSel:   ".cards-2, .cards-3, .cards-4, .cards-6, .hero-stats, .ceo-grid, .goals-grid, .agenda-list, .media-grid, .timeline-nodes, .team-grid, .logo-wall, .chart-kpis, .org-stack, .phase-strip, .incub-milestones, .video-side, [data-stagger]",
    bandSel:    ".synth-band, .cadence-note, .ceo-core, .coach-band, .goals-foot, .cover-note, .band, .end-contact",
    countSel:   ".stat-num, [data-count]",
    barSel:     ".bar-fill",
    donutSel:   ".donut-arc",
    timelineLineSel: ".timeline-line",
    skipSlideSel: ".cover-hero",       // slides whose entrance is owned elsewhere
    skipBodyClasses: ["static-mode", "edit-mode"],
    // Tuning
    timelineDefaults: { ease: "power3.out", duration: .8 },
    countDuration: 1.1,
  };

  const ANIM_PRESETS = {
    rise:  { y: 46, opacity: 0 },
    fade:  { opacity: 0 },
    left:  { x: -70, opacity: 0 },
    right: { x: 70, opacity: 0 },
    scale: { scale: .86, opacity: 0 },
    blur:  { opacity: 0, filter: "blur(14px)" }
  };

  let cfg = Object.assign({}, DEFAULTS);
  let enabled = true;
  let slideTl = null;
  let activeSplits = [];
  let observer = null;
  let splitTextRegistered = false;

  const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
  const hasGsap = () => typeof gsap !== "undefined";
  const hasSplitText = () => typeof SplitText !== "undefined";

  const bodySkips = () =>
    cfg.skipBodyClasses.some(c => document.body.classList.contains(c));

  // Count-up that preserves any prefix / suffix around the digit run.
  // raw="10×"   → animates 0→10, restores "10×"
  // raw="-58%"  → animates 0→58, restores "-58%"
  // raw="1,200" → animates 0→1200, restores "1,200"
  //
  // Two skip conditions for SAFETY:
  //   1. Element has child element nodes (rich HTML — <br>, <span>, …).
  //      Replacing textContent would FLATTEN the structure, then onComplete
  //      restores `raw` which is also flat text → layout permanently lost.
  //      Authors who DO want a count-up on a rich element should use
  //      `data-count="42%"` on a leaf, not on the multi-line container.
  //   2. The matched digit run contains a hyphen-minus on both sides
  //      ("3-5天" → prefix "", number "3", suffix "-5天" reads as garbage
  //      mid-animation). Detected by checking the char after the match.
  //      Pure negative numbers ("-58%") still work — the minus is part of
  //      the matched group via the leading `-?`.
  // Authors can opt out per-element via `data-no-count` attribute.
  const countUp = (el, tl, at) => {
    if (el.hasAttribute("data-no-count")) return;
    if (el.children.length > 0) return;     // rule 1: rich HTML
    const raw = (el.dataset.countOriginal ??= el.textContent.trim());
    const m = raw.match(/-?\d[\d,]*\.?\d*/);
    if (!m) return;
    // rule 2: number is followed by '-' AND followed-by-digit → "range" like
    // "3-5", animation would render "0-5", "1-5" etc. Skip.
    const afterIdx = m.index + m[0].length;
    if (raw[afterIdx] === "-" && /\d/.test(raw[afterIdx + 1] || "")) return;
    const target = parseFloat(m[0].replace(/,/g, ""));
    const prefix = raw.slice(0, m.index);
    const suffix = raw.slice(afterIdx);
    const dec = (m[0].split(".")[1] || "").length;
    const obj = { v: 0 };
    tl.to(obj, {
      v: target, duration: cfg.countDuration, ease: "power2.out",
      onUpdate:   () => { el.textContent = prefix + obj.v.toFixed(dec) + suffix; },
      onComplete: () => { el.textContent = raw; }
    }, at);
  };

  const animate = (sl) => {
    if (!enabled) return;
    if (!sl || !hasGsap() || reducedMotion()) return;
    if (sl.matches && sl.matches(cfg.skipSlideSel)) return;
    if (bodySkips()) return;

    if (hasSplitText() && !splitTextRegistered) {
      try { gsap.registerPlugin(SplitText); splitTextRegistered = true; } catch {}
    }

    // Kill the previous timeline (and revert any SplitTexts) so a fast page-flip
    // doesn't leave us frozen mid-transition.
    if (slideTl) { try { slideTl.progress(1); } catch {} slideTl.kill(); }
    activeSplits.forEach(s => { try { s.revert(); } catch {} });
    activeSplits = [];

    // Clear any leftover GSAP inline state on the elements we're about to
    // touch. Without this, a re-visit to a slide that previously animated
    // sees lingering inline `opacity:1; transform:translate(0,0)` from the
    // first run — and `tl.from(...)` at a non-zero `at` position lets those
    // inline values show during the pre-tween gap, so the slide LOOKS like
    // it's "already arrived" and the tween produces no visible motion.
    // Clearing puts everything back to CSS-default before we re-queue.
    const allTargets = [
      ...sl.querySelectorAll(cfg.titleSel),
      ...sl.querySelectorAll(cfg.kickerSel),
      ...sl.querySelectorAll(cfg.leadSel),
      ...sl.querySelectorAll(cfg.megaSel),
      ...sl.querySelectorAll(cfg.bandSel),
      ...sl.querySelectorAll("[data-anim]"),
    ];
    sl.querySelectorAll(cfg.groupSel).forEach(g => allTargets.push(...g.children));
    sl.querySelectorAll(".media-frame, .media-bg, .media-overlay > *").forEach(e => allTargets.push(e));
    if (allTargets.length) gsap.set(allTargets, { clearProps: "transform,opacity,filter" });

    const tl = slideTl = gsap.timeline({ defaults: cfg.timelineDefaults });

    // 1 · Main title — char-by-char rise via SplitText; fall back to whole-block rise.
    const head = sl.querySelector(cfg.titleSel);
    if (head && hasSplitText()) {
      try {
        const split = new SplitText(head, { type: "chars" });
        activeSplits.push(split);
        tl.from(split.chars, {
          y: 36, opacity: 0, duration: .55, stagger: .016,
          onComplete: () => { try { split.revert(); } catch {} }
        }, 0);
      } catch { tl.from(head, ANIM_PRESETS.rise, 0); }
    } else if (head) {
      tl.from(head, ANIM_PRESETS.rise, 0);
    }

    // 2 · Kicker + lead copy
    sl.querySelectorAll(cfg.kickerSel).forEach(el => {
      if (el.closest(".media-overlay")) return;
      tl.from(el, Object.assign({}, ANIM_PRESETS.left, { duration: .6 }), 0);
    });
    sl.querySelectorAll(cfg.leadSel).forEach(el =>
      tl.from(el, { opacity: 0, y: 24, duration: .7 }, .25)
    );
    const mega = sl.querySelector(cfg.megaSel);
    if (mega) tl.from(mega, { opacity: 0, x: 90, duration: 1.1, ease: "power2.out" }, .1);

    // 3 · Card groups — stagger children.
    //   Default stagger = 0.09s (children land in quick succession, reads as
    //   a single coordinated entrance).
    //   Authors who want a slower "依次出场" beat — each child clearly lands
    //   before the next starts — add `data-stagger="0.5"` (seconds) on the
    //   container. Bare `data-stagger` without a value still works as a
    //   group-marker.
    //   Optional `data-stagger-delay="0.6"` overrides the group's start
    //   offset (default .3s into the slide timeline).
    sl.querySelectorAll(cfg.groupSel).forEach(group => {
      const kids = [...group.children];
      if (!kids.length) return;
      const raw = group.dataset.stagger;
      const staggerSec = (raw && !isNaN(parseFloat(raw))) ? parseFloat(raw) : .09;
      const startAt = parseFloat(group.dataset.staggerDelay) || .3;
      tl.from(kids, { y: 54, opacity: 0, duration: .75, stagger: staggerSec }, startAt);
    });

    // 4 · Media frames + full-bleed bg with Ken Burns
    sl.querySelectorAll(".media-frame").forEach((el, i) => {
      if (el.closest(".media-grid")) return; // grid items handled by group stagger
      tl.from(el, { opacity: 0, scale: .94, duration: .9, ease: "power2.out" }, .25 + i * .12);
    });
    const bg = sl.querySelector(".media-bg");
    if (bg) {
      tl.from(bg, { scale: 1.12, opacity: .4, duration: 1.4, ease: "power2.out" }, 0);
      tl.to(bg, { scale: 1.06, duration: 14, ease: "none" }, 1.4); // Ken Burns drift
      sl.querySelectorAll(".media-overlay > *").forEach((el, i) =>
        tl.from(el, { y: 40, opacity: 0, duration: .8 }, .4 + i * .14)
      );
    }

    // 5 · Number count-up
    sl.querySelectorAll(cfg.countSel).forEach(el => countUp(el, tl, .45));

    // 6 · Charts — bars grow, donut arcs draw, timeline line draws
    const bars = sl.querySelectorAll(cfg.barSel);
    if (bars.length) tl.from(bars, { scaleY: 0, duration: 1, ease: "power3.inOut", stagger: .12 }, .35);
    sl.querySelectorAll(cfg.donutSel).forEach(arc => {
      const c   = parseFloat(arc.getAttribute("stroke-dasharray")) || 754;
      const pct = parseFloat(arc.dataset.pct || 70);
      tl.fromTo(arc,
        { strokeDashoffset: c },
        { strokeDashoffset: c * (1 - pct / 100), duration: 1.3, ease: "power2.inOut" },
        .45);
    });
    const tline = sl.querySelector(cfg.timelineLineSel);
    if (tline) tl.from(tline, { scaleX: 0, duration: 1, ease: "power2.inOut" }, .3);

    // 7 · Closing bands
    sl.querySelectorAll(cfg.bandSel).forEach(el =>
      tl.from(el, { y: 30, opacity: 0, duration: .7 }, .65)
    );

    // 8 · Manual per-element overrides
    sl.querySelectorAll("[data-anim]").forEach(el => {
      const p = ANIM_PRESETS[el.dataset.anim] || ANIM_PRESETS.rise;
      tl.from(el, Object.assign({}, p, { duration: .8 }), parseFloat(el.dataset.animDelay || .2));
    });

    return tl;
  };

  // MutationObserver — runs animate() whenever any `.slide` gains the `active`
  // class. Lets the engine work without modifying the deck's existing show()
  // function. Idempotent: calling autoHook() twice is a no-op.
  const autoHook = (opts) => {
    if (opts) Object.assign(cfg, opts);
    if (observer) return;
    observer = new MutationObserver(muts => {
      for (const m of muts) {
        if (m.type !== "attributes" || m.attributeName !== "class") continue;
        const el = m.target;
        if (el.classList && el.classList.contains("slide") && el.classList.contains("active")) {
          // Re-animate only when the slide TRANSITIONS into active.
          if (el.__slideAnimLast === "active") continue;
          el.__slideAnimLast = "active";
          animate(el);
        } else if (el.classList && el.classList.contains("slide")) {
          el.__slideAnimLast = "inactive";
        }
      }
    });
    observer.observe(document.body, {
      subtree: true, attributes: true, attributeFilter: ["class"]
    });
    // Kick off the currently-active slide so the FIRST page also animates.
    const initial = document.querySelector(".slide.active");
    if (initial) { initial.__slideAnimLast = "active"; animate(initial); }
  };

  const finish = () => {
    if (slideTl) { try { slideTl.progress(1); } catch {} }
    activeSplits.forEach(s => { try { s.revert(); } catch {} });
    activeSplits = [];
  };

  window.addEventListener("beforeprint", finish);

  global.RollingSlideAnim = {
    animate,
    autoHook,
    finish,
    enable:  () => { enabled = true; },
    disable: () => { enabled = false; finish(); },
    config:  (partial) => { Object.assign(cfg, partial); return cfg; },
    get cfg() { return cfg; },
    get isAnimating() { return !!slideTl && slideTl.isActive(); },
  };
})(window);
