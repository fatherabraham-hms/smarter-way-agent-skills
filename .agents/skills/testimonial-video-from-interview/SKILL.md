---
name: testimonial-video-from-interview
description: >-
  Use this when turning a recorded interview (audio plus transcript) into a
  short multi-part testimonial video: writing the shot plan, cutting audio
  clips, pairing stills, generating missing stills, rendering parts, stitching
  them, and adding music.
---

# Testimonial video from an interview recording

Produce a vertical testimonial in parts, then a stitched full video, then a version with music. Run one stage at a time and wait for the user to review it before the next stage.

Do the work on the machine that has the media and ffmpeg. When you are on a different machine, copy the inputs there, process them, copy the outputs back into the interview folder, and delete stray copies that landed in the home directory.

Keep the recording, transcript, stills, and renders inside the interview folder. These are recordings of a real person.

## Tools

Check before stage 1. Install what is missing, then continue.

| Tool | Use | If it is missing |
|---|---|---|
| `ffmpeg` and `ffprobe` | Cuts, Ken Burns, stitch, mix | Run the `install-ffmpeg` skill when it is available. Otherwise install ffmpeg and stop if you cannot. |
| Word-level speech-to-text | Clip in and out points. Transcript timestamps are too coarse. | Install `faster-whisper` (`pip install faster-whisper`). Any local model with word timestamps is fine; `small` is enough. |
| ImageMagick `montage` | Contact sheet of approved stills | Skip the sheet and review the stills one by one. |
| An image generator that accepts a reference photo | New stills when the shot list would repeat an image | Stop and ask the user for stills. Do not invent a face without a reference photo. |

```bash
command -v ffmpeg ffprobe montage
ffmpeg -version | head -1
```

Word timestamps:

```python
from faster_whisper import WhisperModel
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, _ = model.transcribe("recording.m4a", word_timestamps=True)
for segment in segments:
    for word in segment.words:
        print(f"{word.start:.3f}\t{word.end:.3f}\t{word.word}")
```

## Interview folder

Create any directory that is missing.

```text
interview/
  raw/                          recording (.m4a) and transcript (.txt)
  video-scripts/                the shot plan
  audio-clips/                  cut clips
  audio-clips/rejected/         clips the user rejects
  video-stills/<person>/        approved stills
  video-stills/<person>/rejected/
  0_final/                      renders
```

A music file, when the user supplies one. If an attachment will not open, look in `~/Downloads` for a file with the same name, size, and time, and tell the user which file you used.

## Standing rules

Confirm these on the project, and use them when the user has not said otherwise.

- Three parts. Each part is usually 20–40 seconds. A part may run longer when the user wants a sentence kept whole.
- No captions, subtitles, lower thirds, or interviewer question cards. Text that is already inside a still is fine.
- Never use a file from `rejected/`, and do not rebuild rejected content another way.
- One still per shot. Each still appears once in the whole video. A wide crop and a tight crop of the same image count as the same still.
- A phone screen, a bank screen, or another sensitive image appears once at most.
- Each approved portrait appears once. Avoid two face stills in a row. Fill the other shots with objects and details that match the line: hands, a wallet, a statement, a letter, a calendar.
- Intro and title cards play silent, with the drone only, never under the voice. Hold each one for `max(3 seconds, word count / 3 + 1.25 seconds)`.
- An object still that has text baked in may sit under the sentence it illustrates. Hold it about 5–9 seconds, longer when that one image covers a whole beat, so the text can be read.
- Voice shots run about 3–6 seconds and cut on pauses between phrases.
- Leave out details the user calls irrelevant or unclear, such as ages, side anecdotes, or confusing phrases, and edit the plan to match.
- Text inside a generated still is fictional, such as a made-up bank name, unless the user supplies the real text. A real logo or wordmark only goes on a still the user has approved.

## Plan format

Write the plan to `video-scripts/<name>.txt`. The shape is in [references/example-plan.txt](references/example-plan.txt). Each part is a markdown table:

| Time | Visual | On-screen text | Audio (verbatim) |
|---|---|---|---|

