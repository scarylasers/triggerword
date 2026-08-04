# Sample Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop TriggerWord deleting the user's soundpack, add a single backup file, and level all sounds so none startle the listener.

**Architecture:** Extract the persistence and levelling logic out of `index.html` into a new ES module `persistence.js` containing **pure functions only** — no DOM, no `localStorage`, no `indexedDB`, no `AudioContext`. Storage and DB are passed in by the caller. `index.html` keeps all the I/O and calls into the module. That makes the logic testable under Node with zero browser mocking.

**Tech Stack:** Vanilla ES modules, `node:test` + `node:assert` (built into Node 24 — no npm install, no `node_modules`), JSZip 3.10.1 (already loaded from CDN in `index.html`).

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-03-sample-library-design.md`.
- **The governing principle, from spec §4:** *a failure never destroys data.* On error: keep what exists, tell the user, offer a retry. Deletion happens only at explicit user request. Every task is subordinate to this.
- **There is no existing test suite.** Baseline is zero tests. Every test you add must pass. Run with: `cd C:\Projects\PycharmProjects\TriggerWord && node --test`
- **`persistence.js` must contain no DOM, `localStorage`, `indexedDB`, `AudioContext`, `window` or `document` references.** Callers inject what it needs. This is what makes it testable — violating it defeats the whole plan.
- **Never assign `innerHTML`.** Use `textContent` and `document.createElement`. This applies to every UI step below.
- **Do not restructure `index.html`** beyond removing the code that moves into `persistence.js` and adding the calls. It is 458 KB; leave the rest alone.
- **Do not change the storage architecture.** Blobs in IndexedDB, metadata in localStorage stays (spec §7).
- Levelling constants, exact: `targetRMS` = **−20 dBFS** (`0.1` linear), `peakCeiling` = **−1 dBFS** (`0.8912509381337456` linear), manual trim range **−12 dB to +12 dB**, default `0`.
- Existing IndexedDB helpers in `index.html` — do not duplicate: `saveAudioToDB(blobKey, file)`, `getAudioFromDB(blobKey)`, `removeAudioFromDB(blobKey)`, `deleteAudioFromDBByTrigger(trigger)`. DB name `TriggerAudioDB`, version 1, object store `audio`.
- localStorage keys in use: `triggers`, `lastZipData`, `lastZipImport`, `globalSettings`, `keyboardShortcuts`, `controlShortcuts`, `favoriteTriggers`, `masterVolume`, `selectedInputDevice`, `selectedOutputDevice`.

---

## File Structure

| File | Responsibility |
|---|---|
| `package.json` | **New.** Only `{"type": "module"}` so Node treats `.js` as ESM. No dependencies. |
| `persistence.js` | **New.** Pure functions: retention policy, safe save/load decisions, backup manifest build/parse, orphan detection, levelling maths. |
| `test/persistence.test.js` | **New.** `node:test` suite. |
| `index.html` | **Modified.** Import the module; delete the four destructive paths; add the error banner, backup buttons, orphan report, gain application and trim slider. |

---

### Task 1: Test harness and the retention policy

The 7-day expiry (spec §2 item 1) is the single most damaging bug. This task removes it by replacing the whole decision with an explicit, tested policy function.

**Files:**
- Create: `package.json`, `persistence.js`, `test/persistence.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `shouldAutoLoad(stored) -> {load: boolean, reason: string}` where `stored` is the parsed `lastZipData` object or `null`.

- [ ] **Step 1: Write the failing test**

```javascript
// test/persistence.test.js
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldAutoLoad } from '../persistence.js';

test('loads a stored pack regardless of age', () => {
  const tenYearsAgo = Date.now() - 3650 * 24 * 60 * 60 * 1000;
  const stored = { triggers: [{ word: 'hi', sounds: [] }], timestamp: tenYearsAgo };
  assert.equal(shouldAutoLoad(stored).load, true);
});

test('does not load when there is nothing stored', () => {
  const result = shouldAutoLoad(null);
  assert.equal(result.load, false);
  assert.match(result.reason, /nothing stored/i);
});

test('does not load when the stored record has no triggers', () => {
  const result = shouldAutoLoad({ triggers: [], timestamp: Date.now() });
  assert.equal(result.load, false);
  assert.match(result.reason, /no triggers/i);
});

test('does not load when triggers is missing entirely', () => {
  const result = shouldAutoLoad({ timestamp: Date.now() });
  assert.equal(result.load, false);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Projects\PycharmProjects\TriggerWord && node --test`
Expected: FAIL — `Cannot find module '../persistence.js'`

- [ ] **Step 3: Write minimal implementation**

