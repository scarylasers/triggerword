# Changelog

Versioning starts here. Everything before 1.0.0 was the wild west — see git
history if you enjoy archaeology.

When releasing: bump `version` in `package.json` and `APP_VERSION` in
`index.html`, add an entry below, tag `vX.Y.Z`, push the tag, publish a GitHub
Release.

## 1.2.0 — 2026-08-30

Your remote works when you are looking at something else.

- **A remote or stream deck now fires triggers while the window is minimised**,
  or while you are in a game, a DAW, or anything else. Until now TriggerWord
  only heard those buttons when its own window had focus, which rather defeated
  the point of having a remote. It claims F13–F24 for as long as it is open, so
  those keys reach the soundboard instead of whatever you are typing in. Nothing
  else on your keyboard is touched.
- **The app icon is the logo instead of the wordmark.** The tab icon — and the
  icon Windows shows for the app window in the taskbar — used to be the full
  TriggerWord lettering, which is an unreadable smudge at 16 pixels. It is now
  the bunny-and-bullseye mark. The wordmark still heads the window and the guide.
- **The window uses its full width**, and the gap above the tabs is closed up.
- **Tighter layout**: content follows the header, and the microphone button sits
  next to the transcript.

## 1.1.2 — 2026-08-29

Mostly about making it obvious what the app is doing.

- **It now says when it isn't listening.** The status used to read "Ready",
  which looks the same as working. It says *Not listening — press ▶ to start*,
  and the play button pulses until you do. While running it says
  *Transcribing*.
- **Play, stop and the microphone button sit beside the transcript**, where
  you look to see whether it heard you. Pause and resume are gone — start and
  stop say the same thing with one less state.
- **A 🎤 button opens Chrome's microphone picker.** Chrome, not TriggerWord,
  chooses the microphone it transcribes, and the app window has no address bar
  to reach that control from. This opens a tab where you can set it; Chrome
  remembers it per address.
- **The app's own microphone picker is gone.** It selected a device for
  recording while Chrome independently selected the one being transcribed —
  two settings that could disagree. Everything now follows Chrome.
- **The level meter is gone.** It never actually rendered, and had it worked it
  would have metered a different device from the one being transcribed.
- **The header folds away** to just the logo, transport and transcript, with
  the toggle tucked on its bottom-right edge. Tabs, titles and spacing
  tightened; section titles are left-aligned.
- **Long speech wraps and scrolls** instead of running off the end.
- **Corrected the privacy claim.** The README said audio never leaves your
  machine. It does: speech recognition is Chrome's, and unless Chrome has
  on-device models it sends the audio to Google. Your sounds, triggers and
  settings never leave.

## 1.1.1 — 2026-08-29

Fixes found while testing 1.1.0.

- **Sounds no longer play over each other.** Starting a sound now stops
  whatever was already playing, whichever way it was started — clicking a
  card, a favourite, a shortcut or a trigger. Previously only spoken
  triggers choked, so two songs could run at once.
- **Tabs and favourites survive an export.** The ZIP soundpack export
  dropped both, so a shared pack arrived as a flat, unsorted wall.
- **Tab assignment moved into the edit (pencil) popout**, off the card face.
- **Picking a microphone now actually opens it** and restarts listening,
  instead of only remembering the choice, and says so if the device can't
  be opened.
- **The server no longer dies on its own log output.** Run hidden with its
  output redirected, the first emoji it logged raised an encoding error and
  killed it — which stopped transcription in the advanced setup.
- Starter pack is now SCARYLASERS recordings and songs throughout.

## 1.1.0 — 2026-08-28

- **Windows installer** — `TriggerWord-Setup-1.1.0.exe`. Bundles everything
  needed, including Python, so there is nothing to install first and nothing
  to unzip. Desktop and Start Menu shortcuts, and a normal uninstaller.
- **Tabs** — organize the board into pages. All / Favorites / Recordings are
  built in; make your own with ➕ and move any card into one with 🗂️. Tab
  assignments ride along in soundpack and backup exports.
- **Audio Routing Guide** (`routing.html`) — Voicemeeter recipes for letting
  teammates hear your soundboard, and for letting their voices trigger it,
  with a signal-flow diagram and troubleshooting.
- **Dark theme reworked** — warm gold tones instead of a harsh inversion;
  logos, card art and hearts keep their true colors.
- Bigger header logo, and it now opens a menu with help, socials and Ko-fi.
- Five-across card grid, "use responsibly" reminders, and an Advanced section
  in the user guide covering recording, time-shift and global hotkeys.

## 1.0.0 — 2026-08-28

First versioned release. The state of the world:

- **Voice triggers** via browser speech recognition (zero-dependency
  quickstart) or a local Whisper server (advanced install)
- **Starter pack** of original SCARYLASERS SFX and songs, with favorites
- **Stop word "quiet"** / 🔇 button / assignable control shortcut — fades out
  everything playing, works mid-song
- **Keyboard shortcuts** for triggers and controls, with a cooldown-bypass
  toggle; a new press chokes the playing sample instead of layering
- **Global hotkeys** (F13–F24) in full mode — triggers fire without window
  focus, built for macro pads and BLE remotes
- **Levelling** — every sound measured once and tamed, with per-sound trim
- **One-file backups** — sounds, triggers, favorites, shortcuts, settings
- **Quick Record and Time-Shift capture** for making drops on the spot
- **Dark theme**, yellow app frame, installable as a PWA
- **Desktop splash** — Looney-Tunes iris with the animated logo
- **Self-managing lifecycle** in full mode: hidden server and hotkey router,
  everything shuts down when the last app window closes
- **Themed user guide** (`guide.html`), linked from settings
