// Regenerates docs/screenshots from the demo vault. See AGENTS.md.
// Usage: node tools/screenshots.cjs <url printed by `bw_dedupe.py --demo --no-browser`> <output dir>
const { chromium } = require("playwright");

(async () => {
const [url, out] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 760 }, deviceScaleFactor: 2, colorScheme: "light" });
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` });

await page.goto(url);
// The README shows the screens as users see them, without the demo badge.
await page.addStyleTag({ content: ".tag.demo { display: none !important; }" });
await page.waitForSelector(".row");
await page.click('.row:has-text("amazon.fr")');
await shot("review-rule");

await page.click('.row:has-text("steampowered.com")');
await page.click('.seg button:has-text("Merge")');
await page.check('tr:has-text("Steam help") input[type=radio]');
await page.waitForTimeout(500);
await page.locator(".card").nth(1).scrollIntoViewIfNeeded();
await page.evaluate(() => { document.querySelector(".detail").scrollTop = 0; });
await shot("review-conflict");
await page.click('.actions button:text-is("Validate")');

await page.click('.chip:has-text("To review")');
for (const name of ["amazon.fr", "github.com", "dropbox.com"]) {
  await page.click(`.row:has-text("${name}")`);
  await page.click('.actions button:text-is("Validate")');
  await page.waitForTimeout(300);
}
await page.click('button:has-text("Apply validated")');
await page.uncheck(".modal input[type=checkbox]");
await page.click('.modal button:text-is("Apply")');
await page.waitForSelector("text=Finished", { timeout: 20000 });
const [report] = await Promise.all([page.context().waitForEvent("page"), page.click('button:has-text("Open the report")')]);
await report.setViewportSize({ width: 1100, height: 900 });
await report.waitForLoadState();
await report.screenshot({ path: `${out}/report.png` });
await browser.close();
})();
