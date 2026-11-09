// Builds dist/Koersdesk-win32-x64 (a folder with Koersdesk.exe) from ../index.html.
const fs = require("fs");
const path = require("path");
const { packager } = require("@electron/packager");

const here = __dirname;
const appDir = path.join(here, "app");
fs.mkdirSync(appDir, { recursive: true });

// Bundle the chart library locally so charts never depend on a CDN.
const lib = path.join(here, "node_modules", "lightweight-charts", "dist", "lightweight-charts.standalone.production.js");
fs.copyFileSync(lib, path.join(appDir, "lightweight-charts.js"));
const html = fs.readFileSync(path.join(here, "..", "index.html"), "utf8")
  .replace(/<script src="https:\/\/cdn\.jsdelivr\.net\/npm\/lightweight-charts@[^"]+"><\/script>/, '<script src="lightweight-charts.js"></script>');
if (!html.includes('src="lightweight-charts.js"')) throw new Error("chart library tag not found in index.html");
fs.writeFileSync(path.join(appDir, "index.html"), html);
fs.rmSync(path.join(appDir, "vendor"), { recursive: true, force: true });

(async () => {
  const out = await packager({
    dir: here,
    name: "Koersdesk",
    executableName: "Koersdesk",
    platform: "win32",
    arch: "x64",
    out: path.join(here, "dist"),
    overwrite: true,
    asar: true,
    prune: true,
    ignore: [/^\/dist($|\/)/, /^\/build\.js$/, /^\/README\.md$/],
    appCopyright: "Koersdesk",
    win32metadata: { CompanyName: "Koersdesk", ProductName: "Koersdesk", FileDescription: "Koersdesk" },
  });
  console.log("Built:", out.join(", "));
})().catch(e => { console.error(e); process.exit(1); });
