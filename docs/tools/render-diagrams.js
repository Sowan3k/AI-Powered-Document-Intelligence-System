// Renders every docs/diagrams/*.mmd to a PNG beside it, on white, at 2x.
// From the repository root: node docs/tools/render-diagrams.js .
// Needs: npm install --prefix docs/tools (Playwright with Chromium comes from the machine).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const repo = path.resolve(process.argv[2]);
const dir = path.join(repo, "docs/diagrams");
const here = __dirname;
const fonts = path.join(repo, "frontend/app/fonts");

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 }, deviceScaleFactor: 2 });
  const shell = path.join(require("os").tmpdir(), "docintel-diagram.html");
  fs.writeFileSync(
    shell,
    `<!doctype html><html><head><meta charset="utf-8"><style>
      @font-face { font-family: Plex; src: url("file://${fonts}/ibm-plex-sans-latin-wght-normal.woff2"); font-weight: 100 700; }
      body { margin: 0; background: #fff; font-family: Plex, sans-serif; }
      #box { display: inline-block; padding: 24px; background: #fff; }
    </style><script src="file://${here}/node_modules/mermaid/dist/mermaid.min.js"></script></head>
    <body><div id="box"></div></body></html>`,
  );
  await page.goto("file://" + shell, { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".mmd")).sort()) {
    const source = fs.readFileSync(path.join(dir, file), "utf8");
    await page.evaluate(async (src) => {
      mermaid.initialize({
        startOnLoad: false,
        theme: "base",
        fontFamily: "Plex, sans-serif",
        themeVariables: {
          primaryColor: "#f6f2e9",
          primaryBorderColor: "#0f1b2d",
          primaryTextColor: "#0f1b2d",
          lineColor: "#3b4658",
          secondaryColor: "#fbf8f2",
          tertiaryColor: "#fbf8f2",
          clusterBkg: "#fbf8f2",
          clusterBorder: "#a97a26",
          fontSize: "15px",
        },
        flowchart: { htmlLabels: true, padding: 12, useMaxWidth: false },
        er: { useMaxWidth: false },
      });
      const { svg } = await mermaid.render("d" + Math.random().toString(36).slice(2), src);
      const box = document.getElementById("box");
      box.innerHTML = svg;
      const el = box.querySelector("svg");
      el.style.maxWidth = "none";
    }, source);
    await page.waitForTimeout(200);
    const out = path.join(dir, file.replace(/\.mmd$/, ".png"));
    await page.locator("#box").screenshot({ path: out });
    const size = await page.locator("#box").boundingBox();
    console.log(file, "->", path.basename(out), Math.round(size.width), "x", Math.round(size.height));
  }
  await browser.close();
})();
