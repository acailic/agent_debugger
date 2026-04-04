const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const screenshotsDir = '/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/docs/assets/gifs/screenshots';
  
  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-dev-shm-usage']
  });
  
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 }
  });
  
  const page = await context.newPage();
  
  // Navigate to the app
  await page.goto('http://localhost:3000/ui/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  
  // Take initial screenshot
  await page.screenshot({ path: path.join(screenshotsDir, 'search_01_initial.png') });
  console.log('Captured: search_01_initial.png');
  
  // Try to find and interact with search
  try {
    // Look for search input
    const searchSelectors = [
      'input[placeholder*="search" i]',
      'input[aria-label*="search" i]',
      '.search input',
      '#search',
      '[data-testid="search"]'
    ];
    
    for (const selector of searchSelectors) {
      const count = await page.locator(selector).count();
      if (count > 0) {
        console.log(`Found search input with selector: ${selector}`);
        await page.locator(selector).first().click();
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'search_02_click_search.png') });
        console.log('Captured: search_02_click_search.png');
        
        // Type search query
        await page.locator(selector).first().type('error', { delay: 100 });
        await page.waitForTimeout(1000);
        await page.screenshot({ path: path.join(screenshotsDir, 'search_03_typing.png') });
        console.log('Captured: search_03_typing.png');
        
        // Wait for results
        await page.waitForTimeout(2000);
        await page.screenshot({ path: path.join(screenshotsDir, 'search_04_results.png') });
        console.log('Captured: search_04_results.png');
        break;
      }
    }
  } catch (e) {
    console.log('Search interaction failed:', e.message);
  }
  
  await browser.close();
  console.log('Screenshots captured successfully');
})();
