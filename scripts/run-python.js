const path = require('path');
const { spawn } = require('child_process');
const { findPython } = require('./python-env');

const rootDir = path.resolve(__dirname, '..');
const python = findPython(rootDir);
const scriptArg = process.argv[2];
const passthroughArgs = process.argv.slice(3);

if (!scriptArg) {
  console.error('Usage: node scripts/run-python.js path/to/script.py');
  process.exit(1);
}

if (!python) {
  console.error('\nCould not find a usable Python environment.');
  console.error('Run: npm run setup:backend\n');
  process.exit(1);
}

const scriptPath = path.resolve(rootDir, scriptArg);
console.log(`Running ${scriptArg} with ${python.label}...`);

const child = spawn(python.command, [...python.args, scriptPath, ...passthroughArgs], {
  cwd: rootDir,
  stdio: 'inherit',
  windowsHide: true,
  env: process.env,
});

child.on('exit', (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
