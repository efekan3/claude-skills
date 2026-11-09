// Koersdesk desktop shell: one window that loads the bundled page.
const { app, BrowserWindow, shell, Menu } = require("electron");
const path = require("path");

// One running copy at a time; a second launch focuses the existing window.
if (!app.requestSingleInstanceLock()) app.quit();

let win;
function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 420,
    minHeight: 560,
    title: "Koersdesk",
    backgroundColor: "#0e1215",
    icon: path.join(__dirname, "icon.png"),
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  Menu.setApplicationMenu(null);
  win.loadFile(path.join(__dirname, "app", "index.html"));

  // Links (news articles, sources) open in the default browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (e, url) => {
    if (!url.startsWith("file://")) { e.preventDefault(); if (/^https?:\/\//.test(url)) shell.openExternal(url); }
  });
  // F5 / Ctrl+R reloads, F11 fullscreen, Ctrl +/- zoom.
  win.webContents.on("before-input-event", (e, input) => {
    if (input.type !== "keyDown") return;
    const k = input.key.toLowerCase();
    if (k === "f5" || (input.control && k === "r")) { win.webContents.reload(); e.preventDefault(); }
    if (k === "f11") { win.setFullScreen(!win.isFullScreen()); e.preventDefault(); }
    if (input.control && (k === "=" || k === "+")) { win.webContents.setZoomLevel(win.webContents.getZoomLevel() + 0.5); e.preventDefault(); }
    if (input.control && k === "-") { win.webContents.setZoomLevel(win.webContents.getZoomLevel() - 0.5); e.preventDefault(); }
    if (input.control && k === "0") { win.webContents.setZoomLevel(0); e.preventDefault(); }
  });
}

app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });
app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
