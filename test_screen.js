/*
 * test_screen.js: the 73 automated checks of the validation screen (run: node test_screen.js).
 * ATTRIBUTION: Written with AI assistance (Claude, Anthropic) and reviewed, run and
 * tested by the author, Bhuvanesi Barua. Stated per City St George's MSc Project
 * Guidance, Appendix C items 7 and 9.
 * Library: Playwright (Microsoft, Apache License 2.0), used to drive the screen in a browser.
 */
/* Test suite for Validation_screen.html.
   Run after any change to the screen:   node test_screen.js
   Exits non-zero if any check fails, so it can be trusted without reading it.

   WHERE IT LOOKS. The screen and the record it is checked against are looked for next
   to this file, in either of two layouts, so the suite runs from both without editing:
     project folder:     designs/Validation_screen.html   pipeline/out/episodes.json
     public repository:  index.html                       data/episode_0219fb71.json
   The repository's README gives the steps to install Playwright and run it.

   T1  page loads with no console errors, at a desktop size
   T2  the three counters start where they should
   T3  the device gate blocks below 820px wide or 560px tall, and only there
   T4  the "show it anyway" escape works
   T5  every statement shows exactly the evidence it claims to have
   T6  no clause carries both a <mark> and a <u class="nc"> (mutual exclusivity)
   T7  the researcher's reading is off on the plain link and on with ?notes=on
   T8  a decision survives a reload (localStorage save/resume)
   T9  N16's card contains its MRI line
   T10 every card's text is verbatim from episodes.json
   T24 the timeline key fits its panel at 1000, 1280, 1366 and 1440px (added 6 Oct)
   T25 no card header names the same thing twice (added 6 Oct)
   T26 every card title is the note's subject exactly as in episodes.json (added 6 Oct)
   T27 the nine uncarried lines are verbatim and underlined in their cards (added 7 Oct)

   NOTE ON T1. The only thing this page fetches is the Google Fonts stylesheet.
   The test container has no direct internet, so that request fails here and
   would not fail on a reviewer's machine. It is filtered out by URL; every
   other console error still fails the test.

   NOTE ON T2 and T5. Counter 2 does not start at zero. It reads "24 of 30"
   because the summary cites 24 of the 30 records, and the remaining six are
   accounted for only once the reviewer accepts them as unused. Likewise,
   thirteen statements show no record card: ten are field checks (name, NHS
   number, ward, the clinician's details) which are checked against the header
   rather than a ward note, one is not assessable, and two — "Discharge
   destination: Home" and "Secondary diagnoses: Not documented" — have nothing
   in the record behind them at all. That last pair is a finding, not a fault,
   so the test asserts the card count equals the declared evidence count.
*/
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const { pathToFileURL } = require("url");

/* the first of the candidate files that exists, relative to this file */
function pick(...candidates) {
  const found = candidates.map(c => path.resolve(__dirname, c)).find(p => fs.existsSync(p));
  if (!found) {
    console.error(`Cannot find any of: ${candidates.join(", ")}\n(looked next to ${__dirname})`);
    process.exit(2);
  }
  return found;
}
const SCREEN = pathToFileURL(pick("designs/Validation_screen.html", "index.html")).href;
const EPISODES = pick("pipeline/out/episodes.json", "data/episode_0219fb71.json");
const OFFLINE_OK = /fonts\.googleapis\.com|fonts\.gstatic\.com/;

let pass = 0, fail = 0;
const ok  = (t, m = "") => { pass++; console.log(`  PASS  ${t}${m ? "  — " + m : ""}`); };
const bad = (t, m = "") => { fail++; console.log(`  FAIL  ${t}${m ? "  — " + m : ""}`); };
const chk = (c, t, m = "") => c ? ok(t, m) : bad(t, m);

