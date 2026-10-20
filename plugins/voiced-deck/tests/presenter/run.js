'use strict';
// Runs every presenter test in order and exits non-zero if any failed.
const { spawnSync } = require('child_process');
const path = require('path');
const tests = ['sweep.test.js', 'voice.test.js', 'blocked.test.js', 'loader.test.js'];
let failed = 0;
for (const t of tests) {
  console.log(`\n# ${t}`);
  const r = spawnSync(process.execPath, [path.join(__dirname, t)], { stdio: 'inherit' });
  if (r.status !== 0) failed++;
}
console.log(`\n${tests.length - failed}/${tests.length} presenter test files passed`);
process.exit(failed ? 1 : 0);
