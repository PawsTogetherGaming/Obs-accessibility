# OBS Studio Accessibility

An NVDA add-on that makes OBS Studio usable for blind streamers. It supplies missing labels and descriptions for unlabelled or jargon-named controls, adds quick-jump gestures so you can move between OBS's panels without falling into focus traps, and wraps the most common streaming actions in keyboard shortcuts.

This is an early public release — please report issues or send feedback so the next version can fix what bothers you most.

## Installation

1. Download the latest `.nvda-addon` file.
2. Open it. NVDA will prompt to install. Confirm and restart NVDA when asked.
3. The add-on activates automatically when OBS (`obs64.exe`) is the foreground window.

To verify it loaded: open OBS and press **NVDA+Shift+O** — you should hear "OBS accessibility add-on loaded, version 0.8.0".

## Quick-jump gestures

Press these in OBS's main window to land focus inside a specific dock or panel.

| Gesture | Destination |
| --- | --- |
| NVDA+Shift+1 | Scenes list (lands on the active scene) |
| NVDA+Shift+2 | Sources list (lands on the active source) |
| NVDA+Shift+3 | Audio Mixer (first volume slider) |
| NVDA+Shift+4 | Controls panel (Start Streaming, Recording, Virtual Camera) |
| NVDA+Shift+5 | Scene Transitions |
| NVDA+Shift+6 | Preview controls |

These work around two OBS quirks: the audio mixer is a Tab focus trap, and Qt's virtual list items in Scenes/Sources can't be focused via UIA — both are solved here so the keys always land you where you expect.

## Streaming and recording shortcuts

| Gesture | Action |
| --- | --- |
| NVDA+Alt+S | Toggle Start/Stop Streaming |
| NVDA+Alt+R | Toggle Start/Stop Recording |
| NVDA+Alt+P | Toggle Pause/Unpause Recording (only while recording) |
| NVDA+Alt+V | Toggle Start/Stop Virtual Camera |

Each one announces in past tense so you hear what just happened, e.g. *"Started recording"* or *"Recording paused"*.

## Settings dialog shortcuts

Open the Settings dialog with **NVDA+Alt+I**. Once it's open:

| Gesture | Action |
| --- | --- |
| NVDA+Alt+O | OK (save and close) |
| NVDA+Alt+A | Apply (save, leave open) |
| NVDA+Alt+C | Cancel (discard and close) |
| NVDA+Alt+D | Defaults (reset current page) |

The buttons are also reachable normally with Tab, but these let you commit or back out without hunting.

## Hotkeys settings page

OBS's hotkey list is unusual — the rows aren't keyboard-focusable at the system level, so Tab can't reach them. This add-on supplies its own row navigation when you're on Settings → Hotkeys:

| Gesture | Action |
| --- | --- |
| NVDA+Alt+Down arrow | Next hotkey row |
| NVDA+Alt+Up arrow | Previous hotkey row |
| NVDA+Alt+Home | First hotkey row |
| NVDA+Alt+End | Last hotkey row |

Each row's binding edit and the four buttons (Revert / Clear / Add / Remove) are spoken with the action's name, so you'll hear e.g. *"Revert Start Recording binding"* instead of an unnamed button.

## Volume slider announcement

When you focus a slider in the Audio Mixer and adjust it, the new dB value is announced as you change it. OBS's volume sliders fire UIA value-change events inconsistently, so this add-on polls the value while the slider has focus and speaks each change directly.

OBS's slider has an internal step finer than its 0.1 dB display precision, so two key presses per displayed dB step is normal — that's the slider, not the add-on.

## Settings dialog labels and descriptions

The Settings → Output → Advanced page is fully labelled and described:

- **Streaming sub-tab** — encoders, audio encoder, output rescale filter and resolution.
- **Recording sub-tab** — output type, recording path, format, video and audio encoder, rescale filter and resolution, custom muxer settings, automatic file splitting, audio track checkboxes (Track 1–6).
- **Audio sub-tab** — per-track audio bitrate and display name fields (Track 1–6).
- **Replay Buffer sub-tab** — Enable Replay Buffer, Maximum Replay Time.

Each control announces a short, plain-language description — what it does and what value to pick if you're unsure.

In addition, the **Encoder Settings** group below the recording options is now fully labelled. Every property (Rate Control, Bitrate, Keyframe Interval, Preset, Tuning, Multipass Mode, Profile, Max B-frames, Look-ahead, Custom Encoder Settings, and others depending on encoder) reads its visible label and a description, regardless of whether you're using NVENC, x264, AMF, or QuickSync.

## Other labelled controls

- Preview scaling combobox (main toolbar)
- Hotkey filter inputs (Settings → Hotkeys top bar): "Filter hotkeys by name", "Filter hotkeys by key binding", and "Clear hotkey filter".

## Customizing gestures

Every gesture listed above is a default — you can change, add, or remove any of them through NVDA's Input Gestures dialog.

1. Open OBS so the add-on is loaded.
2. Press **NVDA+N** to open the NVDA menu, then go to **Preferences → Input gestures**.
3. Find the **OBS Accessibility** category. All shortcuts the add-on provides are listed there.
4. Select the script you want to remap, click **Add** to assign a new gesture, or select an existing binding and click **Remove** to unbind it.
5. Click **OK** to save.

If you remove a default binding without adding a replacement, the script still exists — it simply has no key assigned. You can add one later from the same dialog.

The "OBS Accessibility" category only appears in the Input Gestures dialog while OBS is the foreground window. If you don't see it, switch to OBS first, then reopen the dialog.

## Troubleshooting

**Descriptions don't speak.** NVDA only reads object descriptions when "Report object descriptions" is enabled in NVDA → Preferences → Settings → Object Presentation. It's on by default.

**A specific control still reads as "edit" or "combo box" with no name.** That means we haven't covered it yet. Press **NVDA+Shift+I** while focused on that control — the inspector script writes detailed information to the NVDA log. Send the relevant log section as a bug report and that control can be labelled in the next release.

## Known limitations

- Settings pages outside Output (top-level Audio, Video, Advanced, etc.) are not yet covered. They speak with whatever labels OBS provides natively. Coverage will expand based on what users hit most.
- Tested against NVDA 2025.3.x and OBS Studio 30.x on Windows 11. Earlier OBS versions may have different control layouts.
- The dock-jump gestures assume the default dock layout. If you've heavily rearranged OBS's UI, some destinations may not be present.

## Changelog

### 0.8.1

- Added a "Customizing gestures" section to the readme — gestures are configurable through NVDA's Input Gestures dialog.
- Internal: hoisted `scriptCategory` to the AppModule class so all scripts appear under "OBS Accessibility" in Input Gestures with cleaner registration.

### 0.8.0 — first public release

Initial Add-on Store submission. Consolidates everything from the 0.7.x development line:

- Quick-jump gestures for all six main OBS panels.
- Streaming, recording, virtual camera, and pause shortcuts with past-tense announcements.
- Settings dialog button shortcuts (OK / Apply / Cancel / Defaults).
- Full keyboard navigation of the Hotkeys settings page, including row stepping with arrow keys.
- Volume slider value announcement during adjustment (polling-based, works around Qt UIA event gaps).
- Labels and descriptions for the entire Output → Advanced surface (Streaming / Recording / Audio / Replay Buffer sub-tabs and the Encoder Settings group).
- Generic resolution of OBSPropertiesView labels via UIA sibling walking, so encoder property rows speak across NVENC / x264 / AMF / QuickSync.
