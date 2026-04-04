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
    await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_01_initial.png') });
    console.log('Captured: failure_cluster_01_initial.png');
    
    // Look for failure cluster panel or navigate to analytics
    // Try to find tabs or navigation to analytics
    const analyticsTab = page.locator('button:has-text("Analytics"), [role="tab"]:has-text("Analytics")').first();
    const tabCount = await analyticsTab.count();
    
    if (tabCount > 0) {
      console.log('Found Analytics tab');
      await analyticsTab.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_02_analytics_tab.png') });
      console.log('Captured: failure_cluster_02_analytics_tab.png');
    } else {
      // Look for failure cluster panel directly
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_02_explore.png') });
      console.log('Captured: failure_cluster_02_explore.png');
    }
    
    // Look for failure cluster cards
    const clusterCard = page.locator('.cluster-card, .failure-cluster-panel').first();
    const clusterCount = await clusterCard.count();
    
    if (clusterCount > 0) {
      console.log('Found failure cluster panel');
      
      // Screenshot showing clusters
      await page.waitForTimeout(500);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_03_clusters.png') });
      console.log('Captured: failure_cluster_03_clusters.png');
      
      // Try to click a cluster
      const clickableCluster = page.locator('.cluster-card').first();
      const clickableCount = await clickableCluster.count();
      
      if (clickableCount > 0) {
        // Hover over cluster
        await clickableCluster.hover();
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_04_hover.png') });
        console.log('Captured: failure_cluster_04_hover.png');
        
        // Click the cluster
        await clickableCluster.click();
        await page.waitForTimeout(1000);
        await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_05_clicked.png') });
        console.log('Captured: failure_cluster_05_clicked.png');
      } else {
        await page.waitForTimeout(500);
        await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_04_final.png') });
        console.log('Captured: failure_cluster_04_final.png');
      }
    } else {
      console.log('No failure clusters found, taking general screenshots');
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_03_no_clusters.png') });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(screenshotsDir, 'failure_cluster_04_final.png') });
    }
    
  } catch (e) {
    console.log('Error during capture:', e.message);
  } finally {
    await browser.close();
    console.log('Failure clustering capture complete');
  }
})();
