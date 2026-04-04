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
    
    // Screenshot 1: Initial state showing sessions list
    await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_01_sessions.png') });
    console.log('Captured: failure_cluster_01_sessions.png');
    
    // Click on Analytics tab
    const analyticsTab = page.locator('button:has-text("Analytics")').first();
    const tabCount = await analyticsTab.count();
    
    if (tabCount > 0) {
      console.log('Clicking Analytics tab');
      await analyticsTab.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_02_analytics.png') });
      console.log('Captured: failure_cluster_02_analytics.png');
      
      // Scroll to show failure clustering panel
      await page.evaluate(() => window.scrollBy(0, 300));
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_03_scrolled.png') });
      console.log('Captured: failure_cluster_03_scrolled.png');
      
      // Look for failure cluster section or related analytics
      const failurePanel = page.locator('.failure-cluster-panel, text=Failure Clusters').first();
      const panelCount = await failurePanel.count();
      
      if (panelCount > 0) {
        console.log('Found Failure Clusters section');
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_04_panel.png') });
        console.log('Captured: failure_cluster_04_panel.png');
      } else {
        // Take a final shot of the analytics view
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_04_analytics_view.png') });
        console.log('Captured: failure_cluster_04_analytics_view.png');
      }
    } else {
      console.log('No Analytics tab found, taking general screenshots');
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_02_explore.png') });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_03_final.png') });
    }
    
    // Final screenshot
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_05_final.png') });
    console.log('Captured: failure_cluster_05_final.png');
    
  } catch (e) {
    console.log('Error during capture:', e.message);
  } finally {
    await browser.close();
    console.log('Failure clustering capture complete');
  }
})();
