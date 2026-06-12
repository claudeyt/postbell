const fs = require('fs');
const os = require('os');
const electronRequire = require('electron');
fs.writeFileSync(os.tmpdir() + '\electron-shape.txt', 
  'typeof electron: ' + typeof electronRequire + '\n' +
  'value: ' + JSON.stringify(electronRequire) + '\n' +
  'keys: ' + (typeof electronRequire === 'object' ? Object.keys(electronRequire || {}).join(',') : 'N/A')
);
process.exit(0);
