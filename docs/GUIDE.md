# TriggerWord — the longer guide

The [README](../README.md) gets you running. This explains what is actually
happening, and the thinking behind the parts that look odd.

---

## Where this came from

I stream in VR. My hands are inside a game, my face is inside a headset, and a
soundboard that needs a keypress may as well not exist.

The obvious fix is a second person on the board, which I don't have. The next
obvious fix is voice control, which existed but always in the wrong shape —
either a cloud assistant that wants an account and a wake word, or a broadcast
suite where the soundboard is feature number forty.

So: a page that listens for words I was going to say anyway, and plays a sound
when it hears one. Nothing else.

### The part that took longest to learn

The first version was too good at its job.

Trigger it on a common word and it fires constantly. Fire it constantly and the
joke dies in about ninety seconds, and then you are the streamer with the
airhorn. I had built something genuinely annoying and it took a friend saying so
for me to hear it.

**Everything restrained in this tool is there because of that.** The cooldown,
the deliberate advice to pick unusual trigger words, the levelling that stops
sounds startling people. None of it is polish — it is the difference between a
tool that is funny and a tool that gets you muted.

A soundboard that listens is a loaded gun pointed at your own stream. Aim it
carefully.

---

## How it works

```
your voice
    │
    ▼
browser speech recognition        (built into Chrome — nothing downloaded)
    │
    ▼
transcript ──▶ matched against your trigger words
    │                    │
    │                    ▼
    │              cooldown check      (has this fired recently?)
    │                    │
    ▼                    ▼
 displayed          sound selected     (random, if the trigger has several)
                         │
                         ▼
                   levelling gain      (measured once, when you added it)
                         │
                         ▼
                   output device       (whichever you chose)
```

Everything above happens on your machine. The only network request the page ever
makes is Chrome's own speech recognition, which is part of the browser.

### Speech recognition

Uses the Web Speech API, which Chrome and Edge ship with. That is why there is no
model to download and no GPU needed — and also why Firefox and Safari don't work.

An earlier version ran OpenAI Whisper locally through `local_server.py`. That
code is still in the repo and still works, but it pulls in torch (a multi-GB
download) for something the browser now does adequately. Most people should not
install it.

### Matching

Trigger words are matched against the running transcript with a few options you
can set:

- **Word-boundary matching** — "cat" won't fire inside "catastrophe". Leave this
  on unless you have a reason.
- **Morphological matching** — "run" also catches "running", "ran". Useful, and
  also a good way to make a trigger fire more than you meant to.
- **Minimum word length** — stops very short words matching noise.
- **Filtered words** — an explicit never-match list.

### Cooldowns

Each trigger has a cooldown. Once it fires, it will not fire again until that
time passes.

This is the single most important setting in the app and the one people are most
tempted to turn off. Don't. A sound that fires twice in five seconds is not twice
as funny.

---

## Storage — and why it used to lose things

Two stores, on purpose:

- **IndexedDB** holds the audio, because audio is large and IndexedDB is built
  for large.
- **localStorage** holds the metadata — your triggers, which sound belongs to
  which word, shortcuts, favourites, settings.

That split is standard and correct. It was also, for a long time, where things
went wrong — not because of the design but because of how failures were handled.

**The bug:** if you didn't open TriggerWord for a week, the next launch deleted
your soundpack. There was a seven-day expiry that called `removeItem` on your
saved layout. Two other paths did the same thing — any error while loading, and
any error while saving — each treating "something went wrong" as permission to
throw your data away.

It looked random. It wasn't; it was a calendar.

**The rule now, applied everywhere:**

> A failure never destroys data. On error: keep what exists, say so, offer a
> retry. Deletion happens only when you ask for it.

Which is why:

- There is no expiry. Your pack persists until you replace it.
- A failed load leaves the stored record untouched so the next launch can retry.
- A partial save never overwrites a good one.
- Failures appear as a **banner in the app**, not a console message. If you run
  the app in a window with no developer tools, a message you can't see isn't a
  message.
- Orphaned audio is **reported, never auto-deleted**. A file that looks orphaned
  might belong to a record that failed to load this session. You get a count and
  a button; the decision is yours.

---

## Levelling, in detail

When you add a sound, it is decoded once and measured:

- **RMS** — roughly, how loud it feels
- **Peak** — the single loudest sample

Then a gain is computed as the *smaller* of two numbers:

```
gain = min( targetRMS / actualRMS ,  peakCeiling / actualPeak )
```

The first term matches perceived loudness across your pack. The second guarantees
nothing clips. Whichever constraint binds, wins — so a quiet clip with one sharp
transient gets held down by the peak term instead of being pushed into distortion.

Targets: **−20 dBFS** RMS, **−1 dBFS** peak ceiling.

**Why RMS rather than peak alone.** Most soundboards normalise by peak, and that
is exactly why they are unpleasant: a quiet clip with one click stays quiet, and
a dense loud clip stays loud. RMS tracks what ears actually hear.

**Why nothing is boosted.** The gain is applied through the audio element's own
`volume`, which cannot exceed 1. That was a deliberate choice: the alternative —
routing everything through Web Audio — would have broken output-device selection,
and sending soundboard audio to a specific device matters more for streaming than
squeezing quiet sounds louder. So loud sounds come down, quiet ones are left
alone, and you raise your master volume to suit.

**Manual trim.** Each sound has a ±12 dB slider and an *auto* button. Trims are
stored per sound and travel inside your backup.

---

## Backup format

The backup ZIP is deliberately a *superset* of the plain soundpack format:

```
backup.zip
├── soundpack.json           standard format — any version can read this
├── triggerword-backup.json  settings, shortcuts, favourites, volume, trims
└── (your sound files)
```

Consequences worth knowing:

- An **old soundpack** with no `triggerword-backup.json` imports normally.
- A **new backup** opens in an older build of TriggerWord — it just ignores the
  extra file and you lose only the settings.

No migration step, no version wall.

---

## Contributing

```bash
node --test
```

28 tests, no dependencies, no `npm install`. They run on `persistence.js`, which
is deliberately pure — no DOM, no storage, no audio context. All of that lives in
`index.html` and gets passed in. If you add logic that needs testing, put it in
`persistence.js` and hand it plain data.

`index.html` is one very large file. That is not ideal and not something to fix
casually; the persistence extraction was done specifically because that logic
needed tests.

---

## A last word on responsibility

This tool makes it effortless to interrupt people. That is its function.

Effortless things get overused. Pick trigger words you rarely say, keep the
cooldowns long, level your sounds so nobody flinches, and remember the people
listening didn't choose your soundboard — you did.

Funny once. Annoying five times. The gap between them is the whole craft.
