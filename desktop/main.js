const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const { spawn } = require('node:child_process');
const http = require('node:http');
const path = require('node:path');

const LOOPBACK = '127.0.0.1';
const port = Number(process.env.OFFICE_UI_PORT || 8765);
const project = process.env.OFFICE_PROJECT || process.argv.slice(2).find(arg => !arg.startsWith('-')) || process.cwd();
const officeBin = process.env.OFFICE_BIN || 'office';
let child = null;
let mainWindow = null;


function installPickerHandlers() {
  ipcMain.handle('office:choose-project-folder', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openDirectory'] });
    return result.canceled ? null : (result.filePaths[0] || null);
  });
  ipcMain.handle('office:choose-files', async () => {
    const result = await dialog.showOpenDialog(mainWindow, { properties: ['openFile', 'multiSelections'] });
    return result.canceled ? [] : result.filePaths;
  });
  ipcMain.handle('office:choose-archive', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openFile'],
      filters: [{ name: 'Project archives', extensions: ['zip', 'tar', 'tgz', 'gz', 'tbz2', 'bz2', 'txz', 'xz'] }],
    });
    return result.canceled ? null : (result.filePaths[0] || null);
  });
}

function startOfficeServer() {
  child = spawn(officeBin, ['ui', project, '--host', LOOPBACK, '--port', String(port), '--no-open'], {
    cwd: project,
    env: process.env,
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });
  child.stdout.on('data', data => process.stdout.write(data));
  child.stderr.on('data', data => process.stderr.write(data));
  child.on('exit', code => {
    if (!app.isQuitting && code && code !== 0) console.error(`Engineering Office UI exited with code ${code}`);
  });
}

function healthReady() {
  return new Promise(resolve => {
    const req = http.get(`http://${LOOPBACK}:${port}/api/health`, res => {
      res.resume();
      resolve(res.statusCode === 200);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(700, () => { req.destroy(); resolve(false); });
  });
}

async function waitForOffice() {
  for (let i = 0; i < 80; i += 1) {
    if (await healthReady()) return true;
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  return false;
}

async function createWindow() {
  const ok = await waitForOffice();
  if (!ok) throw new Error('Engineering Office local UI did not become ready.');
  mainWindow = new BrowserWindow({
    width: 1540,
    height: 930,
    minWidth: 1080,
    minHeight: 700,
    title: 'Engineering Office',
    backgroundColor: '#18101c',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  const localPrefix = `http://${LOOPBACK}:${port}`;
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith(localPrefix)) return { action: 'allow' };
    return { action: 'deny' };
  });
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(localPrefix)) event.preventDefault();
  });
  await mainWindow.loadURL(localPrefix);
}

function stopServer() {
  if (child && !child.killed) {
    child.kill('SIGTERM');
    child = null;
  }
}

app.whenReady().then(async () => {
  installPickerHandlers();
  startOfficeServer();
  try {
    await createWindow();
  } catch (error) {
    console.error(error);
    stopServer();
    app.quit();
  }
});

app.on('before-quit', () => { app.isQuitting = true; stopServer(); });
app.on('window-all-closed', () => { stopServer(); app.quit(); });
