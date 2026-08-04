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
