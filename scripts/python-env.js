const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

function pythonCandidates(rootDir) {
  const backendDir = path.join(rootDir, 'backend');
  const workspaceDir = path.resolve(rootDir, '..', '..');
  const activeVenvPython = process.env.VIRTUAL_ENV
    ? path.join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe')
    : null;

  return [
    activeVenvPython && {
      label: 'active virtualenv',
      command: activeVenvPython,
      args: [],
    },
    {
      label: 'backend virtualenv',
      command: path.join(backendDir, '.venv', 'Scripts', 'python.exe'),
      args: [],
    },
    {
      label: 'project virtualenv',
      command: path.join(rootDir, '.venv', 'Scripts', 'python.exe'),
      args: [],
    },
    {
      label: 'workspace virtualenv',
      command: path.join(workspaceDir, '.venv', 'Scripts', 'python.exe'),
      args: [],
    },
    {
      label: 'Python launcher',
      command: 'py',
      args: ['-3'],
    },
    {
      label: 'PATH python',
      command: 'python',
      args: [],
    },
  ].filter(Boolean);
}

function canRun(candidate, rootDir) {
  if (candidate.command.endsWith('.exe') && !fs.existsSync(candidate.command)) {
    return false;
  }

  const check = spawnSync(candidate.command, [...candidate.args, '--version'], {
    cwd: rootDir,
    encoding: 'utf8',
    windowsHide: true,
    timeout: 8000,
  });

  return !check.error && check.status === 0;
}

function findPython(rootDir) {
  return pythonCandidates(rootDir).find((candidate) => canRun(candidate, rootDir));
}

module.exports = { findPython };
