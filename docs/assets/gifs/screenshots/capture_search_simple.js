const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const screenshotsDir = '/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/docs/assets/gifs/screenshots';
  
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-dev-shm-usage', '--no-sandbox']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  
  const page = await context.newPage();
  
  try {
    // Navigate to the app with shorter timeout
    await page.goto('http://localhost:3000/ui/', { timeout: 10000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    
    // Take initial screenshot
    await page.screenshot({ path: path.join(screenshotsDir, 'search_01_initial.png') });
    console.log('Captured: search_01_initial.png');
    
    // Take a few more screenshots showing different states
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, 'search_02_loaded.png') });
    console.log('Captured: search_02_loaded.png');
    
    // Try to click around to show interactivity
    const body = page.locator('body');
    await body.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotsDir, 'search_03_interact.png') });
    console.log('Captured: search_03_interact.png');
    
    await page.waitForTimeout(1000);
    await page.screenshot({ path: path.join(screenshotsDir, 'search_04_final.png') });
    console.log('Captured: search_04_final.png');
    
  } catch (e) {
    console.log('Error during capture:', e.message);
  } finally {
    await browser.close();
    console.log('Capture complete');
  }
})();
