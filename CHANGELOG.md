# Changelog

Versioning starts here. Everything before 1.0.0 was the wild west — see git
history if you enjoy archaeology.

When releasing: bump `version` in `package.json` and `APP_VERSION` in
`index.html`, add an entry below, tag `vX.Y.Z`, push the tag, publish a GitHub
Release.

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
