// Optional browser integration check. Start a permissioned H.264 RTSP publisher first.
const assert = require("node:assert/strict");
const { performance } = require("node:perf_hooks");
const { chromium } = require(process.env.ASTRA_PLAYWRIGHT_MODULE || "playwright");

async function main() {
  const executablePath = process.env.ASTRA_BROWSER_EXECUTABLE;
  const browser = await chromium.launch(executablePath ? { executablePath } : {});
  try {
    for (const [transport, port] of [["WebRTC", 8889], ["HLS", 8888]]) {
      const page = await browser.newPage();
      await page.addInitScript(() => {
        const play = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function () {
          this.muted = true;
          return play.call(this);
        };
      });
      try {
        const start = performance.now();
        const response = await page.goto(`http://127.0.0.1:${port}/monitor/`);
        assert(response?.ok(), `${transport} player did not load`);
        await page.waitForFunction(() => {
          const video = document.querySelector("video");
          return video && video.videoWidth > 0 && video.currentTime > 0;
        }, null, { timeout: 18000 });
        console.log(`${transport}: ${(performance.now() - start).toFixed(1)} ms from navigation to advancing decoded video`);
      } finally {
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
