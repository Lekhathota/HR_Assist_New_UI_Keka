const path = require('path');
const { spawn } = require('child_process');
const { findPython } = require('./python-env');

const rootDir = path.resolve(__dirname, '..');
const backendDir = path.join(rootDir, 'backend');
const python = findPython(rootDir);

if (!python) {
  console.error('\nCould not find a usable Python for the Flask backend.\n');
  console.error('Fix steps:');
  console.error('  1. Install Python from python.org and tick "Add python.exe to PATH".');
  console.error('  2. Reopen VS Code.');
  console.error('  3. Run: npm run setup:backend');
  console.error('  4. Run: npm run dev');
  process.exit(1);
}

console.log(`Starting Flask API with ${python.label}...`);

const child = spawn(python.command, [...python.args, 'app.py'], {
  cwd: backendDir,
  stdio: 'inherit',
  windowsHide: true,
  env: {
    ...process.env,
    RA_AUTO_START_FRONTEND: 'false',
  },
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
