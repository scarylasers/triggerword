# TriggerWord sample library — persistence, backup, levelling

**Date:** 2026-08-03
**Status:** approved design, not yet planned
**Code:** `index.html` (single 458 KB file), plus a new `persistence.js`

---

## 1. The problem

Two problems, one storage format.

**Soundpacks and layouts disappear.** Reported as intermittent — "sometimes it
doesn't load the sounds or layout." It is not intermittent. It is four code
paths that treat a failure as permission to delete the user's data.

**Sound levels are uneven.** Cantabile was running purely to even them out,
which means a whole VST host in the VR startup chain doing one job that the
browser can do natively and better.

They share a spec because levelling produces **stored per-sound data** that the
persistence rework is already handling, and that must travel inside the backup
file. Designing them apart would mean changing the storage format twice.

## 2. Root cause of the data loss — measured, not inferred

| # | Location | Behaviour |
|---|---|---|
| 1 | `index.html:8844`, `:8930` | **7-day expiry.** `daysSince >= 7` → `removeItem('lastZipData')` + `removeItem('lastZipImport')`. Do not open the app for a week and the next launch deletes the saved layout. |
| 2 | `index.html:8938` | **Load catch deletes.** Any exception during auto-load → both keys removed. A transient IndexedDB error is unrecoverable. |
| 3 | `index.html:7069` | **Save catch overwrites with a degraded record.** On IndexedDB failure the fallback rewrites every sound as `type: 'missing_blob'` and saves *that over the working record*. Next launch: triggers present, no audio. |
| 4 | all of the above | **Silent.** `console.warn` only. The launcher runs Chrome in `--app=` mode (`TriggerWord-Launcher-DefaultProfile.ps1:58`) — no address bar, no DevTools. A message nobody can see is not a message. |

**Plus a leak:** when localStorage is wiped, the IndexedDB audio blobs are not.
They persist, unreferenced and unreachable.

**The storage architecture is correct and stays.** Blobs in IndexedDB, metadata
in localStorage is the standard split. Every failure here is an error-handling
decision, not a structural one.

## 3. What is already covered — why the scope is small

Recovery today: re-import the soundpack ZIP. That works better than the symptom
suggests, because `soundpack.json` inside the ZIP carries the trigger word →
sounds mapping, not just audio (`make_soundpack.py`). And `exportGlobalSettings`
already backs up shortcuts, favourites and global settings.

The genuine gap is narrow: **in-app trigger edits, device selection, volume, and
now the levelling gains.** That gap is what the backup file closes.

## 4. The governing principle

> **A failure never destroys data.** On error: keep what exists, tell the user,
> offer a retry. Deletion happens only when the user explicitly asks.

Every change below follows from that one rule. All four bugs are violations of it.

## 5. Design

### 5.1 Failure handling

- **Delete the 7-day expiry entirely.** A soundpack persists until replaced.
  There is no scenario where silently discarding it is the helpful choice.
- **No `removeItem` inside any catch block.** A failed auto-load leaves the
  stored record untouched so the next launch retries.
- **Never overwrite a good save with a degraded one.** If the IndexedDB write
  fails, keep the previous record and report which sounds failed to store,
  by name.
- **Failures surface in the UI** — a persistent banner in the app window,
  dismissible, not a toast that vanishes. `console.warn` is invisible under
  `--app=`.

### 5.2 Backup file — a superset of the existing format

One file, deliberately backward and forward compatible:

```
backup.zip
├── soundpack.json           existing format, unchanged
├── triggerword-backup.json  new: shortcuts, favourites, global settings,
│                            master volume, device selection, in-app trigger
│                            edits, levelling gains, manual trims
└── sounds/…                 audio, read out of IndexedDB via getAudioFromDB
```

**Old soundpacks import unchanged** (no `triggerword-backup.json` → behaves
exactly as today). **New backups work in older copies of the app** — the extra
file is ignored. No migration step, no version break.

`JSZip` is already loaded for soundpack import; `getAudioFromDB` already exists.

### 5.3 Orphan cleanup — reported, never automatic