(async () => {
  const browser = await chromium.launch();

  /* ---------- T1  load, no console errors ---------- */
  console.log("\nT1  page load");
  let ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  let page = await ctx.newPage();
  const errs = [];
  page.on("console", m => {
    if (m.type() !== "error") return;
    const t = m.text();
    if (OFFLINE_OK.test(t) || /ERR_TUNNEL|ERR_INTERNET|ERR_NAME_NOT_RESOLVED/.test(t)) return;
    errs.push(t);
  });
  page.on("pageerror", e => errs.push("pageerror: " + e.message));
  await page.goto(SCREEN);
  await page.waitForTimeout(700);
  chk(errs.length === 0, "no console or page errors", errs.slice(0, 3).join(" | "));
  chk(await page.locator(".app").isVisible(), "the application renders");
  chk(!(await page.locator("#gate").isVisible()), "the gate is not shown at 1440x900");

  /* ---------- T2  counters ---------- */
  console.log("\nT2  counters at load");
  const v = async id => (await page.locator("#" + id).textContent()).trim();
  chk(await v("v1") === "0 of 50", 'checks decided: "0 of 50"', `got "${await v("v1")}"`);
  chk(await v("v2") === "24 of 30", 'records accounted for: "24 of 30"  (6 unused)',
      `got "${await v("v2")}"`);
  chk(await v("v3") === "0", 'problems found: "0"', `got "${await v("v3")}"`);

  /* ---------- T6  mutual exclusivity + T9 MRI + T10 verbatim ---------- */
  console.log("\nT6  mutual exclusivity of the two marks");
  const recs = await page.evaluate(() => {
    const out = {}; for (const k in REC) out[k] = REC[k][3]; return out;
  });
  let both = 0;
  for (const [rid, raw] of Object.entries(recs))
    if (/<mark>[^<]*<u class="nc">/.test(raw) || /<u class="nc">[^<]*<mark>/.test(raw)) {
      both++; bad("mutual exclusivity", `${rid} nests the two marks`);
    }
  chk(both === 0, "no clause carries both marks", `${Object.keys(recs).length} records checked`);

  console.log("\nT9  N16 shows its MRI line");
  const n16 = (recs.N16 || "").replace(/<[^>]+>/g, "");
  const mriLine = (n16.split("\n").find(l => /MRI/i.test(l)) || "").trim();
  chk(/MRI/i.test(n16), "N16 card contains MRI", mriLine.slice(0, 80));

  console.log("\nT10 card text is verbatim from the source notes");
  const eps = JSON.parse(fs.readFileSync(EPISODES, "utf8"));
  const ep  = eps.find(e => e.episode_id.startsWith("0219fb71"));
  const src = {}; for (const n of ep.notes) src["N" + n.seq] = n.text;
  const norm = s => s.replace(/\r\n/g, "\n").replace(/\s+/g, " ").trim();
  let drift = 0;
  for (const [rid, raw] of Object.entries(recs)) {
    const plain = norm(raw.replace(/<\/?mark>/g, "").replace(/<u class="nc">|<\/u>/g, ""));
    if (norm(src[rid]) !== plain) {
      drift++; bad("verbatim", `${rid} differs from episodes.json`);
      if (drift <= 2) {
        const a = norm(src[rid]);
        let i = 0; while (i < a.length && a[i] === plain[i]) i++;
        console.log(`        at char ${i}\n          note: ...${a.slice(Math.max(0,i-40), i+50)}`);
        console.log(`          card: ...${plain.slice(Math.max(0,i-40), i+50)}`);
      }
    }
  }
  chk(drift === 0, "all 30 cards match the source note exactly");

  /* ---------- T5  evidence panel ---------- */
  console.log("\nT5  each statement shows exactly the evidence it declares");
  const decl = await page.evaluate(() =>
    [...document.querySelectorAll(".st")].map(el =>
      ({ id: el.dataset.k, kind: ST[el.dataset.k].kind, ev: ST[el.dataset.k].ev.length })));
  chk(decl.length === 34, "34 statements present", `found ${decl.length}`);
  const wrong = [];
  for (let i = 0; i < decl.length; i++) {
    await page.locator(".st").nth(i).click();
    await page.waitForTimeout(45);
    const cards = await page.locator(".evl .rowtx").count();
    if (cards !== decl[i].ev) wrong.push(`${decl[i].id} wants ${decl[i].ev} got ${cards}`);
  }
  chk(wrong.length === 0, "card count matches the declared evidence everywhere",
      wrong.slice(0, 4).join("; "));
  const fields = decl.filter(d => d.kind === "f").length;
  const unsupported = decl.filter(d => d.kind === "c" && d.ev === 0).map(d => d.id);
  ok("breakdown", `${fields} field checks, ${unsupported.length} unsupported (${unsupported.join(", ")}), ` +
     `${decl.filter(d => d.kind === "na").length} not assessable`);

  /* ---------- T11  the card opens at the highlighted clause ---------- */
  console.log("\nT11 an overlong card opens at its highlighted clause");
  const ix1 = decl.findIndex(d => d.id === "x1");   // RCVS diagnosis: N6 is 2,242 chars
  await page.locator(".st").nth(ix1).click();
  await page.waitForTimeout(250);
  const frames = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll(".evl .rowtx").forEach((b, i) => {
      const m = b.querySelector("mark") || b.querySelector("u.nc");
      let inView = null;
      if (m) {
        const rb = b.getBoundingClientRect(), rm = m.getBoundingClientRect();
        inView = rm.top >= rb.top - 2 && rm.bottom <= rb.bottom + 2;
      }
      out.push({ i, over: b.scrollHeight > b.clientHeight + 2,
                 more: b.classList.contains("more"), top: Math.round(b.scrollTop),
                 hasMark: !!m, inView });
    });
    return out;
  });
  const over = frames.filter(f => f.over);
  chk(over.length > 0, "some cards are taller than the box", `${over.length} of ${frames.length}`);
  chk(over.every(f => f.more), "every overflowing card is marked scrollable");
  chk(frames.filter(f => !f.over).every(f => !f.more), "short cards are not faded");
  const withMark = frames.filter(f => f.hasMark);
  chk(withMark.length > 0 && withMark.every(f => f.inView),
      "the highlighted clause is inside the visible box",
      withMark.map(f => `#${f.i} scrollTop=${f.top} inView=${f.inView}`).join(", "));

  console.log("\nT12 the card can be scrolled by wheel");
  /* pick the card with the most hidden behind it, and start it at the top, so the
     wheel has somewhere to go — a card already at its bottom correctly passes the
     wheel on to the page, and testing that one proves nothing */
  const worst = await page.evaluate(() => {
    let best = -1, bi = 0;
    document.querySelectorAll(".evl .rowtx").forEach((b, i) => {
      const o = b.scrollHeight - b.clientHeight;
      if (o > best) { best = o; bi = i; }
    });
    const c = document.querySelectorAll(".evl .rowtx")[bi];
    c.scrollTop = 0;
    c.scrollIntoView({ block: "center" });   // the cursor must land on it
    return { bi, hidden: best };
  });
  await page.waitForTimeout(150);
  const box0 = page.locator(".evl .rowtx").nth(worst.bi);
  const t0 = await box0.evaluate(e => e.scrollTop);
  const pt = await box0.evaluate(e => { const r = e.getBoundingClientRect();
    return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2) }; });
  await page.mouse.move(pt.x, pt.y);
  await page.mouse.wheel(0, 200);
  await page.waitForTimeout(250);
  const t1 = await box0.evaluate(e => e.scrollTop);
  chk(t1 > t0, "wheel over a card scrolls the card",
      `card #${worst.bi}, ${worst.hidden}px hidden, scrollTop ${t0} -> ${t1}`);
  const fade = await box0.evaluate(e => getComputedStyle(e).maskImage || getComputedStyle(e).webkitMaskImage);
  chk(/gradient/.test(fade || ""), "the fade mask is applied", (fade || "none").slice(0, 60));

  /* ---------- T8  save / resume ---------- */
  console.log("\nT8  a decision survives a reload");
  const idx = decl.findIndex(d => d.id === "s1");
  await page.locator(".st").nth(idx).locator(".mk.ok").click();
  await page.waitForTimeout(200);
  const before = await v("v1");
  await page.reload();
  await page.waitForTimeout(700);
  const after = await v("v1");
  chk(before === "1 of 50" && after === "1 of 50",
      "the decision is still there after reload", `${before} -> ${after}`);
  await page.evaluate(() => localStorage.clear());
  await ctx.close();

  /* ---------- T7  researcher's reading ---------- */
  console.log("\nT7  the researcher's reading");
  for (const [suffix, want, who] of [["", "false", "plain link — what the clinical stakeholder gets"],
                                     ["?notes=on", "true", "?notes=on — what Mai gets"]]) {
    const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await c.newPage();
    await p.goto(SCREEN + suffix);
    await p.waitForTimeout(500);
    const got = await p.locator("#readtog").getAttribute("aria-pressed");
    const lbl = (await p.locator("#readtog").textContent()).trim();
    chk(got === want, `${who}: aria-pressed=${want}`, `got ${got}, label "${lbl}"`);
    await c.close();
  }

  /* ---------- T13-T19  per-record decisions on unused records ---------- */
  /* Added after supervision asked for the unused-records strip to be decidable one
     record at a time, and for a record to be flaggable at all. */
  {
    const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await c.newPage();
    const perr = [];
    p.on("pageerror", e => perr.push(e.message));
    await p.goto(SCREEN); await p.waitForTimeout(900);
    await p.evaluate(() => { try { localStorage.clear(); } catch (e) {} });
    await p.reload(); await p.waitForTimeout(900);
  const vv=async id=>(await p.locator("#"+id).textContent()).trim();
    const unused = await p.evaluate(()=>UNUSED);
    console.log("\nT13 the six unused records are individually decidable");
    chk(unused.length===6, "six unused records", unused.join(","));
    chk(await vv("v2")==="24 of 30", "counter 2 starts at 24 of 30", await vv("v2"));

    // open the first group
    await p.locator('[data-look]').first().click();
    await p.waitForTimeout(400);
    const ctrl = await p.evaluate(()=>({
      cards: document.querySelectorAll(".evl > li").length,
      pairs: document.querySelectorAll(".evl [data-rv]").length,
      shortcut: !!document.getElementById("accnow"),
    }));
    chk(ctrl.pairs === ctrl.cards*2, "every record card has a tick and a flag",
        `${ctrl.cards} cards, ${ctrl.pairs} buttons`);
    chk(ctrl.shortcut, "the Accept all shortcut is still there");

    console.log("\nT14 accepting one record moves counter 2 by exactly one");
    await p.locator('.evl [data-rv="ok"]').first().click();
    await p.waitForTimeout(300);
    chk(await vv("v2")==="25 of 30", "24 -> 25", await vv("v2"));

    console.log("\nT15 a record can be FLAGGED — the thing that was impossible before");
    await p.locator('.evl [data-rv="flag"]').nth(1).click();
    await p.waitForTimeout(300);
    chk(await vv("v2")==="26 of 30", "flagging also accounts for the record", await vv("v2"));
    chk(await vv("v3")==="1", "problems found = 1", await vv("v3"));
    const reason = p.locator(".evl input[data-rr]").first();
    chk(await reason.count()===1, "flagging opens a reason box");
    await reason.fill("The dietary advice should have reached the GP.");
    await p.waitForTimeout(300);
    const inProblems = await p.evaluate(()=>{
      const t=document.getElementById("probs").textContent;
      return t.includes("dietary advice should have reached") &&
             /Record the summary does not use/.test(t);
    });
    chk(inProblems, "the flagged record and its reason reach the problems list");
    const inExport = await p.evaluate(()=>{
      const t=document.getElementById("exp"); return t && t.value.includes("no statement in the summary draws on this record"); });
    chk(inExport, "and the copied report");

    console.log("\nT16 pressing the same mark again clears it");
    await p.locator('.evl [data-rv="ok"]').first().click();
    await p.waitForTimeout(300);
    chk(await vv("v2")==="25 of 30", "25 after clearing one", await vv("v2"));
    await p.locator('.evl [data-rv="ok"]').first().click();
    await p.waitForTimeout(300);

    console.log("\nT17 Accept all finishes the group, and one can still be changed after");
    await p.locator("#accnow").click();
    await p.waitForTimeout(400);
    const afterAll = await p.evaluate(()=>({
      v2:document.getElementById("v2").textContent.trim(),
      v3:document.getElementById("v3").textContent.trim(),
      stillHasPairs: document.querySelectorAll(".evl [data-rv]").length>0 }));
    chk(afterAll.v3==="0", "the shortcut overrides the flag to 'fine'", "problems "+afterAll.v3);
    chk(afterAll.stillHasPairs, "the per-record controls remain after Accept all");

    console.log("\nT18 everything decided unlocks the approve control");
    await p.evaluate(()=>{
      UNUSED.forEach(r=>verdict.set("rec:"+r,"ok"));
      [...ORDER, ...ABSENT_GATED, ...SPAN_IDS].forEach(k=>verdict.set(k,"ok"));
      render();
    });
    await p.waitForTimeout(400);
    const end = await p.evaluate(()=>({
      v1:document.getElementById("v1").textContent.trim(),
      v2:document.getElementById("v2").textContent.trim(),
      on:document.getElementById("app").classList.contains("on")}));
    chk(end.v1==="50 of 50", "counter 1 still totals 50", end.v1);
    chk(end.v2==="30 of 30", "counter 2 reaches 30", end.v2);
    chk(end.on, "approve unlocks");

    console.log("\nT19 a decision on a record survives a reload");
    await p.evaluate(()=>{try{localStorage.clear()}catch(e){}});
    await p.reload(); await p.waitForTimeout(800);
    await p.locator('[data-look]').first().click(); await p.waitForTimeout(350);
    await p.locator('.evl [data-rv="flag"]').first().click(); await p.waitForTimeout(300);
    const before = await vv("v2");
    await p.reload(); await p.waitForTimeout(900);
    chk(await vv("v2")===before && before!=="24 of 30",
        "record verdict restored", `${before} -> ${await vv("v2")}`);


    chk(perr.length === 0, "no page errors during the record checks", perr.slice(0,2).join(" | "));
    await c.close();
  }

  /* ---------- T20-T23  records are placed by their service ---------- */
  /* Added after supervision objected to a timeline row that was in practice
     "everything the pattern did not match". The rows now come from the record's
     own note_type field through an explicit map, and an unmapped service gets a
     visible row of its own rather than being absorbed. */
  {
    const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await c.newPage();
    const perr = []; p.on("pageerror", e => perr.push(e.message));
    await p.goto(SCREEN); await p.waitForTimeout(900);
    const L = await p.evaluate(() => ({
      shown: LANES_SHOWN.map(l => l.t),
      counts: Object.fromEntries(LANES_SHOWN.map(l => [l.k, RIDS.filter(r => laneKey(r) === l.k).length])),
      services: [...new Set(RIDS.map(svcOf))].sort(),
      unmapped: RIDS.filter(r => laneKey(r) === "other"),
      groups: GROUPS.map(g => g.t),
      everyRecordPlaced: RIDS.every(r => !!laneOf(r)),
      n18: { svc: svcOf("N18"), lane: laneKey("N18") },
    }));
    console.log("\nT20 rows come from the record's own service field");
    chk(L.services.length === 6, "six services in the episode", L.services.join(" · "));
    chk(L.everyRecordPlaced, "every record resolves to a row");
    chk(L.counts.ed === 5 && L.counts.med === 17 && L.counts.ther === 8,
        "5 emergency / 17 medical / 8 therapies", JSON.stringify(L.counts));

    console.log("\nT21 no catch-all: the unrecognised row is empty and hidden");
    chk(L.unmapped.length === 0, "no record falls through the map");
    chk(!L.shown.includes("SERVICE NOT RECOGNISED"), "so that row is not drawn",
        L.shown.join(" | "));

    console.log("\nT22 an unknown service would surface, not be absorbed");
    const probe = await p.evaluate(() => {
      const before = LANES_SHOWN.length;
      const was = SERVICE.N6; SERVICE.N6 = "Cardiology Inpatients";   // a service the map has never seen
      const lane = laneKey("N6");
      SERVICE.N6 = was;
      return { lane, before };
    });
    chk(probe.lane === "other", "an unmapped service routes to 'not recognised', not to medical",
        `got ${probe.lane}`);

    console.log("\nT23 unused records are grouped by department, not by 'everything else'");
    chk(!L.groups.includes("Everything else"), "no 'Everything else' group", L.groups.join(" · "));
    chk(L.groups.every(g => L.services.includes(g)), "every group is a named service",
        L.groups.join(" · "));
    chk(L.n18.svc === "Neurology Inpatients" && L.n18.lane === "med",
        "N18 follows its service, not the word in its title", JSON.stringify(L.n18));
    chk(perr.length === 0, "no page errors", perr.slice(0,2).join(" | "));
    await c.close();
  }

  /* ---------- T24-T25  display faults found 6 Oct, kept from coming back ----------
     T24: the timeline key was clipped on the right at laptop widths after the rows
     sentence grew on 2 Oct ("used by some other lin"). T25: N5's card read
     "ED Depart Summary · ED Depart Summary" because its title equals its service. */
  console.log("\nT24 the timeline key is not cut off on the right");
  for (const w of [1000, 1280, 1366, 1440]) {
    const c = await browser.newContext({ viewport: { width: w, height: 900 } });
    const p = await c.newPage();
    const perr = []; p.on("pageerror", e => perr.push(e.message));
    await p.goto(SCREEN);
    await p.waitForTimeout(400);
    await p.evaluate(() => {
      const el = [...document.querySelectorAll(".st")].find(e => e.dataset.k === "i2");
      if (el) el.click();
    });
    await p.waitForTimeout(300);
    const m = await p.evaluate(() => {
      const viz = document.querySelector(".viz"), key = viz.querySelector(".vizkey");
      const edge = viz.getBoundingClientRect().right;
      const cut = [...key.querySelectorAll(".k")]
        .filter(k => k.getBoundingClientRect().right > edge + 1)
        .map(k => k.textContent.trim().replace(/\s+/g, " ").slice(0, 28));
      return { sw: viz.scrollWidth, cw: viz.clientWidth, cut };
    });
    chk(m.cut.length === 0 && m.sw <= m.cw + 1 && perr.length === 0,
        `key fits its panel at ${w}px, no sideways scroll`,
        m.cut.length ? "cut: " + m.cut.join(" | ") : `${m.sw} <= ${m.cw}`);
    await c.close();
  }

  console.log("\nT25 a card names its source once");
  {
    const c = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p = await c.newPage();
    await p.goto(SCREEN);
    await p.waitForTimeout(400);
    const r = await p.evaluate(() => {
      const heads = {};
      for (const id of RIDS) {
        const d = document.createElement("div");
        d.innerHTML = card(id, "c", "", "");
        heads[id] = d.querySelector(".rid").textContent.replace(/\s+/g, " ").trim();
      }
      const repeats = Object.entries(heads).filter(([, h]) => {
        const parts = h.split(" · ").map(s => s.trim());
        return parts.some((s, i) => i > 0 && s === parts[i - 1]);
      }).map(([id]) => id);
      return { repeats, n5: heads.N5, n18: heads.N18 };
    });
    chk(r.repeats.length === 0, "no card header repeats a label", r.repeats.join(", ") || "none of 30");
    chk((r.n5.match(/ED Depart Summary/g) || []).length === 1,
        "N5 names 'ED Depart Summary' once", r.n5);
    chk(/Neurology Inpatients · Dietary Consultation/.test(r.n18),
        "N18 still shows service and title when they differ", r.n18);

    /* T26: the title on a card is the record's subject as written. Until 6 Oct,
       11 of 30 were shortened or re-cased by hand ("GP contacted" for "GP contacted
       re: RCVS and discharge") while the card text beneath was verbatim. */
    console.log("\nT26 every card title is the note's subject as written");
    const ep26 = JSON.parse(fs.readFileSync(EPISODES, "utf8")).find(e => e.episode_id.startsWith("0219fb71"));
    const subj = Object.fromEntries(ep26.notes.map(n => ["N" + n.seq, n.note_subject]));
    const titles = await p.evaluate(() => Object.fromEntries(RIDS.map(id => [id, REC[id][1]])));
    const off = Object.keys(subj).filter(id => titles[id] !== subj[id]);
    chk(off.length === 0, "all 30 titles match note_subject in episodes.json",
        off.length ? off.map(id => `${id} "${titles[id]}"`).join("; ") : "30 of 30");

    /* T27: the nine uncarried lines are quoted as written and underlined where they
       sit. Until 7 Oct four quotes had been tidied ("review" for "re view",
       "Non-smoker" for "Non-s moker", a sentence cut short, a full stop added), and
       two of them were therefore never underlined in their cards. */
    console.log("\nT27 every uncarried line is verbatim and underlined in its card");
    const src27 = Object.fromEntries(ep26.notes.map(n => ["N" + n.seq, n.text]));
    const flat27 = s => s.replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim();
    const norm27 = s => flat27(s).replace(/\.$/, "");   // the underline omits a closing full stop
    const spans = await p.evaluate(() => SPANS.map(([sid, r, quote]) => {
      const m = markUncarried(r, REC[r][3]);
      const d = document.createElement("div"); d.innerHTML = m.html;
      const under = [...d.querySelectorAll("u.nc")].map(u => u.textContent);
      return { sid, r, quote, under };
    }));
    /* full stop kept here, so an added full stop or a sentence cut short both fail */
    const notVerbatim = spans.filter(s => !flat27(src27[s.r]).includes(flat27(s.quote)));
    const notUnder = spans.filter(s => !s.under.some(u => norm27(u) === norm27(s.quote)));
    chk(spans.length === 9, "nine uncarried lines", `${spans.length}`);
    chk(notVerbatim.length === 0, "each quote is in its record exactly as written",
        notVerbatim.map(s => `${s.sid} ${s.r}`).join(", ") || "9 of 9");
    chk(notUnder.length === 0, "each one is underlined in its own card",
        notUnder.map(s => `${s.sid} ${s.r}`).join(", ") || "9 of 9");
    await c.close();
  }

  /* ---------- T3 / T4  the device gate ---------- */
  console.log("\nT3  the device gate  (threshold: under 820 wide or under 560 tall)");
  const SIZES = [
    [1920, 1080, false], [1440,  900, false], [1280,  800, false],
    [1024,  768, false], [ 900,  600, false], [ 820,  560, false],
    [ 819,  900, true ], [ 768, 1024, true ], [ 430,  932, true ],
    [ 390,  844, true ], [ 932,  430, true ], [1440,  559, true ],
  ];
  for (const [w, h, blocked] of SIZES) {
    const c = await browser.newContext({ viewport: { width: w, height: h } });
    const p = await c.newPage();
    await p.goto(SCREEN);
    await p.waitForTimeout(250);
    const gate = await p.locator("#gate").isVisible();
    const app  = await p.locator(".app").isVisible();
    chk(gate === blocked && app === !blocked,
        `${String(w).padStart(4)}x${String(h).padStart(4)}  ${blocked ? "blocked" : "allowed"}`,
        gate === blocked ? "" : `gate=${gate} app=${app}`);
    if (blocked && w === 390) {
      await p.locator("#anyway").click();
      await p.waitForTimeout(200);
      chk(await p.locator(".app").isVisible() && !(await p.locator("#gate").isVisible()),
          "T4  \"show it anyway\" reveals the screen");
    }
    await c.close();
  }

  await browser.close();
  console.log(`\n${"=".repeat(52)}\n  ${pass} passed, ${fail} failed\n${"=".repeat(52)}\n`);
  process.exit(fail ? 1 : 0);
})();
