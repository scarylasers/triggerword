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
    record: { triggers: [...(triggers || [])], timestamp: Date.now(), version: '2.0' },
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
  const settings = {
    version: raw.version ?? BACKUP_MANIFEST_VERSION,
    exportedAt: raw.exportedAt ?? null,
    globalSettings: raw.globalSettings ?? {},
    keyboardShortcuts: raw.keyboardShortcuts ?? {},
    controlShortcuts: raw.controlShortcuts ?? {},
    favoriteTriggers: raw.favoriteTriggers ?? [],
    masterVolume: raw.masterVolume ?? 1,
    selectedInputDevice: raw.selectedInputDevice ?? null,
    selectedOutputDevice: raw.selectedOutputDevice ?? null,
    gains: raw.gains ?? {},
  };
  return { settings, warnings };
}