- Time is `m:ss.s–m:ss.s` from the start of that part.
- Visual names the still file, the crop, and the move (`gentle push`, `slow push`).
- On-screen text is `—` when the words are baked into the still, or `— (baked in)` on a text card. Do not plan extra captions.
- Audio quotes the transcript verbatim. A new clip is `` `<part><letter>_<short-slug>` starts m:ss.s ``, for example `` `01d_card-rejected` starts 0:12.75 ``. A continuation row has the quote only.
- Silent rows say `drone`. A row that drops the bed says `drone killed`.
- Under the table, one line: `Runtime: <seconds>s.` Then any hold, gap, or reading-time note.

The first draft is `<name>.txt`. After the user rejects clips, write `<name>-v2.txt` and leave the original alone. Later changes update that same v2 file.

## Stage 0: Write the plan

1. Read the transcript. Pick the lines that carry the story. Drop filler, side anecdotes, and anything the user has flagged.
2. Draft three parts. Open with silent intro cards when the user wants a title. Then the voice, cut on pauses.
3. Assign one still per shot. Where no still exists, name the shot and mark it `NEEDED`, with one sentence describing the picture.
4. Apply the reading-time rule to every text card and write those durations into the table.
5. Stop. Show the plan and the `NEEDED` list. Cut audio only after the user accepts the lines.

## Stage 1: Cut audio clips

1. Build a word-timestamp table for the recording.
2. For each clip in the plan, find those exact words. Pad the cut by about 80–150 ms on each side and fade 20–40 ms so the edit does not click. Clamp the pad to the file.

```bash
ffmpeg -y -i raw/recording.m4a -ss START -to END \
  -af "afade=t=in:st=0:d=0.03,afade=t=out:st=FADE_OUT:d=0.03" \
  -c:a aac -b:a 192k audio-clips/01d_card-rejected.m4a
```

`FADE_OUT` is the clip duration minus 0.03 seconds. `START` and `END` are the padded times.

3. Trim only on word boundaries: drop a filler word, splice out laughter, or end on a given word. Run speech-to-text on the result and confirm the words that remain.
4. Copy the clips into `audio-clips/` and report each filename and duration.

## Stage 2: Revise the plan

When the user rejects clips, move those files to `audio-clips/rejected/`. Update `<name>-v2.txt`: remove the rejected lines, re-time the shots so each still covers its audio with a little room, and keep one still per shot. Record a drone-killed moment on the lines the user wants bare.

## Stage 3: Fill gaps in the stills

1. Contact sheet of the approved stills, excluding `rejected/`:

```bash
montage video-stills/<person>/*.{png,jpg,jpeg} \
  -tile 4x -geometry 240x426+4+4 -label '%f' contact-sheet.png
```

2. For every `NEEDED` shot, and anywhere the plan would repeat a still, propose a new still in one sentence. Wait for a yes before generating.
3. Generate at 9:16, using an existing photo of the subject as the reference so the face and the style match. Show the image before using it. Regenerate any face that does not match.
4. Copy approved stills into `video-stills/<person>/`. Move files that arrived in the home directory into that folder and delete the stray copies.
5. Stop for a stills sanity check. Tell the user the absolute path of `video-stills/<person>/` and ask them to open that folder and approve the set that will be used. `rejected/` is out of the video. Do not render until they approve. Move anything they reject into `video-stills/<person>/rejected/` and replace it before asking again.

## Stage 4: Render each part

Default picture: 1080×1920, 30 fps, H.264 CRF 18, AAC 192k, `+faststart`.

Keep one shot list for the part, with duration, still, zoom end, focus, and audio start. A change is one edit and a rerun. Zoom ends at 1.03–1.08, or up to 1.14 on a long slow shot. Focus `FX` and `FY` are 0–1; `0.5` is the center.

Render each shot from a single still. `FRAMES` is `round(seconds × 30)`.

```bash
ffmpeg -y -loop 1 -framerate 30 -i STILL.png \
  -vf "scale=2160:3840:force_original_aspect_ratio=increase,crop=2160:3840,zoompan=z='1+(ZOOM_END-1)*on/FRAMES':x='max(0,min(iw-iw/zoom,FX*iw-iw/zoom/2))':y='max(0,min(ih-ih/zoom,FY*ih-ih/zoom/2))':d=1:s=1080x1920:fps=30" \
  -frames:v FRAMES -c:v libx264 -pix_fmt yuv420p -crf 18 -an shot.mp4
```

Join shots with a hard cut, or with a 0.8 s dissolve. A dissolve shortens the timeline, so render the outgoing shot 0.8 s longer than the plan and set the offset to the planned shot length. Two shots where the first planned length is `A`:

