#!/usr/bin/env node
/**
 * Automated demo GIF recorder using Playwright + ffmpeg.
 * Iteration 3: Fixed tab navigation, selectors, and wait times.
 *
 * UI structure (confirmed from source):
 *   - 3 tabs: "Trace" (default), "Inspect", "Analytics"
 *   - Tabs use button.tab-btn with .active class
 *   - Left rail: session list with .session-card items
 *   - Trace tab: SessionReplay, TraceTimeline (.timeline-event), SearchPanel (#search-input)
 *   - Inspect tab: DecisionTree (.decision-tree), Tool Inspector, LLM Viewer,
 *     Conversation Panel, Comparison (.comparison-panel), Live Dashboard,
 *     Checkpoints, Drift Alerts, FailureClusterPanel (.failure-cluster-panel, .cluster-card),
 *     MultiAgentCoordinationPanel
 *   - Analytics tab: Lazy-loaded AnalyticsTab (separate, NOT where failure clustering lives)
 *
 * Usage: node scripts/record_demo_gifs.js
 */
const { chromium } = require("playwright");
const { execSync } = require("child_process");
const { existsSync, mkdirSync, readdirSync, unlinkSync } = require("fs");
const { join } = require("path");

const ROOT = join(__dirname, "..");
const CHROME = process.env.CHROME_PATH;
const UI = process.env.UI_URL || "http://localhost:5173";
const VP = { width: 1440, height: 900 };
const VIDEOS = "/tmp/pw-demo-videos";
const GIF_OUT = join(ROOT, "docs", "assets", "gifs");

// Slower GIFs: fps=3, width=640, slowdown=2.0 for better visibility
const FPS = 3;
const WIDTH = 640;
const SLOWDOWN = 2.0;

for (const d of [VIDEOS, GIF_OUT]) mkdirSync(d, { recursive: true });
for (const f of readdirSync(VIDEOS)) unlinkSync(join(VIDEOS, f));

function toGif(videoPath, gifPath) {
  if (!existsSync(videoPath)) return false;
  try {
    const setpts = SLOWDOWN > 1 ? `setpts=${SLOWDOWN}*PTS,` : "";
    execSync(
      `ffmpeg -y -i "${videoPath}" -vf "${setpts}fps=${FPS},scale=${WIDTH}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" -loop 0 "${gifPath}"`,
      { stdio: "pipe", timeout: 120000 }
    );
    return existsSync(gifPath);
  } catch (e) {
    console.error(`  toGif failed: ${e.message?.slice(0, 100)}`);
    return false;
  }
}

async function recordDemo(browser, actions) {
  const ctx = await browser.newContext({
    viewport: VP,
    recordVideo: { dir: VIDEOS, size: VP },
    deviceScaleFactor: 1,
  });
  const page = await ctx.newPage();
  await page.goto(UI, { waitUntil: "load", timeout: 60000 });
  await page.waitForTimeout(2500);

  await actions(page);

  await page.waitForTimeout(1000);

  const video = page.video();
  const videoPath = await video.path().catch(() => null);
  await page.close();
  await ctx.close();
  await new Promise((r) => setTimeout(r, 500));
  return videoPath;
}

/** Click a session card by index. */
async function clickSession(page, idx = 0) {
  const cards = await page.locator(".session-card").all();
  if (cards.length > idx) {
    await cards[idx].click();
    await page.waitForTimeout(2000);
    return true;
  }
  return false;
}

