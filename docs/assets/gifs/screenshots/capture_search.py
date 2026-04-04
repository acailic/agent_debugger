
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

async def capture_screenshots():
    screenshots_dir = Path("/home/nistrator/Documents/github/amplifier/ai_working/agent_debugger/docs/assets/gifs/screenshots")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        page = await context.new_page()
        
        # Navigate to the app
        await page.goto("http://localhost:3000/ui/")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        # Take initial screenshot
        await page.screenshot(path=str(screenshots_dir / "search_01_initial.png"))
        
        # Find and click on search box
        search_input = page.locator("input[placeholder*='search' i], input[aria-label*='search' i], .search input, #search").first
        if await search_input.count() > 0:
            await search_input.click()
            await asyncio.sleep(0.5)
            await page.screenshot(path=str(screenshots_dir / "search_02_click_search.png"))
            
            # Type search query
            await search_input.type("error", delay=100)
            await asyncio.sleep(1)
            await page.screenshot(path=str(screenshots_dir / "search_03_typing.png"))
            
            # Wait for results
            await asyncio.sleep(2)
            await page.screenshot(path=str(screenshots_dir / "search_04_results.png"))
        else:
            print("Could not find search input")
            # Take a few more screenshots anyway
            await asyncio.sleep(1)
            await page.screenshot(path=str(screenshots_dir / "search_02_nav.png"))
            await asyncio.sleep(1)
            await page.screenshot(path=str(screenshots_dir / "search_03_explore.png"))
        
        await browser.close()
        print(f"Screenshots saved to {screenshots_dir}")

asyncio.run(capture_screenshots())
