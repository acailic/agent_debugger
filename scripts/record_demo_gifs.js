#!/usr/bin/env node
/**
 * Automated demo GIF recorder using Playwright + ffmpeg.
 * Records UI interactions and converts to optimized GIFs.
 *
 * Usage: CHROME_PATH=~/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome node scripts/record_demo_gifs.js
 */
const { chromium } = require("playwright");
const { execSync } = require("child_process");
const { existsSync, mkdirSync, readdirSync, unlinkSync } = require("fs");
const { join } = require("path");

const ROOT = join(__dirname, "..");
const CHROME = process.env.CHROME_PATH || "/home/nistrator/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome";
const UI = "http://localhost:5173/ui/";
const VP = { width: 1440, height: 900 };
const VIDEOS = "/tmp/pw-demo-videos";
const SCREENSHOTS = join(ROOT, "docs", "assets");
const GIF_OUT = join(ROOT, "docs", "assets", "gifs");

for (const d of [VIDEOS, SCREENSHOTS, GIF_OUT]) mkdirSync(d, { recursive: true });

// Clean old videos
for (const f of readdirSync(VIDEOS)) unlinkSync(join(VIDEOS, f));

function toGif(videoPath, gifPath, fps = 10, width = 960) {
  if (!existsSync(videoPath)) return false;
  try {
    execSync(
      `ffmpeg -y -i "${videoPath}" -vf "fps=${fps},scale=${width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" -loop 0 "${gifPath}"`,
      { stdio: "pipe", timeout: 60000 }
    );
    return existsSync(gifPath);
  } catch { return false; }
}

