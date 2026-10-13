// Copies the MediaPipe face-detection runtime into public/ so the exam loads it
// from our own origin at runtime instead of webpack bundling it or a third-party CDN.
const fs = require('fs');
const path = require('path');

const source = path.join(__dirname, '..', 'node_modules', '@mediapipe', 'tasks-vision');
const target = path.join(__dirname, '..', 'public', 'proctoring', 'vendor');

fs.mkdirSync(path.join(target, 'wasm'), { recursive: true });
for (const file of fs.readdirSync(path.join(source, 'wasm'))) {
  fs.copyFileSync(path.join(source, 'wasm', file), path.join(target, 'wasm', file));
}
// The published bundle references a source map that is not shipped; drop the comment.
const bundle = fs.readFileSync(path.join(source, 'vision_bundle.mjs'), 'utf8')
  .replace(/\n?\/\/# sourceMappingURL=.*$/m, '');
fs.writeFileSync(path.join(target, 'vision_bundle.mjs'), bundle);
