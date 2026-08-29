# TriggerWord

A soundboard that listens.

You say a word while streaming. It plays the sound. You never touch a key, never
alt-tab, never break what you were doing.

That is the whole idea.

---

## Why this exists

Soundboards are usually operated by hand, which means every sound costs you a
glance at a second screen and a break in whatever you were saying. In VR it is
worse — your hands are busy being hands.

So this listens instead. Say the word, get the sound, keep talking.

**But the reason it works is restraint, and that needs saying plainly.**

There is a very fine line between *funny* and *annoying*, and a listening
soundboard sits right on it. A sound that lands once is a joke. The same sound
on a hair trigger, five times in a minute, is a reason to close the tab.

This tool is built for the funny side of that line:

- **Trigger words are yours to choose.** Pick words you actually say at moments
  that actually deserve a sound. Not "the" and not "and".
- **Cooldowns exist on purpose.** A trigger that just fired will not fire again
  immediately. This is a feature. Leave it on.
- **Levelling is built in** so nothing blasts your listeners. See below.
- **Everything is local.** No account, no server, no telemetry. Your audio never
  leaves the machine.

Use it responsibly. The people listening did not consent to an airhorn.

---

## Install it — the easy way

Download **`TriggerWord-Setup.exe`** from the
[latest release](https://github.com/scarylasers/triggerword/releases/latest)
and run it. Python is bundled, so there is nothing else to install and nothing
to unzip — you get a desktop shortcut and a normal uninstaller.

> Windows will show *"Windows protected your PC"* because the installer isn't
> code-signed (those certificates are expensive). Click **More info → Run
> anyway**. All the source is right here if you'd rather read it first.

You still need **Chrome or Edge** installed — speech recognition and per-sound
output routing are Chromium features.

Then: click **Allow** for the microphone, import the starter pack, and say
**"lasers"**.

## Run from source — the developer way

This route also unlocks the advanced features (offline Whisper, global hotkeys).

1. **Download this repository** — the green *Code* button → *Download ZIP* →
   unzip it somewhere you'll find again.
2. **Double-click `start-triggerword.bat`** (Windows).
   A black window opens and stays open. That is the app running — leave it.
3. TriggerWord opens in its own window (or at **http://localhost:8002** in a
   browser tab if neither Chrome nor Edge is installed).
4. **Click "Allow"** when it asks for your microphone. Nothing works without it.
5. Import the included **`TriggerWord-Starter-Pack.zip`** (use *Import backup*
   in the 🔧 menu to also get favorites) — original SCARYLASERS sounds and
   songs. Or add your own sounds one at a time.
6. Say one of your trigger words. Try **"lasers"**. Say **"quiet"** to fade
   everything out — including the full songs.

The full manual lives in **[guide.html](guide.html)** — also reachable from the
⚙️ settings inside the app (❓ User Guide).

To stop it: close the TriggerWord window.

**To update later:** double-click `update-triggerword.bat` — it fetches the
latest version and replaces the app files. Your sounds and settings live in
your browser, not this folder, so updates never touch them.

> **No Python?** Install it from [python.org](https://www.python.org/downloads/)
> and tick **"Add Python to PATH"** during setup. Nothing else is needed — the
> app does not use any Python packages.

### Why does it need a browser at all?

TriggerWord is a web page that runs on your own machine. There is no website, no
cloud, no sign-in. The little black window is a file server handing the page to
your browser and nothing more.

---

## What it does

| | |
|---|---|
| **Listens** | Uses your browser's built-in speech recognition. No AI model to download. |
| **Plays sounds** | One or many per trigger word, chosen at random if you add several. |
| **Levels sounds** | Measures each sound once and turns down the loud ones so nothing startles anyone. |
| **Remembers** | Your pack, triggers, shortcuts and favourites persist between sessions. |
| **Backs up** | One file containing everything — sounds, triggers, settings, shortcuts, trims. |
| **Routes audio** | Pick which output device sounds play to — a virtual cable for streaming, for example. |

---

## Levelling — why your sounds stop being startling

Soundboards collect clips from everywhere, and those clips are at wildly
different volumes. One is a quiet clip from a film; the next is a phone
recording that peaks into distortion. Played back to back, the second one hurts.

TriggerWord measures every sound once when you add it, then **turns the loud
ones down** so they sit closer together. Nothing is boosted, and nothing clips.

If a particular sound still isn't right, each one has a **trim slider**
(±12 dB) and an **auto** button to put it back.

The honest limitation: because levelling is applied through the audio element's
own volume, sounds can only be turned **down**, never up. Everything therefore
ends up a little quieter overall — turn your master volume up to compensate.
This was a deliberate trade so that **output-device routing keeps working**,
which matters if you send soundboard audio to a virtual cable for streaming.

---

## Backups — read this once

Your sounds live in your browser's storage. That is normally fine, but browsers
can be cleared, and profiles can be reset.

**Use "Export backup (everything)".** It writes a single ZIP containing your
sounds, triggers, shortcuts, favourites, settings and volume trims. Keep it
somewhere that isn't your browser.

"Import backup" puts it all back.

That backup ZIP is also a normal soundpack, so older versions of TriggerWord can
still open it — they just ignore the extra settings.

---

## Advanced install

If you want the FastAPI server instead of the simple one — it adds a WebSocket
endpoint used by an older Whisper-based transcription path:

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python local_server.py
```

Be aware this pulls in **torch and openai-whisper**, which are large downloads.
The soundboard itself does not need them — trigger detection runs in the
browser. Most people should use the quickstart above.

---

## Requirements and limits

- **Chrome or Edge.** Speech recognition and output-device selection are both
  Chromium features. Firefox and Safari will not work properly.
- **A microphone**, and permission granted to the page.
- **Windows** for the `.bat` launcher; on macOS or Linux run
  `python3 -m http.server 8002` in the project folder and open
  `http://localhost:8002`.

---

## Troubleshooting

**The device dropdowns are empty.**
Microphone permission was never granted. Open
`chrome://settings/content/microphone`, add `http://localhost:8002` under
*Allowed*, and restart. If you launch the app in a window with no address bar,
there is no padlock icon to click — this is the way to fix it.

**Nothing happens when I speak.**
Check the microphone dropdown is set to the mic you are actually using, and that
the page says it is listening. Speech recognition needs a moment of clear speech;
it will not catch a single muttered syllable.

**Sounds play to the wrong device.**
Set the output device in the app, not just in Windows. Each sound is routed
individually.

**I lost my soundpack.**
Import your backup ZIP. If you don't have one, make one now — see Backups above.

---

## Development

```bash
node --test        # 28 tests, no dependencies to install
```

Persistence and levelling logic lives in `persistence.js` as pure functions with
no DOM or storage access, which is what makes it testable outside a browser. All
I/O stays in `index.html`.

---

## Support

TriggerWord is free, part of the [Hopzle Toolkit](https://hopzle.com), made by
[SCARYLASERS](https://www.youtube.com/@ScaryLasers). If it made your stream
funnier, tips keep the toolkit growing: **[ko-fi.com/scarylasers_](https://ko-fi.com/scarylasers_)** ☕

[YouTube](https://www.youtube.com/@ScaryLasers) ·
[Twitch](https://www.twitch.tv/scarylasers) ·
[TikTok](https://www.tiktok.com/@scarylasers) ·
[Instagram](https://www.instagram.com/scarylasers_) ·
[X](https://x.com/ScaryLasers) ·
[Reddit](https://www.reddit.com/user/scarylasers/)

## License

**GPL-3.0** — see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).

Use it, fork it, build on it. If you distribute your version — free or paid —
you have to publish its source under the same licence, so nobody can take
TriggerWord closed-source. The name and the artwork stay mine; give your fork
its own.

The starter-pack songs are original SCARYLASERS tracks, included for personal
soundboard use and not covered by the code licence.
