// Pure-Node migration helpers, factored out of main.js so they can be unit
// tested under plain `node` without booting Electron.
//
// `migrateLegacyData` recursively copies everything from `legacyPath` into
// `userDataPath`, with two important guarantees:
//   1. Existing files in userData are NEVER overwritten (force: false). If
//      the user has already started the Electron app and modified state, we
//      preserve their state intact.
//   2. The `temp/` subtree and any `__pycache__` directories are skipped —
//      these are transient and would just bloat the user's per-app data dir.
//
// Uses Node 16+ `fs.cpSync` (synchronous) so callers can run it as part of a
// startup sequence without async plumbing.

const fs = require('node:fs');
const path = require('node:path');

function migrateLegacyData(legacyPath, userDataPath) {
  fs.cpSync(legacyPath, userDataPath, {
    recursive: true,
    force: false, // don't overwrite existing files in userData
    errorOnExist: false, // skip silently if dest exists
    filter: (src) => {
      const rel = path.relative(legacyPath, src);
      // Skip temp/ entirely (transient — user can re-download if needed)
      // and any stray __pycache__ dirs left behind by the legacy dev install.
      if (rel === 'temp' || rel.startsWith('temp' + path.sep)) return false;
      if (rel.split(path.sep).includes('__pycache__')) return false;
      return true;
    },
  });
}

module.exports = { migrateLegacyData };
