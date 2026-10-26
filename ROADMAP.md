# Roadmap

What's planned for LineDrive. Nothing here is promised or dated; order is roughly the order of work.
Shipped features move to [CHANGELOG.md](CHANGELOG.md). Ideas and requests are welcome as issues.

4.0 shipped Sonarr handoff, Comskip, graphics-card encoding, several HDHomeRun boxes and live TV in
the guide. Reports from Linux machines with a graphics card
([#1](https://github.com/HansDandle/LineDrive/issues/1)) and from setups with more than one
HDHomeRun are especially welcome: both were built and tested without that hardware.

## Next

### Comskip while recording
The way Windows Media Center and DVRMSToolbox did it: start watching a show 30 minutes in, while
it's still recording, with the ad breaks found so far already skippable. Comskip can mark breaks as
the file grows (its `live_tv` mode). The work is on LineDrive's side: record to a file that can be
played while it grows (`.ts` or fragmented MP4, where today's `.mp4` can't be played until it's
finished), run Comskip alongside the recording, and let the guide's player play an in-progress
recording from the start, skipping the marked breaks. Marks only, never cuts, until it's done.

## Later

### Series priorities
When more recordings overlap than there are tuners and no other airing has a tuner free, let
per-series priorities decide which one loses, instead of the one scheduled first winning. Only
worth it if real clashes turn out to be common; 4.1 already offers another airing where there is
one.

## Smaller items for any release

- **Skip episodes already in Jellyfin.** Before recording, ask Jellyfin whether that episode is in
  any library and skip it if so. Mostly helps with reruns.
- **Upload IPTV playlists and guides.** An Upload button beside Settings → IPTV's M3U and XMLTV
  fields that saves the file into LineDrive's config folder and fills in its path. In Docker
  LineDrive only sees its own folders, so this beats a file browser.
