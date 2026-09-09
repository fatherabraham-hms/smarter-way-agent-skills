---
name: media-disk-space-archiver
description: >-
  Find large local media not yet on an external archive drive, verify a
  candidate list with the user, optionally compress oversized video with ffmpeg
  for a chosen screen size, then move approved files to the archive. Use when
  the user wants to free disk space by archiving media, reconcile local vs
  external media, or compress huge videos for TV/monitor viewing before archive.
disable-model-invocation: true
metadata:
  requires:
    bins: []
---

# media-disk-space-archiver

Free space on a personal computer by finding large local media that is **not**
already on an external archive volume, verifying candidates, optionally
compressing oversized video for a target screen, then moving only what the user
approves.

Works on **anyone’s** computer: ask for (or detect) the archive volume, home
scan roots, size floor, and **target screen size** — never hard-code one user’s
paths or a fixed display size.

## Inputs (collect before mutating)

Ask only for what is missing. Prefer one question at a time.

| Input | Required | Notes |
|-------|----------|-------|
| Archive volume | Yes | Mount path or volume name (e.g. `/Volumes/My Media Archive`, `D:\Media Archive`, `/mnt/media-archive`) |
| Local scan roots | Default OK | Default: the user’s home directory. Allow extras (e.g. other disks) if named. |
| Minimum size | Default OK | Default: **50 MB** for discovery; present ≥**100 MB** in the main verification table unless the user asks otherwise. |
| Target screen size | Yes before compress | Diagonal inches and/or explicit max resolution. Used only if compressing. |
| Compress before archive? | Ask if unclear | Default when files are multi‑GB camera/screen originals: offer compress. |

If the archive is not mounted, **stop** and ask the user to attach/mount it.
Do not invent an archive path.

## Target screen → encode ceiling

Before compressing, resolve **max output resolution** from the user’s screen
size (or an explicit resolution they give). The goal is sharp on that display
without keeping unnecessary 4K bulk.

| Target screen (diagonal) | Default max resolution | Notes |
|--------------------------|------------------------|-------|
| Phone / small tablet (≤10″) | 1280×720 | |
| Laptop / desktop monitor (11–32″) | 1920×1080 | |
| TV / large display (33–65″) | 1920×1080 | Default for a living-room TV; still sharp without 4K |
| Very large TV / projector (66–85″) | 2560×1440 | Use 1080p if the user prioritizes size over sharpness |
| Cinema / giant / “keep 4K” | 3840×2160 | Only when the user asks for 4K or names a huge screen **and** wants fidelity |

Rules:

1. If the user gives an explicit resolution (e.g. “1080p”, “1440p”), **that wins**.
2. Never **upscale**. If the source is already ≤ the ceiling, keep source dimensions.
3. Confirm the chosen ceiling + encode preset with the user before the first
   encode (a single test file is enough approval to proceed after they like it).

## Workflow

Copy and track:

```text
media-disk-space-archiver:
- [ ] 1. Confirm archive mounted + free space
- [ ] 2. Index archive media (basename + bytes + path)
- [ ] 3. Scan local media ≥ min size (exclude archive + junk trees)
- [ ] 4. Diff → write local markdown report (no moves yet)
- [ ] 5. User verifies / edits the list
- [ ] 6. Optional: install ffmpeg + compress for target screen
- [ ] 7. Move only approved files onto the archive
- [ ] 8. Report space freed / archived / skipped
```

### 1. Confirm archive mounted + free space

On the user’s machine, locate the archive volume and report capacity:

```bash
# macOS example
ls -la /Volumes/
df -h "/Volumes/<Archive Name>"

# Linux example
lsblk -f; df -h /mnt/<archive>

# Windows (PowerShell)
Get-PSDrive -PSProvider FileSystem
```

Record: mount path, used/free space, top-level layout. If free space is less
than the candidate set, warn before any move or batch compress.

### 2. Index archive media

Build an index of media already on the archive:

`basename|size_bytes|full_path` (one row per file).

Include (case-insensitive) at least:

- Video: `mp4, mov, m4v, avi, mkv, wmv, flv, webm, mpg, mpeg, 3gp, mts, m2ts, vob, hevc, ts`
- Audio: `mp3, wav, aiff, aif, flac, m4a, aac, wma, ogg, alac`
- Large stills/raw when clearly personal media: `heic, dng, cr2, nef, arw, tif, tiff`

### 3. Scan local media

Scan the agreed roots on the **local** disk only:

- **Exclude** the archive mount and other `/Volumes/*` (or equivalent) paths from
  the “local” set.
- Prune noisy trees: caches, Trash, `node_modules`, `.git`, build artifacts,
  `DerivedData`, package manager caches.
- Prefer user media areas when home is huge: Documents, Downloads, Movies,
  Music, Desktop, Pictures (note OS privacy limits).
- Respect permission denials (Photos libraries, iCloud). Report them as caveats;
  do not demand Full Disk Access unless the user wants those areas scanned.

### 4. Diff → write local markdown report (read-only)

Matching rule — a local file is **already on archive** only if **both**:

1. Same **basename**, and
2. Same **exact size in bytes**

Otherwise it is a **candidate**:

- Basename missing on archive → candidate
- Basename present, size differs → candidate, flag **SIZE MISMATCH**

**Required:** write the full disk-check / verification output to a **markdown
file on the user’s local machine** before any move or destructive action. Do
not leave the list only in chat.

