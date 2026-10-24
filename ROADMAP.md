# Roadmap

What's planned for LineDrive. Nothing here is promised or dated; order is roughly the order of work.
Shipped features move to [CHANGELOG.md](CHANGELOG.md). Ideas and requests are welcome as issues.

## 4.0

### Sonarr handoff (done, unreleased)
When an episode finishes recording, LineDrive unmonitors it in Sonarr so Sonarr doesn't download it
too. Only the episode's monitored flag changes: nothing is imported or moved, and Sonarr doesn't
need to see the recordings folder. Episodes are matched by season/episode number, then air date,
then episode title, and a match whose episode title disagrees is ignored (an older show with the
same name, such as a rerun of the original vs. a revival).

### Comskip (done, unreleased)
Mark commercial breaks so media servers can skip them. Off by default. After a recording finishes,
LineDrive runs [Comskip](https://github.com/erikkaashoek/Comskip) on it and writes the breaks into
the file as chapters (the video itself isn't re-encoded or cut), plus a `.edl` beside it for Kodi.
Jellyfin 10.10+ can turn those chapters into skippable segments with its Chapter Segments plugin.
For Plex and other players that can't skip chapters, the breaks can be cut out instead; the uncut
original is kept in the recycle folder for a week in case Comskip got a break wrong.

### Multiple HDHomeRun boxes
Pool the tuners of more than one HDHomeRun. Today there's one tuner address, one channel lineup
and one tuner count, and the clash checks, recording, signal readings, status card and Home
Assistant buttons all assume a single box.

### Automatic clash resolution (to evaluate)
When more recordings overlap than there are tuners, move one to another airing of the same episode
(a later time or a sister station) or use per-series priorities, as NextPVR does. Today LineDrive
warns and badges the recording that won't get a tuner.

### Graphics-card encoding
Recordings are encoded with libx264 on the CPU (except the Original quality). Add NVIDIA NVENC,
Intel Quick Sync and VAAPI as options ([#1](https://github.com/HansDandle/LineDrive/issues/1)).

### Live viewer in the guide
Watch live TV in a side panel of the guide, with picture-in-picture and full screen. Browsers can't
play the tuner's MPEG-2/AC-3 stream, so ffmpeg transcodes it to H.264/AAC HLS. The hard part is
the tuner and CPU: one tuner and one transcode per viewer, stopped when the panel closes or the
viewer goes away, and giving way to scheduled recordings. Shares work with graphics-card encoding.

## Smaller items for any release

- **Skip episodes already in Jellyfin.** Before recording, ask Jellyfin whether that episode is in
  any library and skip it if so. Mostly helps with reruns.
