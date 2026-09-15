const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const rootDir = path.resolve(__dirname, '..');
const venvDir = path.join(rootDir, '.venv');
const venvPython = path.join(venvDir, 'Scripts', 'python.exe');
const requirements = path.join(rootDir, 'backend', 'requirements.txt');
const activeVenvPython = process.env.VIRTUAL_ENV
  ? path.join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe')
  : null;

const candidates = [
  { command: 'py', args: ['-3'], label: 'Python launcher' },
  { command: 'python', args: [], label: 'PATH python' },
];

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: rootDir,
    stdio: 'inherit',
    windowsHide: true,
    ...options,
  });
  if (result.error || result.status !== 0) {
    throw result.error || new Error(`${command} ${args.join(' ')} failed`);
  }
}

function canRun(candidate) {
  const result = spawnSync(candidate.command, [...candidate.args, '--version'], {
    cwd: rootDir,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 8000,
  });
  return !result.error && result.status === 0;
}

const python = candidates.find(canRun);

if (!python) {
  if (activeVenvPython && fs.existsSync(activeVenvPython)) {
    console.log('Using active virtualenv to install backend requirements...');
    run(activeVenvPython, ['-m', 'pip', 'install', '--upgrade', 'pip']);
    run(activeVenvPython, ['-m', 'pip', 'install', '-r', requirements]);
    console.log('\nBackend setup complete. Run: npm run dev\n');
    process.exit(0);
  }

  console.error('\nCould not find Python.');
  console.error('Install Python from python.org, tick "Add python.exe to PATH", reopen VS Code, then run this again.\n');
  process.exit(1);
}

if (fs.existsSync(venvDir)) {
  console.log('Removing old .venv...');
  fs.rmSync(venvDir, { recursive: true, force: true });
}

console.log(`Creating .venv with ${python.label}...`);
run(python.command, [...python.args, '-m', 'venv', '.venv']);

console.log('Upgrading pip...');
run(venvPython, ['-m', 'pip', 'install', '--upgrade', 'pip']);

console.log('Installing backend requirements...');
run(venvPython, ['-m', 'pip', 'install', '-r', requirements]);

console.log('\nBackend setup complete. Run: npm run dev\n');