#### Report path

Default (create parent dirs if needed):

```text
~/Documents/media-archive-reports/media-not-on-archive-YYYY-MM-DD.md
```

- Prefer that path unless the user names another local folder.
- Use the local date in the filename.
- Also OK: Desktop, Downloads, or next to the archive mount — but it must be a
  real file on **their** computer, not only on a remote agent sandbox.
- Optionally write a companion TSV/CSV of the same rows for sorting/filtering.

#### Report contents (required sections)

Mirror this structure (adapt names/paths to the current machine):

1. **Title** — e.g. `Large local media NOT on "<Archive Name>"`
2. **Header meta** — scan date/time + timezone, machine label, user home,
   explicit “read-only / nothing moved”
3. **Archive confirmed** — mount path, `df`-style capacity, top-level layout
   under the archive (folder ≈ size / file counts when practical)
4. **Matching method** — basename + exact bytes rule; size-mismatch behavior
5. **Local scan scope** — roots scanned, prunes, media extensions, privacy
   / permission gaps
6. **Summary table** — local ≥ min size found; already on archive (count +
   bytes); candidates (count + bytes); candidates ≥100 MB; size-mismatch count
7. **Already on archive (skipped)** — each file: human size, bytes, filename,
   local path, archive path
8. **Size mismatches** — local path + sizes seen on archive for that basename
9. **Candidates NOT on archive** — markdown table, **largest first**, all
   files ≥100 MB (or the user’s threshold). Columns:

   `| # | Size | Bytes | Filename | Full local path | Notes |`

10. **Caveats** — TCC/privacy blocks, duplicates, collisions, free-space vs
    candidate total

In chat, send a short TLDR (summary + top ~10 largest) and **point at / attach
the local markdown file** so the user can review the full list on disk.

**Do not move, delete, or overwrite anything in this step.**

### 5. User verifies / edits the list

Wait for explicit approval of which files to compress and/or move.
Offer sensible subsets (largest N, everything ≥100 MB, folder groups) but
never proceed on an unanswered prompt — if they skip the question, keep the
list and ask only when the next action needs a decision.

### 6. Optional compress for target screen

When candidates are huge (multi‑GB) and the user wants smaller viewable copies:

1. Run the sibling skill **`install-ffmpeg`**
   (`.agents/skills/install-ffmpeg/SKILL.md`) — or follow those steps
   inline — so `ffmpeg` / `ffprobe` exist on the user’s machine.
2. Resolve max resolution from **Target screen → encode ceiling** above.
3. Probe sources (`ffprobe` or OS metadata) for width, height, duration, codec.
4. Propose this default preset (override only if the user asks):

| Setting | Default |
|---------|---------|
| Video codec | HEVC / H.265 (`libx265` or hardware encoder if reliably available) |
| Quality | CRF **23** (visual quality over target bitrate) |
| Scale | `scale=w='min(max_w,iw)':h='min(max_h,ih)':force_original_aspect_ratio=decrease` (never upscale) |
| Audio | AAC **160 kbps** |
| Container | `.mp4` (faststart) |
| Originals | **Keep** until the user approves the compressed result |

Example shape (adjust `max_w` / `max_h` from the screen table):

```bash
ffmpeg -i "$SRC" \
  -c:v libx265 -crf 23 -preset medium -tag:v hvc1 \
  -vf "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease" \
  -c:a aac -b:a 160k \
  -movflags +faststart \
  "$DST"
```

5. **Test-encode one file first.** Show before/after size and resolution.
   Only batch after the user likes the test.
6. Write outputs beside the source or into a clear staging folder
   (`*-archive-compressed/` or similar). Never replace the original in place
   unless the user explicitly asks.
7. After approval, the compressed files (not necessarily the originals) are
   what get moved in step 7 — confirm which with the user.

Hardware encoders (`hevc_videotoolbox`, `hevc_nvenc`, etc.) may be used when
they clearly work and quality is acceptable; fall back to `libx265` on failure.

### 7. Move approved files onto the archive

Only after explicit approval:

1. Choose destination folders under the archive (mirror local theme, year, or
   user-specified layout — ask if unclear).
2. Prefer `mv` within the same machine when the archive is a mounted volume;
   use copy + verify + delete only when a cross-filesystem move is safer.
3. After each move (or small batch), verify the destination file exists with
   the expected size.
4. Do **not** delete local originals of compressed workflows until the user
   confirms the archive copy is good.
5. Skip conflicts (same basename+size already there). On basename conflict with
   different size, stop and ask — do not overwrite.

### 8. Final report

Short summary:

1. Archive path + free space after
2. Files moved / compressed / skipped (counts + bytes)
3. Local space roughly freed (if originals removed)
4. Remaining candidates (if any)
5. Caveats

## Safety rules

- Always persist the verification list as a local `.md` on the user’s machine
  (step 4); chat-only lists are not enough.
- Read-only until the user approves the verification list.
- No deletes of originals without an explicit OK.
- No overwrite of differently sized archive files.
- Keep sensitive paths in reports factual; do not broadcast them beyond the user.
- If free space on the archive cannot hold the approved set, stop and say so.

## Out of scope

- Cloud backup services (iCloud, Google Photos sync) as the archive target
  unless the user names them
- Editing video content (cuts, titles, color)
- Installing HandBrake or other GUIs unless requested