async function recordDemo(browser, name, actions) {
  const ctx = await browser.newContext({
    viewport: VP,
    recordVideo: { dir: VIDEOS, size: VP },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();

  await page.goto(UI, { waitUntil: "load", timeout: 60000 });
  await page.waitForTimeout(2000);

  // Run the demo actions
  await actions(page);

  // Small pause at end
  await page.waitForTimeout(1000);

  // Close to finalize video
  const video = page.video();
  const videoPath = await video.path().catch(() => null);
  await page.close();
  await ctx.close();

  // Wait for video to be written
  await new Promise(r => setTimeout(r, 500));

  return videoPath;
}

async function main() {
  if (!existsSync(CHROME)) {
    console.error(`Chrome not found at ${CHROME}`);
    process.exit(1);
  }

  console.log("Launching Chromium...");
  const browser = await chromium.launch({ executablePath: CHROME, headless: true });

  const results = [];

  // ── Demo 1: Full walkthrough ────────────────────────────────────────
  console.log("\n[1/6] Full walkthrough...");
  const v1 = await recordDemo(browser, "walkthrough", async (page) => {
    // Show session list
    await page.waitForTimeout(2000);
    await page.screenshot({ path: join(SCREENSHOTS, "screenshot-full-ui.png") });

    // Click a session with events
    const sessions = await page.locator("li, .session-card, [data-testid]").all();
    for (let i = 0; i < Math.min(3, sessions.length); i++) {
      try { await sessions[i].click(); await page.waitForTimeout(1500); } catch {}
    }

    // Try tabs
    for (const tab of ["Timeline", "Decision Tree", "Tools", "Analytics"]) {
      try {
        const el = page.locator(`button:has-text("${tab}"), [role=tab]:has-text("${tab}")`).first();
        await el.click({ timeout: 2000 });
        await page.waitForTimeout(1500);
      } catch {}
    }
  });

  if (v1 && toGif(v1, join(ROOT, "peek-v5-demo.gif"), 10, 960)) {
    const size = Math.round(parseInt(execSync(`stat --format=%s "${join(ROOT, "peek-v5-demo.gif")}"`).toString()) / 1024);
    results.push(`peek-v5-demo.gif (${size}KB)`);
  }

  // ── Demo 2: Decision Tree ───────────────────────────────────────────
  console.log("[2/6] Decision tree...");
  const v2 = await recordDemo(browser, "decision-tree", async (page) => {
    await page.waitForTimeout(1500);
    // Click first session
    const s = page.locator("li, .session-card, [data-testid]").first();
    try { await s.click(); await page.waitForTimeout(1000); } catch {}

    // Find and click Decision Tree tab
    const dt = page.locator(`button:has-text("Decision Tree"), [role=tab]:has-text("Decision Tree"), button:has-text("Tree")`).first();
    try {
      await dt.click({ timeout: 3000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: join(SCREENSHOTS, "screenshot-decision-tree.png") });

      // Click a node if visible
      const node = page.locator(".tree-node, [data-testid*=node], circle, .node").first();
      try { await node.click(); await page.waitForTimeout(1000); } catch {}
    } catch {}
  });

  if (v2 && toGif(v2, join(GIF_OUT, "demo-decision-tree.gif"), 8, 720)) {
    results.push("gifs/demo-decision-tree.gif");
  }

  // ── Demo 3: Timeline + Events ───────────────────────────────────────
  console.log("[3/6] Timeline...");
  const v3 = await recordDemo(browser, "timeline", async (page) => {
    await page.waitForTimeout(1500);
    const s = page.locator("li, .session-card, [data-testid]").first();
    try { await s.click(); await page.waitForTimeout(1000); } catch {}

    const tl = page.locator(`button:has-text("Timeline"), [role=tab]:has-text("Timeline"), button:has-text("Trace")`).first();
    try {
      await tl.click({ timeout: 3000 });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: join(SCREENSHOTS, "screenshot-timeline.png") });

      // Click through events
      const events = await page.locator(".event-item, [data-testid*=event], .timeline-event").all();
      for (let i = 0; i < Math.min(3, events.length); i++) {
        try { await events[i].click(); await page.waitForTimeout(800); } catch {}
      }
    } catch {}
  });

  if (v3 && toGif(v3, join(GIF_OUT, "demo-timeline.gif"), 8, 720)) {
    results.push("gifs/demo-timeline.gif");
  }

  // ── Demo 4: Search ──────────────────────────────────────────────────
  console.log("[4/6] Search...");
  const v4 = await recordDemo(browser, "search", async (page) => {
    await page.waitForTimeout(1500);
    const s = page.locator("li, .session-card, [data-testid]").first();
    try { await s.click(); await page.waitForTimeout(1000); } catch {}

    const search = page.locator(`button:has-text("Search"), [role=tab]:has-text("Search")`).first();
    try {
      await search.click({ timeout: 3000 });
      await page.waitForTimeout(1000);

      // Type in search
      const input = page.locator("input[type=text], input[placeholder*=earch]").first();
      try {
        await input.fill("error");
        await page.waitForTimeout(1500);
      } catch {}
      await page.screenshot({ path: join(SCREENSHOTS, "screenshot-search-results.png") });
    } catch {}
  });

  if (v4 && toGif(v4, join(GIF_OUT, "demo-search.gif"), 8, 720)) {
    results.push("gifs/demo-search.gif");
  }

  // ── Demo 5: Analytics ───────────────────────────────────────────────
  console.log("[5/6] Analytics...");
  const v5 = await recordDemo(browser, "analytics", async (page) => {
    await page.waitForTimeout(1500);
    const s = page.locator("li, .session-card, [data-testid]").first();
    try { await s.click(); await page.waitForTimeout(1000); } catch {}

    const analytics = page.locator(`button:has-text("Analytics"), [role=tab]:has-text("Analytics")`).first();
    try {
      await analytics.click({ timeout: 3000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: join(SCREENSHOTS, "screenshot-analytics.png") });
    } catch {}
  });

  if (v5 && toGif(v5, join(GIF_OUT, "demo-analytics.gif"), 8, 720)) {
    results.push("gifs/demo-analytics.gif");
  }

  // ── Demo 6: Session comparison ──────────────────────────────────────
  console.log("[6/6] Comparison...");
  const v6 = await recordDemo(browser, "comparison", async (page) => {
    await page.waitForTimeout(1500);
    const s = page.locator("li, .session-card, [data-testid]").first();
    try { await s.click(); await page.waitForTimeout(1000); } catch {}

    const compare = page.locator(`button:has-text("Compare"), [role=tab]:has-text("Compare")`).first();
    try {
      await compare.click({ timeout: 3000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: join(SCREENSHOTS, "screenshot-session-comparison.png") });
    } catch {}
  });

  if (v6 && toGif(v6, join(GIF_OUT, "demo-comparison.gif"), 8, 720)) {
    results.push("gifs/demo-comparison.gif");
  }

  await browser.close();

  // ── Summary ─────────────────────────────────────────────────────────
  console.log("\n" + "=".repeat(50));
  console.log("RESULTS:");
  for (const r of results) console.log(`  ✓ ${r}`);
  console.log(`\nScreenshots: ${SCREENSHOTS}`);
  console.log(`GIFs: ${GIF_OUT}`);

  if (existsSync(join(ROOT, "peek-v5-demo.gif"))) {
    console.log(`\nMain demo GIF: peek-v5-demo.gif`);
  }

  // Cleanup videos
  try {
    for (const f of readdirSync(VIDEOS)) unlinkSync(join(VIDEOS, f));
  } catch {}
}

main().catch(e => { console.error("Failed:", e.message); process.exit(1); });
