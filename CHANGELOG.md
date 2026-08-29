# Changelog

Versioning starts here. Everything before 1.0.0 was the wild west — see git
history if you enjoy archaeology.

When releasing: bump `version` in `package.json` and `APP_VERSION` in
`index.html`, add an entry below, tag `vX.Y.Z`, push the tag, publish a GitHub
Release.

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
