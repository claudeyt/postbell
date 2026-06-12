// Headless test for the first-run data migration helper.
//
// Verifies, without booting Electron:
//   1. Happy path  - fresh userData receives the legacy data minus temp/.
//   2. Idempotency - existing files in userData are NOT overwritten.
//
// Exits 0 on success, nonzero on any assertion failure with a clear message.
// Always cleans the .scratch/ tree, even on failure, so re-runs are clean.

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const { migrateLegacyData } = require('..' + path.sep + 'migration');

const SCRATCH = path.resolve(__dirname, '..', '.scratch');
const LEGACY = path.join(SCRATCH, 'legacy-src');
const DEST_EMPTY = path.join(SCRATCH, 'dest-empty');
const DEST_PARTIAL = path.join(SCRATCH, 'dest-partial');

let failed = false;
const fail = (msg) => {
  failed = true;
  console.error('FAIL:', msg);
};
const ok = (msg) => console.log('PASS:', msg);

function rmrf(p) {
  if (fs.existsSync(p)) fs.rmSync(p, { recursive: true, force: true });
}

function writeFile(p, contents) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, contents);
}

function setupLegacy() {
  rmrf(LEGACY);
  // Mimics the real layout the task spec calls out: postbell.db, an OAuth
  // token file, a big temp/ blob that must NOT be copied, and settings.json.
  writeFile(path.join(LEGACY, 'postbell.db'), 'LEGACY_DB_CONTENTS_v1');
  writeFile(
    path.join(LEGACY, 'oauth_tokens', 'raijin.json'),
    JSON.stringify({ access_token: 'legacy-token', channel: 'raijin' }),
  );
  // 1 MiB placeholder to stand in for a transient temp video file.
  writeFile(path.join(LEGACY, 'temp', 'big.mp4'), Buffer.alloc(1024 * 1024, 0));
  writeFile(
    path.join(LEGACY, 'settings.json'),
    JSON.stringify({ language: 'pt-BR', theme: 'dark' }),
  );
  // Stray __pycache__ that must also be skipped.
  writeFile(path.join(LEGACY, 'scripts', '__pycache__', 'foo.pyc'), 'PYC');
  writeFile(path.join(LEGACY, 'scripts', 'real.py'), 'print("hi")');
}

function testHappyPath() {
  console.log('\n--- Test 1: happy path (empty destination) ---');
  rmrf(DEST_EMPTY);
  fs.mkdirSync(DEST_EMPTY, { recursive: true });

  migrateLegacyData(LEGACY, DEST_EMPTY);

  // Required files present.
  const dbPath = path.join(DEST_EMPTY, 'postbell.db');
  if (!fs.existsSync(dbPath)) fail('postbell.db not copied');
  else ok('postbell.db copied');

  const dbContent = fs.readFileSync(dbPath, 'utf8');
  if (dbContent !== 'LEGACY_DB_CONTENTS_v1') {
    fail(`postbell.db content mismatch: got "${dbContent}"`);
  } else ok('postbell.db content matches legacy');

  const tokenPath = path.join(DEST_EMPTY, 'oauth_tokens', 'raijin.json');
  if (!fs.existsSync(tokenPath)) fail('oauth_tokens/raijin.json not copied');
  else ok('oauth_tokens/raijin.json copied');

  const settingsPath = path.join(DEST_EMPTY, 'settings.json');
  if (!fs.existsSync(settingsPath)) fail('settings.json not copied');
  else ok('settings.json copied');

  // Forbidden: temp/ subtree must be absent entirely.
  const tempBig = path.join(DEST_EMPTY, 'temp', 'big.mp4');
  if (fs.existsSync(tempBig)) {
    fail('temp/big.mp4 was copied but should have been skipped');
  } else ok('temp/big.mp4 skipped');

  const tempDir = path.join(DEST_EMPTY, 'temp');
  if (fs.existsSync(tempDir)) {
    fail('temp/ dir was created in destination');
  } else ok('temp/ dir not created in destination');

  // Forbidden: __pycache__ must be skipped.
  const pyc = path.join(DEST_EMPTY, 'scripts', '__pycache__', 'foo.pyc');
  if (fs.existsSync(pyc)) {
    fail('scripts/__pycache__/foo.pyc was copied but should have been skipped');
  } else ok('scripts/__pycache__ skipped');

  // But non-pycache scripts/ contents should be copied (parent dir survives).
  const realPy = path.join(DEST_EMPTY, 'scripts', 'real.py');
  if (!fs.existsSync(realPy)) fail('scripts/real.py not copied');
  else ok('scripts/real.py copied');
}

function testIdempotency() {
  console.log('\n--- Test 2: idempotency (existing files preserved) ---');
  rmrf(DEST_PARTIAL);
  fs.mkdirSync(DEST_PARTIAL, { recursive: true });
  // User has already used the app: their postbell.db has new state we must
  // not stomp on.
  const userDb = 'USER_MODIFIED_DB_v2';
  writeFile(path.join(DEST_PARTIAL, 'postbell.db'), userDb);

  migrateLegacyData(LEGACY, DEST_PARTIAL);

  // postbell.db must still be the user's version.
  const dbContent = fs.readFileSync(
    path.join(DEST_PARTIAL, 'postbell.db'),
    'utf8',
  );
  if (dbContent !== userDb) {
    fail(
      `postbell.db was overwritten: expected "${userDb}", got "${dbContent}"`,
    );
  } else ok('existing postbell.db preserved (not overwritten)');

  // But new files that didn't exist in userData should still be filled in.
  const tokenPath = path.join(DEST_PARTIAL, 'oauth_tokens', 'raijin.json');
  if (!fs.existsSync(tokenPath)) {
    fail('oauth_tokens/raijin.json missing — partial-dest fill-in failed');
  } else ok('oauth_tokens/raijin.json copied alongside existing db');

  const settingsPath = path.join(DEST_PARTIAL, 'settings.json');
  if (!fs.existsSync(settingsPath)) fail('settings.json missing');
  else ok('settings.json copied alongside existing db');
}

function main() {
  try {
    setupLegacy();
    testHappyPath();
    testIdempotency();
  } catch (err) {
    fail(`unexpected exception: ${err && err.stack ? err.stack : err}`);
  } finally {
    // Always tidy up so re-runs start clean.
    rmrf(SCRATCH);
    console.log('\nCleaned up .scratch/');
  }

  if (failed) {
    console.error('\nRESULT: FAILURE');
    process.exit(1);
  } else {
    console.log('\nRESULT: ALL PASSED');
    process.exit(0);
  }
}

main();