/** Click a main tab by name. */
async function clickTab(page, name) {
  const tab = page
    .locator(`button.tab-btn:has-text("${name}")`)
    .first();
  try {
    await tab.click({ timeout: 5000 });
    await page.waitForTimeout(2500);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  console.log("Launching Chromium...");
  const browser = await chromium.launch({
    ...(CHROME && { executablePath: CHROME }),
    headless: true,
  });
  const results = [];

  // ── 1. Decision Tree Visualization ──────────────────────────────────
  console.log("\n[1/5] Decision Tree...");
  const v1 = await recordDemo(browser, async (page) => {
    await clickSession(page, 0);
    await clickTab(page, "Inspect");
    await page.waitForTimeout(3000);

    // Click 2 tree nodes to show details
    const nodes = await page.locator(".decision-tree .node, .tree-node, circle").all();
    for (let i = 0; i < Math.min(2, nodes.length); i++) {
      try { await nodes[i].click(); await page.waitForTimeout(2500); } catch {}
    }

    // Try "Jump to Recommended" if available
    const jumpBtn = page.locator("button:has-text('Jump'), button:has-text('Recommended')").first();
    try { await jumpBtn.click(); await page.waitForTimeout(2500); } catch {}
  });

  if (v1 && toGif(v1, join(GIF_OUT, "demo-decision-tree.gif"))) {
    const sz = Math.round(parseInt(execSync(`stat --format=%s "${join(GIF_OUT, "demo-decision-tree.gif")}"`).toString()) / 1024);
    results.push(`demo-decision-tree.gif (${sz}KB)`);
  } else {
    results.push("demo-decision-tree.gif FAILED");
  }

  // ── 2. Timeline / Checkpoint Replay ─────────────────────────────────
  // Actual DOM uses .timeline-marker, .replay-btn.play-pause, .replay-btn.step-forward
  console.log("[2/5] Timeline (Checkpoint Replay)...");
  const v2 = await recordDemo(browser, async (page) => {
    await clickSession(page, 0);
    // Trace tab is default after session click
    await page.waitForTimeout(2000);

    // Wait for timeline markers, then click 1 to show event detail
    try {
      await page.waitForSelector(".timeline-marker", { timeout: 8000 });
      const markers = await page.locator(".timeline-marker").all();
      console.log(`  Timeline markers found: ${markers.length}`);
      // Click 1 marker for event detail
      if (markers.length > 2) {
        try { await markers[2].click(); await page.waitForTimeout(1200); } catch {}
      }
    } catch {
      console.log("  No .timeline-marker found, continuing anyway...");
    }

    // Step forward 3 times to show replay advancing
    const stepBtn = page.locator("button.replay-btn.step-forward").first();
    try {
      for (let i = 0; i < 3; i++) {
        await stepBtn.click();
        await page.waitForTimeout(1000);
      }
    } catch {}
  });

  if (v2 && toGif(v2, join(GIF_OUT, "demo-timeline.gif"))) {
    const sz = Math.round(parseInt(execSync(`stat --format=%s "${join(GIF_OUT, "demo-timeline.gif")}"`).toString()) / 1024);
    results.push(`demo-timeline.gif (${sz}KB)`);
  } else {
    results.push("demo-timeline.gif FAILED");
  }

  // ── 3. Trace Search ─────────────────────────────────────────────────
  console.log("[3/5] Trace Search...");
  const v3 = await recordDemo(browser, async (page) => {
    await clickSession(page, 0);
    // Trace tab is default
    await page.waitForTimeout(3000);

    // Wait for search input to be visible in the detail rail
    try {
      await page.waitForSelector("#search-input", { state: "visible", timeout: 8000 });
      const searchInput = page.locator("#search-input");
      await searchInput.click();
      await page.waitForTimeout(1000);
      // Type character by character for visual effect
      await searchInput.type("error", { delay: 500 });
      await page.waitForTimeout(4000);

      // Click a search result if available
      const resultItem = page.locator(".search-result, .result-item").first();
      try { await resultItem.click(); await page.waitForTimeout(2500); } catch {}
    } catch (e) {
      console.log("  Search interaction failed:", e.message?.slice(0, 80));
    }
  });

  if (v3 && toGif(v3, join(GIF_OUT, "demo-trace-search.gif"))) {
    const sz = Math.round(parseInt(execSync(`stat --format=%s "${join(GIF_OUT, "demo-trace-search.gif")}"`).toString()) / 1024);
    results.push(`demo-trace-search.gif (${sz}KB)`);
  } else {
    results.push("demo-trace-search.gif FAILED");
  }

  // ── 4. Failure Clustering ───────────────────────────────────────────
  // FIX: FailureClusterPanel is in the Inspect tab, NOT Analytics tab
  console.log("[4/5] Failure Clustering...");
  const v4 = await recordDemo(browser, async (page) => {
    await clickSession(page, 0);
    await clickTab(page, "Inspect");
    await page.waitForTimeout(4000);

    // Scroll down to the Intelligence section where failure clusters live
    const clusterPanel = page.locator(".failure-cluster-panel").first();
    try {
      await clusterPanel.scrollIntoViewIfNeeded({ timeout: 5000 });
      await page.waitForTimeout(2000);
    } catch {}

    // Click 2 cluster cards
    const clusters = await page.locator(".cluster-card").all();
    console.log(`  Found ${clusters.length} cluster cards`);
    for (let i = 0; i < Math.min(2, clusters.length); i++) {
      try { await clusters[i].click(); await page.waitForTimeout(3000); } catch {}
    }

    // Also try cluster pills if present
    const pills = await page.locator(".cluster-pill").all();
    for (let i = 0; i < Math.min(2, pills.length); i++) {
      try { await pills[i].click(); await page.waitForTimeout(2500); } catch {}
    }
  });

  if (v4 && toGif(v4, join(GIF_OUT, "demo-failure-clustering.gif"))) {
    const sz = Math.round(parseInt(execSync(`stat --format=%s "${join(GIF_OUT, "demo-failure-clustering.gif")}"`).toString()) / 1024);
    results.push(`demo-failure-clustering.gif (${sz}KB)`);
  } else {
    results.push("demo-failure-clustering.gif FAILED");
  }

  // ── 5. Session Comparison ───────────────────────────────────────────
  // FIX: Use .comparison-panel selector, it's in the Inspect tab Analysis section
  console.log("[5/5] Session Comparison...");
  const v5 = await recordDemo(browser, async (page) => {
    await clickSession(page, 0);
    await clickTab(page, "Inspect");
    await page.waitForTimeout(3000);

    // Scroll to the comparison panel in the Analysis section
    const comparisonPanel = page.locator(".comparison-panel").first();
    try {
      await comparisonPanel.scrollIntoViewIfNeeded({ timeout: 5000 });
      await page.waitForTimeout(2000);
    } catch {}

    // Find session dropdown and select a different session
    const dropdown = page.locator(
      ".comparison-panel select, .comparison-panel button[role='combobox']"
    ).first();
    try {
      await dropdown.click();
      await page.waitForTimeout(1500);
      const options = await page.locator("li[role='option'], option").all();
      if (options.length > 1) {
        await options[1].click();
        await page.waitForTimeout(4000);
      }
    } catch {}

    // Scroll back up to show the comparison results
    try {
      await comparisonPanel.scrollIntoViewIfNeeded({ timeout: 3000 });
      await page.waitForTimeout(2000);
    } catch {}
  });

  if (v5 && toGif(v5, join(GIF_OUT, "demo-comparison.gif"))) {
    const sz = Math.round(parseInt(execSync(`stat --format=%s "${join(GIF_OUT, "demo-comparison.gif")}"`).toString()) / 1024);
    results.push(`demo-comparison.gif (${sz}KB)`);
  } else {
    results.push("demo-comparison.gif FAILED");
  }

  await browser.close();

  console.log("\n" + "=".repeat(50));
  console.log("RESULTS:");
  for (const r of results) console.log(`  ${r}`);

  // Cleanup videos
  try {
    for (const f of readdirSync(VIDEOS)) unlinkSync(join(VIDEOS, f));
  } catch {}
}

main().catch((e) => {
  console.error("Failed:", e.message);
  process.exit(1);
});
