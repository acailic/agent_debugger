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
    // Navigate to the app
    await page.goto('http://localhost:3000/ui/', { timeout: 15000, waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(3000);
    
    // Screenshot 1: Initial state
    await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_01_initial.png') });
    console.log('Captured: trace_search_01_initial.png');
    
    // Find and click on search input (id="search-input")
    const searchInput = page.locator('#search-input');
    const count = await searchInput.count();
    
    if (count > 0) {
      console.log('Found search input');
      
      // Click on search input
      await searchInput.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_02_click.png') });
      console.log('Captured: trace_search_02_click.png');
      
      // Type search query slowly
      await searchInput.type('error', { delay: 150 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_03_typing.png') });
      console.log('Captured: trace_search_03_typing.png');
      
      // Press Enter to search
      await searchInput.press('Enter');
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_04_results.png') });
      console.log('Captured: trace_search_04_results.png');
      
      // Try to click a search result
      const firstResult = page.locator('.search-result').first();
      const resultCount = await firstResult.count();
      
      if (resultCount > 0) {
        await firstResult.click();
        await page.waitForTimeout(1000);
        await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_05_clicked.png') });
        console.log('Captured: trace_search_05_clicked.png');
      } else {
        // Take one more shot of the results
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_05_final.png') });
        console.log('Captured: trace_search_05_final.png');
      }
    } else {
      console.log('Search input not found, taking general screenshots');
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_02_explore.png') });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'trace_search_03_final.png') });
    }
    
  } catch (e) {
    console.log('Error during capture:', e.message);
  } finally {
    await browser.close();
    console.log('Trace search capture complete');
  }
})();
