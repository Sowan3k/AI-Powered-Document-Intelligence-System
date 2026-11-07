// Builds docs/DocIntel-Deliverables.pdf from docs/DELIVERABLES.md.
// From the repository root: node docs/tools/build-pdf.js .
// Needs: npm install --prefix docs/tools (Playwright with Chromium comes from the machine).
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const repo = path.resolve(process.argv[2]);
const docs = path.join(repo, "docs");
const here = __dirname;
const GH = "https://github.com/Sowan3k/AI-Powered-Document-Intelligence-System/blob/main/";
const fonts = path.join(repo, "frontend/app/fonts");
const md = fs.readFileSync(path.join(docs, "DELIVERABLES.md"), "utf8");

const css = `
@font-face { font-family: Plex; src: url("file://${fonts}/ibm-plex-sans-latin-wght-normal.woff2"); font-weight: 100 700; }
@font-face { font-family: Barlow; src: url("file://${fonts}/barlow-semi-condensed-latin-700-normal.woff2"); font-weight: 700; }
@font-face { font-family: Barlow; src: url("file://${fonts}/barlow-semi-condensed-latin-600-normal.woff2"); font-weight: 600; }
@font-face { font-family: PlexMono; src: url("file://${fonts}/ibm-plex-mono-latin-400-normal.woff2"); }
@page { size: A4; margin: 16mm 15mm 18mm; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: Plex, sans-serif; font-size: 9.6pt; line-height: 1.5; color: #0f1b2d; margin: 0; }
h1 { font-family: Barlow; font-weight: 700; font-size: 26pt; line-height: 1.1; margin: 0 0 4pt; letter-spacing: -0.2pt; }
h1 + p { color: #5b6472; margin-top: 0; }
h2 { font-family: Barlow; font-weight: 700; font-size: 15pt; margin: 14pt 0 6pt; padding-top: 6pt; border-top: 1.5pt solid #0f1b2d; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: #0f1b2d; text-decoration: underline; text-decoration-color: #a97a26; text-underline-offset: 2pt; }
code { font-family: PlexMono, monospace; font-size: 8.4pt; background: #f1ece1; padding: 0.5pt 3pt; border-radius: 3pt; }
pre { background: #f6f2e9; border: 0.6pt solid #e2dccd; border-radius: 5pt; padding: 7pt 9pt; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.2pt; }
table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt; font-size: 8.8pt; }
thead { display: table-header-group; }
tr:first-child { break-before: avoid; }
th, td { text-align: left; vertical-align: top; padding: 4pt 6pt; border-bottom: 0.6pt solid #e2dccd; }
th { font-family: Barlow; font-weight: 600; font-size: 9.2pt; border-bottom: 1pt solid #0f1b2d; }
tr { break-inside: avoid; }
table.links td:first-child { width: 28%; font-weight: 600; }
table.links th { display: none; }
.keep { break-inside: avoid; }
.mermaid { display: flex; justify-content: center; margin: 8pt 0 10pt; break-inside: avoid; }
.mermaid svg { max-width: 100%; height: auto; max-height: 300pt; }
img[src*="diagrams/"] { display: block; margin: 4pt auto 8pt; max-width: 100%; max-height: 330pt; }
img[src*="schema-overview"] { max-height: 200pt; }
table.shots { break-inside: avoid; }
table.shots td { width: 25%; padding: 3pt; border: none; }
table.shots th { border: none; text-align: center; }
table.shots img { width: 100%; max-height: 180pt; object-fit: contain; border: 0.6pt solid #d8d1c2; border-radius: 6pt; }
ul { padding-left: 14pt; }
strong { font-weight: 650; }
`;

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const shell = path.join(require("os").tmpdir(), "docintel-pdf.html");
  fs.writeFileSync(
    shell,
    `<!doctype html><html><head><meta charset="utf-8"><base href="file://${docs}/"><style>${css}</style>
     <script src="file://${here}/node_modules/marked/lib/marked.umd.js"></script>
     <script src="file://${here}/node_modules/mermaid/dist/mermaid.min.js"></script></head>
     <body><main id="doc"></main></body></html>`,
  );
  await page.goto("file://" + shell, { waitUntil: "load" });
  await page.evaluate(
    async ({ md, GH }) => {
      const renderer = new marked.Renderer();
      const code = renderer.code.bind(renderer);
      renderer.code = (token) =>
        token.lang === "mermaid" ? `<div class="mermaid">${token.text}</div>` : code(token);
      const main = document.getElementById("doc");
      main.innerHTML = marked.parse(md, { renderer });
      // Links that point inside the repository go to GitHub, since a PDF has no folder around it.
      for (const a of main.querySelectorAll("a[href]")) {
        const href = a.getAttribute("href");
        if (/^(https?:|mailto:|#)/.test(href)) continue;
        a.href = href.startsWith("../") ? GH + href.slice(3) : GH + "docs/" + href;
      }
      const tables = main.querySelectorAll("table");
      tables[0].classList.add("links");
      for (const t of tables) if (t.querySelector("img")) t.classList.add("shots");
      // Keep a heading, and a line ending in a colon, on the same page as the block after it.
      const block = (el) => el && (el.matches("table, pre, .mermaid, ul") || !!el.querySelector("img"));
      const keep = (start, stopAtBlock) => {
        const group = [start];
        let el = start.nextElementSibling;
        while (el && !el.matches("h2")) {
          group.push(el);
          // A table can be long: keep the heading with its intro text only,
          // and let the table itself flow onto the next page.
          const leadIn = el.matches("p") && el.textContent.trim().endsWith(":");
          if (stopAtBlock(el) || (group.length >= 2 && !leadIn) || group.length >= 3) break;
          el = el.nextElementSibling;
        }
        // Tables always flow: the heading and lead-in hold on to the first row only.
        if (group.length > 1 && group[group.length - 1].matches("table")) {
          group.pop();
          group[group.length - 1].style.breakAfter = "avoid";
        }
        if (group.length < 2) return;
        const wrap = document.createElement("div");
        wrap.className = "keep";
        start.before(wrap);
        group.forEach((g) => wrap.appendChild(g));
      };
      for (const h of [...main.querySelectorAll("h2")]) keep(h, block);
      for (const para of [...main.querySelectorAll("p")]) {
        if (para.closest(".keep")) continue;
        if (para.textContent.trim().endsWith(":") && block(para.nextElementSibling)) keep(para, block);
      }
      mermaid.initialize({ startOnLoad: false, theme: "neutral", fontFamily: "Plex, sans-serif", flowchart: { htmlLabels: true } });
      await mermaid.run({ querySelector: ".mermaid" });
    },
    { md, GH },
  );
  await page.waitForFunction(() => [...document.images].every((i) => i.complete && i.naturalWidth > 0));
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: path.join(docs, "DocIntel-Deliverables.pdf"),
    format: "A4",
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: "<span></span>",
    footerTemplate:
      '<div style="width:100%;font-size:7.5pt;color:#7a8291;padding:0 15mm;display:flex;justify-content:space-between;font-family:sans-serif"><span>DocIntel: submission deliverables</span><span><span class="pageNumber"></span> of <span class="totalPages"></span></span></div>',
    margin: { top: "16mm", bottom: "18mm", left: "15mm", right: "15mm" },
  });
  await browser.close();
  console.log("wrote", path.join(docs, "DocIntel-Deliverables.pdf"));
})();
