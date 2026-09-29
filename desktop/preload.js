const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('engineeringOfficeDesktop', Object.freeze({
  platform: process.platform,
  shell: 'electron-local-loopback',
  chooseProjectFolder: () => ipcRenderer.invoke('office:choose-project-folder'),
  chooseFiles: () => ipcRenderer.invoke('office:choose-files'),
  chooseArchive: () => ipcRenderer.invoke('office:choose-archive'),
}));
