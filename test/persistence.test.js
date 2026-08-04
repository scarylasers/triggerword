import { test } from 'node:test';
import assert from 'node:assert/strict';
import { shouldAutoLoad, planSave, chooseRecordToPersist } from '../persistence.js';

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
