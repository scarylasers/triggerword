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