Unreferenced IndexedDB blobs are counted and shown with their total size
("3 unused sounds, 24 MB — clean up?") behind a button.

**Not auto-deleted, on purpose.** Auto-deleting orphans is the same instinct
that caused this bug: a blob that looks orphaned may be referenced by a record
that failed to load this session. The user decides.

### 5.4 Levelling

**Analyse once at import.** The sound is already decoded for playback; that
yields an `AudioBuffer`. One pass over `getChannelData()` gives RMS and true
peak. Store the result. No library, no second decode, no analysis at load time.

**Gain formula, doing two jobs:**

```
autoGain = min( targetRMS / actualRMS ,  peakCeiling / actualPeak )
```

| Constant | Value | Why |
|---|---|---|
| `targetRMS` | **−20 dBFS** | Consistent perceived level across the pack. |
| `peakCeiling` | **−1 dBFS** | Guarantees nothing clips. Clipping is what actually makes a soundboard unpleasant. |

Whichever term binds, wins — so a clip with one sharp transient is held down by
the peak term rather than boosted into distortion.

**RMS, not peak.** Peak normalisation is what most soundboards do and is why
they are unpleasant: a quiet clip with a single click stays quiet, a dense loud
clip stays loud. RMS tracks what ears hear.

**Not full LUFS.** Proper EBU R128 needs K-weighting filters. This is a "nobody
flinches" problem, not a compliance one; RMS delivers ~90% of the benefit for a
fraction of the work. Revisit only if matching across packs proves audibly off.

**Manual trim.** A per-sound slider, **−12 dB to +12 dB**, default 0, stored
per sound and applied on top of `autoGain`:

```
finalGain = autoGain * 10^(trimDb / 20)
```

With a reset-to-auto control. Trims travel in the backup file.

**Master limiter.** A `DynamicsCompressorNode` on the output bus, as the safety
net for two sounds firing simultaneously — the one case per-sound gain cannot
address.

**This replaces Cantabile**, and improves on it: pre-computed per-sound gain
preserves each clip's own dynamics, where a live compressor ducks whatever is
playing whenever something loud arrives.

### 5.5 Testability

`index.html` is a single 458 KB file with no test framework, and its persistence
logic is entangled with DOM code.

**Extract the persistence and levelling functions into `persistence.js`, with no
DOM dependencies.** `index.html` calls into it. That module is unit-testable;
everything else in the file stays untouched. This is the smallest change that
makes the logic verifiable, and it is confined to the code this spec already
rewrites.

## 6. Implementation phases

1. **Failure handling** (§5.1) — fixes 100% of the reported symptom on its own.
2. **Backup file** (§5.2) and **orphan cleanup** (§5.3).
3. **Levelling** (§5.4) — auto gain, then manual trim.

Phase 1 ships value alone and is independently verifiable.

## 7. Out of scope

- **Rewriting the storage architecture.** The IndexedDB/localStorage split is
  correct. Moving metadata into IndexedDB would be a large change to working
  code to prevent a bug that §5.1 already prevents.
- **Restructuring `index.html`** beyond extracting `persistence.js`.
- **Full EBU R128 loudness.** See §5.4.
- **The empty audio-device dropdowns.** Separate root cause, already diagnosed:
  microphone permission was never granted for `http://localhost:8002`
  (Chrome's `media_stream_mic` exceptions list is empty), and `--app=` mode has
  no padlock icon to grant it from. Fixed via `chrome://settings/content/microphone`,
  no code change required.

## 8. Success criteria

1. No code path deletes stored data except at explicit user request.
2. A soundpack survives arbitrarily long gaps between sessions.
3. A failed save leaves the previous working record intact.
4. Any persistence failure is visible in the app window without DevTools.
5. One exported file restores sounds, triggers, shortcuts, favourites,
   settings, gains and trims.
6. Old soundpacks still import; new backups still open in older builds.
7. Orphaned blobs are reported with their size and removed only on request.
8. No sound in a pack clips, and no sound is startlingly louder than its
   neighbours.
9. Cantabile is no longer needed for levelling.
