---
name: install-ffmpeg
description: >-
  Install ffmpeg (and ffprobe) on the user's computer when missing. Use when a
  workflow needs ffmpeg, the user asks to install ffmpeg, or media compress /
  probe / convert steps fail because ffmpeg is not on PATH.
disable-model-invocation: true
metadata:
  requires:
    bins: []
---

# install-ffmpeg

Ensure `ffmpeg` and `ffprobe` are available on the **user's computer** (the
machine where the media lives). Portable across macOS, Linux, and Windows.

## When invoked

Treat invocation as permission to check for `ffmpeg`/`ffprobe` and install them
with the platform package manager when missing. Confirm with the user before any
install that needs elevated privileges or a long download if they have not
already asked to install ffmpeg.

## Workflow

Copy and track:

```text
install-ffmpeg:
- [ ] 1. Detect OS + package manager
- [ ] 2. Check existing ffmpeg / ffprobe
- [ ] 3. Install if missing
- [ ] 4. Verify on PATH
```

### 1. Detect OS + package manager

On the user's machine:

```bash
uname -s
command -v brew apt-get dnf pacman winget choco 2>/dev/null
```

Map:

| Platform | Preferred installer |
|----------|---------------------|
| macOS | Homebrew (`brew`) |
| Debian/Ubuntu | `apt-get` / `apt` |
| Fedora/RHEL | `dnf` or `yum` |
| Arch | `pacman` |
| Windows | `winget` (else Chocolatey) |

If no supported installer is found, stop and tell the user how to install
manually from https://ffmpeg.org/download.html — do not invent a custom build.

### 2. Check existing ffmpeg / ffprobe

```bash
command -v ffmpeg
command -v ffprobe
ffmpeg -version | head -2
ffprobe -version | head -1
```

If both resolve and `ffmpeg -version` succeeds, **skip install**. Report the
path and version, then stop successfully.

### 3. Install if missing

Run **one** of the following on the user's machine (not on a remote sandbox
unless that is where the media will be processed).

**macOS (Homebrew):**

```bash
brew install ffmpeg
```

If `brew` is missing, stop and point the user at https://brew.sh — do not curl
installer scripts unless they explicitly ask.

**Debian / Ubuntu:**

```bash
sudo apt-get update && sudo apt-get install -y ffmpeg
```

**Fedora:**

```bash
sudo dnf install -y ffmpeg
```

**Arch:**

```bash
sudo pacman -Sy --noconfirm ffmpeg
```

**Windows (winget):**

```bash
winget install --id Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements
```

**Windows (Chocolatey), only if winget is unavailable:**

```bash
choco install ffmpeg -y
```

Notes:

- Prefer a full build that includes `ffprobe` (Homebrew and distro packages do).
- Do not compile from source unless the user asks.
- Long installs: run in the background, keep the user posted, verify when done.

### 4. Verify on PATH

```bash
command -v ffmpeg && command -v ffprobe
ffmpeg -version | head -2
ffprobe -version | head -1
```

On success, report:

1. Install method used (or “already present”)
2. Absolute paths of `ffmpeg` and `ffprobe`
3. Version line

On failure, report the exact error and the platform-specific recovery step.
Do not claim success without a working `ffmpeg -version`.

## Out of scope

- Choosing video encode presets (that belongs to the calling skill)
- Editing or deleting media files
- Installing GUI apps (HandBrake, etc.) unless the user asks
