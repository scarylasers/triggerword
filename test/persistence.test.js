import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldAutoLoad, planSave, chooseRecordToPersist, buildBackupManifest, parseBackupManifest, findOrphanBlobs } from '../persistence.js';

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

test('planSave decouples the returned record from mutations to the caller\'s array', () => {
  const mutableTriggers = [
    { word: 'yes', sounds: [{ name: 'a.wav', blobKey: 'k1' }] },
  ];
  const { record } = planSave(mutableTriggers, ['k1']);
  assert.equal(record.triggers.length, 1, 'initial snapshot is correct');

  mutableTriggers.push({ word: 'extra', sounds: [] });
  assert.equal(record.triggers.length, 1, 'record is not mutated by caller changes');
  assert.equal(mutableTriggers.length, 2, 'caller array was actually mutated');
});

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

test('buildBackupManifest preserves masterVolume: 0 (not falsy defaults)', () => {
  const m = buildBackupManifest({ masterVolume: 0 });
  assert.equal(m.masterVolume, 0);
});

test('parseBackupManifest applies defaults to truncated manifests', () => {
  const truncated = JSON.stringify({ version: '1.0', masterVolume: 0.5 });
  const parsed = parseBackupManifest(truncated);
  assert.equal(parsed.settings.masterVolume, 0.5);
  assert(Array.isArray(parsed.settings.favoriteTriggers));
  assert(typeof parsed.settings.gains === 'object');
  assert.equal(parsed.warnings.length, 0);
});

test('parseBackupManifest handles missing version field without warning', () => {
  const noVersion = JSON.stringify({ masterVolume: 0.5 });
  const parsed = parseBackupManifest(noVersion);
  assert.equal(parsed.settings.masterVolume, 0.5);
  assert.equal(parsed.warnings.length, 0);
});

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