```bash
ffmpeg -y -i shotA.mp4 -i shotB.mp4 \
  -filter_complex "[0:v][1:v]xfade=transition=fade:duration=0.8:offset=A[v]" \
  -map "[v]" -c:v libx264 -pix_fmt yuv420p -crf 18 -an part-video.mp4
```

Chain the same way for more shots. Each offset is measured on the stream going into that `xfade`.

Place each voice clip with `adelay` (milliseconds, both channels) over a silent bed of the part length. `amix` uses `normalize=0` so it does not turn the voice down as clips come and go.

```bash
ffmpeg -y -i part-video.mp4 \
  -f lavfi -t PART_LEN -i anullsrc=r=48000:cl=stereo \
  -i audio-clips/01d_card-rejected.m4a \
  -filter_complex "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,adelay=12750|12750[a1];[1:a][a1]amix=inputs=2:normalize=0:duration=first:dropout_transition=0[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -movflags +faststart \
  0_final/part1_the-freeze.mp4
```

Add one `adelay` input per clip and raise `amix=inputs`. A drone is another input on that same mix: one low bed for the whole video, volume `1` except on the intervals the plan marks `drone killed`, where it goes to `0` across a short fade. Skip the drone when the plan has none.

Save the three part videos as `0_final/part1_<slug>.mp4`, `0_final/part2_<slug>.mp4`, and `0_final/part3_<slug>.mp4`. Pull a few frames, or a contact sheet of frames, and check for a repeated still, a rejected image, or stray text before you hand them over.

Stop for a flow check. Give the user the absolute path of `0_final/` and the three part filenames. Ask them to watch all three, in order, and approve the flow. Do not stitch until they approve. If they want a change, revise that part and ask again.

## Stage 5: Stitch

Start only after the user has approved the three part videos.

Join the parts with about 0.5 s of fade through black. The offset is the outgoing part's duration minus 0.5.

```bash
ffmpeg -y -i 0_final/part1_the-freeze.mp4 -i 0_final/part2_the-cost.mp4 \
  -filter_complex "[0:v][1:v]xfade=transition=fadeblack:duration=0.5:offset=OFFSET[v];[0:a][1:a]acrossfade=d=0.5[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -pix_fmt yuv420p -crf 18 -c:a aac -b:a 192k \
  -movflags +faststart 0_final/<person>_full.mp4
```

Chain further parts the same way. Report the total length and the timestamp where each part starts.

## Stage 6: Music

1. When the user asks for options, offer about three royalty-free tracks and name the license. One source that fits is Kevin MacLeod at incompetech.com, CC BY 4.0. Let the user choose.
2. Mix the track under the voice of `<person>_full.mp4`:
   - When the track is shorter than the video, loop it and crossfade the join at a quiet point (`acrossfade`) so the loop is not a hard cut.
   - Duck it under speech with `sidechaincompress`, keyed on the voice, so it lifts a little in the gaps.
   - Fade in at the start and out over the last 2–3 s.
   - Normalize to about −14 LUFS.

```bash
ffmpeg -y -i 0_final/<person>_full.mp4 -i music.mp3 \
  -filter_complex "[0:a]asplit=2[voice][sc];[1:a]aloop=loop=-1:size=2000000000,atrim=0:VIDEO_LEN,afade=t=in:st=0:d=1,afade=t=out:st=FADE_AT:d=2.5[bed];[bed][sc]sidechaincompress=threshold=0.05:ratio=6:attack=20:release=300[ducked];[voice][ducked]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
  -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -movflags +faststart \
  0_final/<person>_full_w_music.mp4
```

`FADE_AT` is the video length minus 2.5 seconds. Replace the `aloop` branch with the file itself when the track already covers the video.

3. Run speech-to-text on the mix and confirm the voice is still the same words. Listen to the loudest sections. If you cannot listen, say so and ask the user to.
4. Save `0_final/<person>_full_w_music.mp4`. For an incompetech track the credit line is: `Music: "<title>" by Kevin MacLeod (incompetech.com), licensed under Creative Commons By Attribution 4.0 (https://creativecommons.org/licenses/by/4.0/)`. For any other track, give the credit line that license requires.

## Delivery

At the end of each stage, report what changed, the file paths, and the durations. Name any substitution, such as a different music file. Offer one or two specific tweaks, then stop and wait.