Create `package.json`:

```json
{
  "type": "module"
}
```

Create `persistence.js`:

```javascript
// Pure persistence + levelling logic for TriggerWord.
//
// NO DOM, NO localStorage, NO indexedDB, NO AudioContext in this file.
// Callers inject what they need. That is what makes it testable under Node.

/**
 * Decide whether a stored pack should be auto-loaded.
 *
 * There is deliberately NO expiry. The previous code deleted the user's
 * soundpack after 7 days of not opening the app, which is the bug this
 * module exists to prevent.
 */
export function shouldAutoLoad(stored) {
  if (!stored) {
    return { load: false, reason: 'nothing stored' };
  }
  if (!Array.isArray(stored.triggers) || stored.triggers.length === 0) {
    return { load: false, reason: 'stored record has no triggers' };
  }
  return { load: true, reason: `${stored.triggers.length} triggers stored` };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: 4 passing

- [ ] **Step 5: Commit**

```bash
git add package.json persistence.js test/persistence.test.js
git commit -m "feat(persistence): retention policy with no expiry"
```

---

### Task 2: Non-destructive save decisions

Spec §2 item 3: the save fallback overwrote a good record with one where every sound was `type: 'missing_blob'`. This task makes that impossible.

**Files:**
- Modify: `persistence.js`, `test/persistence.test.js`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `planSave(triggers, storedBlobKeys) -> {record, failures}` and `chooseRecordToPersist(newRecord, previousRecord, failures) -> {record, warning}`.

- [ ] **Step 1: Write the failing test**

```javascript
// append to test/persistence.test.js
import { planSave, chooseRecordToPersist } from '../persistence.js';

const TRIGGERS = [
  { word: 'yes', sounds: [{ name: 'a.wav', blobKey: 'k1' }] },
  { word: 'no',  sounds: [{ name: 'b.wav', blobKey: 'k2' }] },
];

test('planSave reports sounds whose blobs did not store', () => {
  const { record, failures } = planSave(TRIGGERS, ['k1']);   // k2 missing
  assert.equal(failures.length, 1);
  assert.equal(failures[0].name, 'b.wav');
  assert.equal(record.triggers.length, 2);
});

test('planSave reports no failures when every blob stored', () => {
  const { failures } = planSave(TRIGGERS, ['k1', 'k2']);
  assert.equal(failures.length, 0);
});

test('a clean save is persisted', () => {
  const next = { triggers: TRIGGERS, version: '2.0' };
  const { record, warning } = chooseRecordToPersist(next, null, []);
  assert.equal(record, next);
  assert.equal(warning, null);
});

test('a partial save NEVER replaces a good previous record', () => {
  const previous = { triggers: TRIGGERS, version: '2.0' };
  const degraded = { triggers: [], version: '2.0' };
  const { record, warning } = chooseRecordToPersist(
    degraded, previous, [{ name: 'b.wav' }]);
  assert.equal(record, previous, 'must keep the previous good record');
  assert.match(warning, /b\.wav/);
});

test('a partial save is kept when there is no previous record', () => {
  const partial = { triggers: TRIGGERS, version: '2.0' };
  const { record, warning } = chooseRecordToPersist(
    partial, null, [{ name: 'b.wav' }]);
  assert.equal(record, partial, 'something is better than nothing');
  assert.match(warning, /b\.wav/);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `planSave is not a function`

- [ ] **Step 3: Write minimal implementation**

Append to `persistence.js`:

```javascript
/**
 * Build the record to store, and list any sounds whose blobs are absent.
 * Does not decide what to persist — that is chooseRecordToPersist's job.
 */
export function planSave(triggers, storedBlobKeys) {
  const stored = new Set(storedBlobKeys || []);
  const failures = [];
  for (const trigger of triggers || []) {
    for (const sound of trigger.sounds || []) {
      if (sound.blobKey && !stored.has(sound.blobKey)) {
        failures.push({ word: trigger.word, name: sound.name });
      }
    }
  }
  return {
    record: { triggers, timestamp: Date.now(), version: '2.0' },
    failures,
  };
}

/**
 * Choose which record actually goes to storage.
 *
 * The rule that matters: a save with failures must never overwrite a good
 * previous record. The old code wrote a record marking every sound
 * 'missing_blob' over the working one, which is how layouts survived but
 * audio did not.
 */
export function chooseRecordToPersist(newRecord, previousRecord, failures) {
  if (!failures || failures.length === 0) {
    return { record: newRecord, warning: null };
  }
  const names = failures.map(f => f.name).join(', ');
  if (previousRecord) {
    return {
      record: previousRecord,
      warning: `Could not store: ${names}. Kept the previous saved pack.`,
    };
  }
  return {
    record: newRecord,
    warning: `Could not store: ${names}. Saved what did work.`,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: 9 passing

- [ ] **Step 5: Commit**

```bash
git add persistence.js test/persistence.test.js
git commit -m "feat(persistence): never overwrite a good save with a partial one"
```

---

### Task 3: Wire Task 1 and 2 into index.html, delete the destructive paths

This is the task that fixes the reported symptom. After it, phase 1 of the spec is done.

**Files:**
- Modify: `index.html` — the auto-load block (~`:8837`–`:8941`), the ZIP save block (~`:7055`–`:7076`), and the `<head>` script tags.

**Interfaces:**
- Consumes: `shouldAutoLoad`, `planSave`, `chooseRecordToPersist` from `persistence.js`.
- Produces: a global `showPersistenceWarning(message)` used by later tasks.

- [ ] **Step 1: Import the module**

`persistence.js` is an ES module, so the inline script that uses it must become one. Add this **once**, immediately after the JSZip `<script>` tag in `<head>`:

```html
<script type="module">
  import * as persistence from './persistence.js';
  window.persistence = persistence;
  window.dispatchEvent(new Event('persistence-ready'));
</script>
```

Attaching to `window` deliberately: the existing 8000-line inline script is a classic script, not a module, and cannot `import`. This is the smallest bridge that avoids restructuring it.

- [ ] **Step 2: Add the warning banner**

The launcher runs Chrome with `--app=` (no DevTools), so `console.warn` is invisible. Add this markup immediately after `<body>`:

```html
<div id="persistenceWarning" style="display:none;position:sticky;top:0;z-index:9999;
     background:#3a2a00;color:#ffd479;border-bottom:1px solid #7a5a00;
     padding:10px 14px;font-size:14px;">
  <span id="persistenceWarningText"></span>
  <button id="persistenceWarningDismiss"
          style="float:right;background:none;border:1px solid #7a5a00;color:#ffd479;
                 border-radius:4px;cursor:pointer;padding:2px 8px;">dismiss</button>
</div>
```

And this function alongside the other top-level functions in the inline script:

```javascript
function showPersistenceWarning(message) {
    const bar = document.getElementById('persistenceWarning');
    const text = document.getElementById('persistenceWarningText');
    if (!bar || !text) { console.warn(message); return; }
    text.textContent = message;          // textContent, never innerHTML
    bar.style.display = '';
    console.warn(message);
}
document.getElementById('persistenceWarningDismiss')
    ?.addEventListener('click', () => {
        document.getElementById('persistenceWarning').style.display = 'none';
    });
```

- [ ] **Step 3: Replace the auto-load decision and DELETE both removeItem pairs**

In the auto-load block, replace the `daysSince` computation and its `if (daysSince < 7 && zipInfo.triggerCount > 0)` condition with a call to `shouldAutoLoad`, and **delete the entire `else` branch containing the `daysSince >= 7` cleanup.** The decision becomes:

```javascript
const stored = JSON.parse(lastZipData);
const decision = window.persistence.shouldAutoLoad(stored);
if (!decision.load) {
    console.log(`ℹ️ Not auto-loading: ${decision.reason}`);
    return false;
}
// ... existing restore logic continues unchanged, using `stored` ...
```

Then in the outer `catch (e)`, **delete both `localStorage.removeItem` lines** and replace with:

```javascript
} catch (e) {
    showPersistenceWarning(
        `Could not load your saved soundpack: ${e.message}. ` +
        `Your saved data has been left untouched — try reloading.`);
    return false;
}
```

> **Verify:** after this step, `grep -n "removeItem('lastZipData')" index.html` must return **nothing**. If it returns a line, the destructive path is still live.

- [ ] **Step 4: Replace the save fallback**

In the ZIP save block, replace the `try`/`catch (storageError)` so the catch no longer builds a `missing_blob` record:

```javascript
const previousRaw = localStorage.getItem('lastZipData');
const previousRecord = previousRaw ? JSON.parse(previousRaw) : null;
const { record, failures } = window.persistence.planSave(
    triggersWithDBRefs, storedBlobKeys);
const { record: toPersist, warning } =
    window.persistence.chooseRecordToPersist(record, previousRecord, failures);
localStorage.setItem('lastZipData', JSON.stringify(toPersist));
if (warning) showPersistenceWarning(warning);
```

`storedBlobKeys` is an array you accumulate as each `saveAudioToDB` resolves — push `blobKey` on success only.

- [ ] **Step 5: Verify in the browser**

Start the server (`python local_server.py`), open `http://localhost:8002`, import a soundpack, close the tab, reopen. The pack must still load. Then in DevTools run `localStorage.setItem('lastZipData','{bad json')` and reload: you must see the warning banner and `lastZipData` must **still be present** afterwards.

- [ ] **Step 6: Commit**

```bash
git add index.html
git commit -m "fix: stop deleting the user's soundpack on expiry or error"
```

---

### Task 4: Backup manifest — build and parse

Spec §5.2. Pure data shaping; the ZIP I/O is Task 5.

**Files:**
- Modify: `persistence.js`, `test/persistence.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `buildBackupManifest(state) -> object`, `parseBackupManifest(json) -> {settings, warnings}`. `state` has keys `globalSettings`, `keyboardShortcuts`, `controlShortcuts`, `favoriteTriggers`, `masterVolume`, `selectedInputDevice`, `selectedOutputDevice`, `gains`.

- [ ] **Step 1: Write the failing test**

```javascript
// append to test/persistence.test.js
import { buildBackupManifest, parseBackupManifest } from '../persistence.js';

const STATE = {
  globalSettings: { minWordLength: 3 },
  keyboardShortcuts: { a: 'yes' },
  controlShortcuts: { b: 'stop' },
  favoriteTriggers: ['yes'],
  masterVolume: 0.8,
  selectedInputDevice: 'mic-1',
  selectedOutputDevice: 'out-1',
  gains: { 'a.wav': { autoGain: 0.5, trimDb: 3 } },
};

test('manifest carries every field and a version', () => {
  const m = buildBackupManifest(STATE);
  assert.equal(m.version, '1.0');
  assert.equal(m.masterVolume, 0.8);
  assert.deepEqual(m.favoriteTriggers, ['yes']);
  assert.equal(m.gains['a.wav'].trimDb, 3);
});

test('round trip preserves state', () => {
  const parsed = parseBackupManifest(JSON.stringify(buildBackupManifest(STATE)));
  assert.deepEqual(parsed.settings.globalSettings, STATE.globalSettings);
  assert.equal(parsed.warnings.length, 0);
});

test('malformed json yields a warning, not a throw', () => {
  const parsed = parseBackupManifest('{not json');
  assert.equal(parsed.settings, null);
  assert.match(parsed.warnings[0], /could not/i);
});

test('an unknown future version still parses what it recognises', () => {
  const future = JSON.stringify({ version: '9.9', masterVolume: 0.5 });
  const parsed = parseBackupManifest(future);
  assert.equal(parsed.settings.masterVolume, 0.5);
  assert.match(parsed.warnings[0], /newer/i);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `buildBackupManifest is not a function`

- [ ] **Step 3: Write minimal implementation**

Append to `persistence.js`:

```javascript
export const BACKUP_MANIFEST_VERSION = '1.0';

export function buildBackupManifest(state) {
  return {
    version: BACKUP_MANIFEST_VERSION,
    exportedAt: new Date().toISOString(),
    globalSettings: state.globalSettings ?? {},
    keyboardShortcuts: state.keyboardShortcuts ?? {},
    controlShortcuts: state.controlShortcuts ?? {},
    favoriteTriggers: state.favoriteTriggers ?? [],
    masterVolume: state.masterVolume ?? 1,
    selectedInputDevice: state.selectedInputDevice ?? null,
    selectedOutputDevice: state.selectedOutputDevice ?? null,
    gains: state.gains ?? {},
  };
}

export function parseBackupManifest(json) {
  const warnings = [];
  let raw;
  try {
    raw = JSON.parse(json);
  } catch (e) {
    return { settings: null, warnings: [`Could not read backup settings: ${e.message}`] };
  }
  if (raw.version && raw.version !== BACKUP_MANIFEST_VERSION) {
    warnings.push(
      `Backup was made by a newer version (${raw.version}); ` +
      `restoring what this build understands.`);
  }
  return { settings: raw, warnings };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: 13 passing

- [ ] **Step 5: Commit**

```bash
git add persistence.js test/persistence.test.js
git commit -m "feat(backup): manifest build and forward-compatible parse"
```

---

### Task 5: Export and import the backup ZIP

Spec §5.2 — a superset of the existing soundpack format, so old packs still import and new backups open in older builds.

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `buildBackupManifest`, `parseBackupManifest`, `getAudioFromDB`, JSZip.
- Produces: `exportBackup()`, `importBackup(file)`.

- [ ] **Step 1: Add the export function**

Add alongside `exportGlobalSettings` in the inline script:

```javascript
async function exportBackup() {
    try {
        updateStatus('Building backup…');
        const zip = new JSZip();
        const soundpack = { triggers: [] };
        const seen = new Set();

        for (const trigger of triggers) {
            const entry = { word: trigger.word, sounds: [] };
            for (const sound of (trigger.sounds || [])) {
                entry.sounds.push({ name: sound.name });
                if (sound.blobKey && !seen.has(sound.name)) {
                    seen.add(sound.name);
                    const blob = await getAudioFromDB(sound.blobKey);
                    if (blob) zip.file(sound.name, blob);
                }
            }
            soundpack.triggers.push(entry);
        }

        zip.file('soundpack.json', JSON.stringify(soundpack, null, 2));
        zip.file('triggerword-backup.json', JSON.stringify(
            window.persistence.buildBackupManifest({
                globalSettings, keyboardShortcuts, controlShortcuts,
                favoriteTriggers: [...favoriteTriggers],
                masterVolume: parseFloat(localStorage.getItem('masterVolume') || '1'),
                selectedInputDevice: localStorage.getItem('selectedInputDevice'),
                selectedOutputDevice: localStorage.getItem('selectedOutputDevice'),
                gains: loadGains(),
            }), null, 2));

        const blob = await zip.generateAsync({ type: 'blob' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `triggerword-backup-${new Date().toISOString().slice(0,10)}.zip`;
        a.click();
        URL.revokeObjectURL(url);
        updateStatus('✅ Backup exported', 'success');
    } catch (e) {
        showPersistenceWarning(`Backup failed: ${e.message}. Nothing was changed.`);
    }
}
```

`loadGains()` is defined in Task 8. **Until Task 8 lands, define a stub returning `{}`** at the top of the inline script so export works standalone:

```javascript
function loadGains() { return JSON.parse(localStorage.getItem('soundGains') || '{}'); }
```

- [ ] **Step 2: Add the import function**

```javascript
async function importBackup(file) {
    try {
        const zip = await JSZip.loadAsync(file);
        const manifestFile = zip.file('triggerword-backup.json');
        if (!manifestFile) {
            updateStatus('No backup settings in this ZIP — importing as a soundpack');
            return handleZipFile(file);       // existing soundpack path, unchanged
        }
        const { settings, warnings } =
            window.persistence.parseBackupManifest(await manifestFile.async('string'));
        warnings.forEach(showPersistenceWarning);
        if (settings) {
            if (settings.globalSettings)
                localStorage.setItem('globalSettings', JSON.stringify(settings.globalSettings));
            if (settings.keyboardShortcuts)
                localStorage.setItem('keyboardShortcuts', JSON.stringify(settings.keyboardShortcuts));
            if (settings.controlShortcuts)
                localStorage.setItem('controlShortcuts', JSON.stringify(settings.controlShortcuts));
            if (settings.favoriteTriggers)
                localStorage.setItem('favoriteTriggers', JSON.stringify(settings.favoriteTriggers));
            if (settings.masterVolume != null)
                localStorage.setItem('masterVolume', String(settings.masterVolume));
            if (settings.gains)
                localStorage.setItem('soundGains', JSON.stringify(settings.gains));
        }
        await handleZipFile(file);            // sounds + triggers via the existing path
        updateStatus('✅ Backup restored', 'success');
    } catch (e) {
        showPersistenceWarning(`Restore failed: ${e.message}. Nothing was changed.`);
    }
}
```

> **Verify before committing:** confirm the existing soundpack import function is actually named `handleZipFile` — `grep -n "function handleZipFile" index.html`. If it has a different name, use the real one.

- [ ] **Step 3: Add the two buttons**

Next to the existing settings export/import controls:

```html
<button id="exportBackupBtn">Export backup (everything)</button>
<input type="file" id="importBackupInput" accept=".zip" style="display:none">
<button id="importBackupBtn">Import backup</button>
```

Wire them without inline handlers:

```javascript
document.getElementById('exportBackupBtn')?.addEventListener('click', exportBackup);
document.getElementById('importBackupBtn')?.addEventListener('click',
    () => document.getElementById('importBackupInput').click());
document.getElementById('importBackupInput')?.addEventListener('change', function () {
    if (this.files[0]) importBackup(this.files[0]);
    this.value = '';
});
```

- [ ] **Step 4: Verify both directions in the browser**

Import a soundpack, set a keyboard shortcut and a favourite, export a backup. Open DevTools → Application → clear localStorage **and** delete the `TriggerAudioDB` database. Reload, import the backup: sounds, triggers, the shortcut and the favourite must all return.

Then import an **old** soundpack ZIP (no `triggerword-backup.json`) and confirm it still imports normally.

- [ ] **Step 5: Commit**

```bash
git add index.html
git commit -m "feat(backup): one-file export and restore"
```

---

### Task 6: Orphan detection

Spec §5.3 — reported with size, never auto-deleted.

**Files:**
- Modify: `persistence.js`, `test/persistence.test.js`, `index.html`

**Interfaces:**
- Consumes: nothing.
- Produces: `findOrphanBlobs(triggers, dbEntries) -> {keys, totalBytes}` where `dbEntries` is `[{key, size}]`.

- [ ] **Step 1: Write the failing test**

```javascript
// append to test/persistence.test.js
import { findOrphanBlobs } from '../persistence.js';

test('finds blobs no trigger references', () => {
  const triggers = [{ word: 'a', sounds: [{ blobKey: 'k1' }] }];
  const db = [{ key: 'k1', size: 100 }, { key: 'k2', size: 250 }];
  const { keys, totalBytes } = findOrphanBlobs(triggers, db);
  assert.deepEqual(keys, ['k2']);
  assert.equal(totalBytes, 250);
});

test('reports nothing when every blob is referenced', () => {
  const triggers = [{ word: 'a', sounds: [{ blobKey: 'k1' }] }];
  const { keys, totalBytes } = findOrphanBlobs(triggers, [{ key: 'k1', size: 100 }]);
  assert.deepEqual(keys, []);
  assert.equal(totalBytes, 0);
});

test('treats an empty trigger list as referencing nothing', () => {
  const { keys } = findOrphanBlobs([], [{ key: 'k1', size: 100 }]);
  assert.deepEqual(keys, ['k1']);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `findOrphanBlobs is not a function`

- [ ] **Step 3: Write minimal implementation**

```javascript
/**
 * Identify DB blobs no trigger references.
 *
 * Reporting only. Callers must NOT delete automatically — a blob that looks
 * orphaned may belong to a record that failed to load this session, and
 * auto-deleting is the same instinct that caused the data loss this module
 * exists to prevent.
 */
export function findOrphanBlobs(triggers, dbEntries) {
  const referenced = new Set();
  for (const trigger of triggers || []) {
    for (const sound of trigger.sounds || []) {
      if (sound.blobKey) referenced.add(sound.blobKey);
    }
  }
  const keys = [];
  let totalBytes = 0;
  for (const entry of dbEntries || []) {
    if (!referenced.has(entry.key)) {
      keys.push(entry.key);
      totalBytes += entry.size || 0;
    }
  }
  return { keys, totalBytes };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: 16 passing

- [ ] **Step 5: Wire the report into the UI**

Add `<div id="orphanReport"></div>` and `<button id="checkOrphansBtn">Check for unused sounds</button>` in the settings area, then:

```javascript
async function reportOrphans() {
    const entries = await new Promise((resolve) => {
        const req = indexedDB.open('TriggerAudioDB', 1);
        req.onsuccess = function() {
            const db = req.result;
            const tx = db.transaction('audio', 'readonly');
            const store = tx.objectStore('audio');
            const out = [];
            store.openCursor().onsuccess = function(e) {
                const cursor = e.target.result;
                if (cursor) {
                    out.push({ key: cursor.key, size: cursor.value?.size || 0 });
                    cursor.continue();
                } else resolve(out);
            };
        };
        req.onerror = function() { resolve([]); };
    });

    const { keys, totalBytes } = window.persistence.findOrphanBlobs(triggers, entries);
    const el = document.getElementById('orphanReport');
    el.textContent = '';                              // clear, never innerHTML
    if (!keys.length) { el.textContent = 'No unused sounds.'; return; }

    const mb = (totalBytes / 1048576).toFixed(1);
    el.appendChild(document.createTextNode(
        `${keys.length} unused sounds (${mb} MB). `));

    const btn = document.createElement('button');
    btn.textContent = 'Clean up';
    btn.addEventListener('click', async () => {
        btn.disabled = true;
        for (const k of keys) await removeAudioFromDB(k);
        el.textContent = `Removed ${keys.length} unused sounds.`;
    });
    el.appendChild(btn);
}
document.getElementById('checkOrphansBtn')?.addEventListener('click', reportOrphans);
```

- [ ] **Step 6: Commit**

```bash
git add persistence.js test/persistence.test.js index.html
git commit -m "feat(storage): report orphaned audio blobs without deleting them"
```

---

### Task 7: Levelling maths

Spec §5.4. Pure arithmetic over a `Float32Array` — fully testable in Node.

**Files:**
- Modify: `persistence.js`, `test/persistence.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `analyseSamples(channelData) -> {rms, peak}`, `computeAutoGain({rms, peak}) -> number`, `finalGain(autoGain, trimDb) -> number`, and constants `TARGET_RMS`, `PEAK_CEILING`, `TRIM_MIN_DB`, `TRIM_MAX_DB`.

- [ ] **Step 1: Write the failing test**

```javascript
// append to test/persistence.test.js
import {
  analyseSamples, computeAutoGain, finalGain,
  TARGET_RMS, PEAK_CEILING, TRIM_MIN_DB, TRIM_MAX_DB,
} from '../persistence.js';

test('constants match the spec', () => {
  assert.ok(Math.abs(TARGET_RMS - 0.1) < 1e-9);                  // -20 dBFS
  assert.ok(Math.abs(PEAK_CEILING - 0.8912509381337456) < 1e-9); // -1 dBFS
  assert.equal(TRIM_MIN_DB, -12);
  assert.equal(TRIM_MAX_DB, 12);
});

test('analyseSamples computes rms and peak', () => {
  const data = Float32Array.from([0.5, -0.5, 0.5, -0.5]);
  const { rms, peak } = analyseSamples(data);
  assert.ok(Math.abs(rms - 0.5) < 1e-6);
  assert.ok(Math.abs(peak - 0.5) < 1e-6);
});

test('a quiet sound is boosted toward the target', () => {
  const gain = computeAutoGain({ rms: 0.01, peak: 0.02 });
  assert.ok(gain > 1, 'quiet sound should be turned up');
});

test('the peak ceiling wins over the rms target when it must', () => {
  // rms alone says boost 10x; peak 0.5 would then reach 5.0 and clip badly.
  const gain = computeAutoGain({ rms: 0.01, peak: 0.5 });
  assert.ok(gain * 0.5 <= PEAK_CEILING + 1e-9, 'must not exceed the ceiling');
});

test('silence is left alone rather than dividing by zero', () => {
  assert.equal(computeAutoGain({ rms: 0, peak: 0 }), 1);
});

test('trim of 0 dB changes nothing', () => {
  assert.ok(Math.abs(finalGain(0.5, 0) - 0.5) < 1e-9);
});

test('+6 dB trim roughly doubles the gain', () => {
  assert.ok(Math.abs(finalGain(0.5, 6) - 1.0) < 0.01);
});

test('trim is clamped to the allowed range', () => {
  assert.equal(finalGain(1, 99), finalGain(1, TRIM_MAX_DB));
  assert.equal(finalGain(1, -99), finalGain(1, TRIM_MIN_DB));
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test`
Expected: FAIL — `analyseSamples is not a function`

- [ ] **Step 3: Write minimal implementation**

```javascript
// ---- levelling ----------------------------------------------------------
// Targets from spec 5.4. RMS tracks perceived loudness; the peak ceiling
// guarantees nothing clips, which is what actually makes a soundboard
// unpleasant.
export const TARGET_RMS = 0.1;                    // -20 dBFS
export const PEAK_CEILING = 0.8912509381337456;   // -1 dBFS
export const TRIM_MIN_DB = -12;
export const TRIM_MAX_DB = 12;

export function analyseSamples(channelData) {
  let sumSquares = 0;
  let peak = 0;
  for (let i = 0; i < channelData.length; i++) {
    const s = channelData[i];
    sumSquares += s * s;
    const a = s < 0 ? -s : s;
    if (a > peak) peak = a;
  }
  const rms = channelData.length ? Math.sqrt(sumSquares / channelData.length) : 0;
  return { rms, peak };
}

/** Whichever constraint binds, wins. Silence is left at unity gain. */
export function computeAutoGain({ rms, peak }) {
  if (!rms || !peak) return 1;
  return Math.min(TARGET_RMS / rms, PEAK_CEILING / peak);
}

export function finalGain(autoGain, trimDb) {
  const clamped = Math.max(TRIM_MIN_DB, Math.min(TRIM_MAX_DB, trimDb || 0));
  return autoGain * Math.pow(10, clamped / 20);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test`
Expected: 24 passing

- [ ] **Step 5: Commit**

```bash
git add persistence.js test/persistence.test.js
git commit -m "feat(levelling): rms-targeted gain with a peak ceiling and trim"
```

---

### Task 8: Apply gain at playback, add the trim slider and master limiter

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `analyseSamples`, `computeAutoGain`, `finalGain`, `TRIM_MIN_DB`, `TRIM_MAX_DB`.
- Produces: `loadGains()`, `saveGains(gains)`, `analyseAndStoreGain(name, audioBuffer)`, and a master `GainNode` → `DynamicsCompressorNode` chain.

- [ ] **Step 1: Store and retrieve gains**

```javascript
function loadGains() {
    try { return JSON.parse(localStorage.getItem('soundGains') || '{}'); }
    catch (e) { return {}; }
}
function saveGains(gains) {
    localStorage.setItem('soundGains', JSON.stringify(gains));
}
```

If a `loadGains` stub was added in Task 5, replace it with this pair.

- [ ] **Step 2: Analyse each sound once, at import**

Where the app decodes audio during soundpack import, add:

```javascript
function analyseAndStoreGain(name, audioBuffer) {
    const gains = loadGains();
    if (gains[name] && gains[name].autoGain != null) return gains[name];
    const stats = window.persistence.analyseSamples(audioBuffer.getChannelData(0));
    const entry = { autoGain: window.persistence.computeAutoGain(stats), trimDb: 0 };
    gains[name] = entry;
    saveGains(gains);
    return entry;
}
```

Analysis happens **once per sound at import**, never on every load — the decode is already happening for playback, so this is one extra pass over samples already in memory.

- [ ] **Step 3: Build the master chain**

Once, where the `AudioContext` is created:

```javascript
const masterGain = audioContext.createGain();
const masterLimiter = audioContext.createDynamicsCompressor();
// Safety net for two sounds firing at once — per-sound gain cannot fix overlap.
masterLimiter.threshold.value = -3;
masterLimiter.knee.value = 0;
masterLimiter.ratio.value = 20;
masterLimiter.attack.value = 0.002;
masterLimiter.release.value = 0.1;
masterGain.connect(masterLimiter);
masterLimiter.connect(audioContext.destination);
```

Route every playing source through `masterGain` instead of straight to `destination`.

- [ ] **Step 4: Apply per-sound gain on playback**

Where a sound is played, insert a `GainNode` carrying its computed value:

```javascript
const gains = loadGains();
const entry = gains[soundName] || { autoGain: 1, trimDb: 0 };
const g = audioContext.createGain();
g.gain.value = window.persistence.finalGain(entry.autoGain, entry.trimDb);
source.connect(g);
g.connect(masterGain);
```

- [ ] **Step 5: Add the trim slider**

In each sound's row in the trigger list, create the controls with DOM methods (the list is rendered in JS):

```javascript
function makeTrimControls(soundName) {
    const gains = loadGains();
    const entry = gains[soundName] || { autoGain: 1, trimDb: 0 };

    const slider = document.createElement('input');
    slider.type = 'range';
    slider.min = String(window.persistence.TRIM_MIN_DB);
    slider.max = String(window.persistence.TRIM_MAX_DB);
    slider.step = '0.5';
    slider.value = String(entry.trimDb || 0);
    slider.title = 'Trim (dB)';
    slider.addEventListener('input', () => setTrim(soundName, parseFloat(slider.value)));

    const reset = document.createElement('button');
    reset.textContent = 'auto';
    reset.title = 'Reset to automatic';
    reset.addEventListener('click', () => { slider.value = '0'; setTrim(soundName, 0); });

    const wrap = document.createElement('span');
    wrap.appendChild(slider);
    wrap.appendChild(reset);
    return wrap;
}

function setTrim(soundName, trimDb) {
    const gains = loadGains();
    if (!gains[soundName]) gains[soundName] = { autoGain: 1, trimDb: 0 };
    gains[soundName].trimDb = Math.max(
        window.persistence.TRIM_MIN_DB,
        Math.min(window.persistence.TRIM_MAX_DB, trimDb));
    saveGains(gains);
}
```

Append `makeTrimControls(sound.name)` to each sound's row where the list is built.

- [ ] **Step 6: Verify by ear**

Import a pack containing one very quiet and one very loud sound. Both must play at a similar level, and neither must crackle. Pull a trim to −12 and confirm that sound gets quieter; press **auto** and confirm it returns.

- [ ] **Step 7: Run the full suite and commit**

Run: `node --test`
Expected: 24 passing, no failures.

```bash
git add index.html
git commit -m "feat(levelling): apply per-sound gain, trim slider and master limiter"
```

---

## Deferred, deliberately

- **Full EBU R128 loudness** — spec §5.4 chose RMS. Revisit only if matching across different packs proves audibly off.
- **Moving metadata into IndexedDB** — spec §7. The split is correct; Tasks 1–3 remove the bug that made it look otherwise.
- **The empty audio-device dropdowns** — spec §7. Root cause is a missing Chrome microphone permission for `http://localhost:8002`, fixed in browser settings, no code change.
