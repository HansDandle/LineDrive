# Changelog

All notable changes to LineDrive will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.2.0] - 2026-10-24

### Added
- XMLTV guide import (Settings → TV guide → **XMLTV guide**, `epg.xmltv`): a URL or a file (`.xml` or `.xml.gz`) for channels the ZIP code doesn't cover, so outside the US and Canada (a UK Freeview guide, say) the guide reaches a week ahead instead of SiliconDust's day. Its channels are matched to the tuner's by channel number or LCN, then by name; **Test** says how many matched, and `epg.xmltv_channels` maps the rest. A feed that never marks new episodes or repeats leaves "new episodes only" alone rather than treating everything as a rerun.
- IPTV (Settings → Integrations → **IPTV**, `iptv`): M3U playlists whose channels join the guide and record, play live and follow series like antenna channels. Each playlist is a source with as many "tuners" as the provider allows streams at once (`max_streams`), and its guide is the playlist's XMLTV (`url-tvg`) or one you give, matched by `tvg-id`. Channels keep the playlist's `tvg-chno` when it's free, otherwise 1001, 1002…; `groups` keeps only some of a big playlist.

- A **Support LineDrive** link (Ko-fi) in the footer, the README and the GitHub page. LineDrive stays free.

### Changed
- Clash warnings know which tuners can record which channels: an IPTV stream never counts as an antenna tuner, and HDHomeRuns on different antennas only count for the channels they get.
- `/debug/refresh_epg` refreshes every guide source, not just Gracenote.

## [4.1.0] - 2026-10-24

### Added
- Tuner clashes suggest another airing. When a recording won't get a tuner and the same episode (same show, season/episode or episode title) airs again in the week's guide when a tuner is free, the warning says so and **Record that one instead** moves it: one tap in Upcoming on the home page or in the show's details in the guide. Local channels are offered before out-of-market ones, then the earliest airing, and never one that would leave another recording without a tuner. Nothing moves without the tap.
  - Includes clashes caused by sports overrun padding: when a game runs long the show after it is pushed back, so the padding holds its tuner, and another airing of the show that needs it is the way out.
  - A one-time recording (or a new-episodes series episode) moves to the other airing; a time-slot series skips just that airing ("Recording another airing" in Upcoming) and its keep/delete setting applies to the moved recording.

### Fixed
- A recording of a live game gets the sports overrun minutes too (`recording.sports_overrun_minutes`, default 30), including **Record the rest** of a game already on. Only the shows after a game got them before, so a game that ran long lost its ending.

## [4.0.0] - 2026-10-24

### Added
- Live TV in the guide: **Watch here** in the details of anything on now opens a player docked in the corner of the guide, which stays while you browse, with picture-in-picture and full screen. LineDrive converts the broadcast to 720p H.264/AAC HLS as it airs (on the encoder chosen for recordings) and the player uses a bundled hls.js (Safari plays it natively).
  - Each viewer holds a tuner. Closing the player or the page frees it at once; a player that stops checking in is stopped after about a minute.
  - Recordings come first: when a recording needs a tuner and none is free, the longest-running viewer on a box with that channel is stopped, and the player says why. The home page's tuner list shows live TV, with a **Stop** button.
  - At most two viewers at once by default (`live.max_viewers`). **Watch in VLC** is still there.
- Several HDHomeRun boxes: list their addresses separated by commas in Settings (or click each discovered box) and their tuners are pooled.
  - The channel list is every box's lineup together. A recording goes to a box that carries the channel and has a free tuner (the one with the most free first), and moves to the next box if another app took the last tuner first.
  - Tuners are numbered across boxes (box 1's first), on the home page and in Home Assistant. A box that doesn't answer is shown as such and the others carry on.
  - Clash warnings count every box's tuners together. SiliconDust's guide is also read from a second box when it has channels the first doesn't.
- Graphics card encoding ([#1](https://github.com/HansDandle/LineDrive/issues/1)): Settings → Recordings → **Encode with** CPU (default), NVIDIA (NVENC), Intel Quick Sync or VAAPI (Intel/AMD on Linux). Each quality setting maps to the card's closest equivalent.
  - **Test** tries every encoder and says which work here, and why the others don't ("Cannot load libcuda.so.1", "/dev/dri/renderD128 not found", ...).
  - A card that doesn't work falls back to the CPU, with a note on the home page. One that fails partway through a live recording (some cards reject odd frames at the start of a broadcast) hands the rest of the show to the CPU, as a `(part 2)` file if some was already saved, and isn't used again until it passes **Test**.
  - The Docker image includes the VAAPI and Quick Sync drivers (Intel's on x86 only). Pass `/dev/dri` into the container for Intel/AMD, or use the NVIDIA Container Toolkit; see the README.
  - New options: `recording.encoder`, `recording.vaapi_device`.
- Sonarr handoff: Settings → Integrations → Sonarr (URL + API key). When an episode finishes recording, LineDrive finds it in Sonarr and unmonitors it, so Sonarr doesn't download the same episode. The home page says when it did.
  - Episodes are matched by season and episode number, else by the date it aired, else by episode title. A number or date match whose episode title disagrees is ignored, so a rerun of an older show with the same name (the original *Scrubs* vs. the revival) is never mistaken for the new one.
  - Only the episode's monitored flag changes. Nothing is imported, moved or deleted, and Sonarr doesn't need access to the recordings folder. Shows Sonarr doesn't have, episodes it already has and movies and sports are left alone.
- Commercial marking with Comskip (Settings → Recordings → Commercials, off by default). After a recording finishes, Comskip finds the ad breaks; LineDrive writes them into the file as **Show / Commercial** chapters and keeps a `.edl` beside it. The video is only remuxed, never cut or re-encoded. One recording is processed at a time at low CPU priority, and Jellyfin is told about the recording once its chapters are in.
  - Jellyfin 10.10+: the Chapter Segments plugin turns the Commercial chapters into skippable segments. Kodi skips breaks from the `.edl`. Plex and Emby show the chapters to jump past them.
  - Or **cut them out** (`recording.comskip_mode: "cut"`), for Plex, Emby and anything else that can't skip chapters. Still no re-encoding: the show is stream-copied in pieces, each starting on the keyframe just before it, so a second of ad may remain but no show is lost. The uncut original (with its `.srt`, `.nfo` and `.edl`) goes to `<recordings>/.deleted/` for 7 days, so a bad cut can be undone by moving it back. Captions are re-timed to match. A recording is given chapters instead when Comskip marks over half of it as ads, or the cut comes out the wrong length.
  - The Docker image now includes Comskip (built from source). Use your own settings with `recording.comskip_ini`.
  - `.mp4` and `.mkv` get chapters; Original-quality `.ts` recordings get only the `.edl`.
  - Keep/delete clean-up removes the `.edl` with its recording.

## [3.5.0] - 2026-10-01

### Added
- Keep or delete, per series: a menu on each series in Upcoming keeps everything (the default), the newest 1, 3, 5 or 10 episodes, deletes after 1 week, 2 weeks or 30 days, or, with Jellyfin connected, deletes once watched (right away, after 2 days or after a week). Clean-up runs hourly and after each recording.
  - Only recordings LineDrive made for that series are ever removed. They're listed in `data/recordings.json` from this version on, so downloads, your own files, and recordings from before 3.5 are never touched.
  - Removed recordings and their `.srt`/`.nfo` go to `<recordings>/.deleted/` for 7 days first (Jellyfin skips it), and the home page says what was cleaned up.
  - A removed episode still counts as one you have, so a rerun doesn't record it again.
- **Watch in VLC** in the guide's details for anything on now: phones and tablets open the tuner's stream in the VLC app, computers get a one-channel playlist to open with VLC. Nothing is converted, and closing VLC frees the tuner.

## [3.4.0] - 2026-10-01

### Added
- Tuner clash warnings. Scheduling a recording that would need more tuners than you have still schedules it, but says which airing won't record and what's holding the tuners. Until you cancel one, the recording left without a tuner has a **No free tuner** badge in Upcoming and an amber mark in the guide. Overlaps are worked out for the week ahead, the way the recordings will actually take tuners (counting sports overrun padding, and not counting airings that will be skipped as reruns or already recorded).
- The version number, in the footer of the home and Settings pages, in `/api/status`, and on the Home Assistant device.
- Settings → Recordings: switches for the closed-caption `.srt` and the `.nfo` saved beside each recording (`recording.captions`, and the new `recording.nfo`).

### Changed
- Guide lookups are faster (listings indexed by channel, start times parsed once).

## [3.3.0] - 2026-09-29

### Added
- More than one ZIP/postal code, comma-separated (`L2E 6S4, 14201`), for antennas that reach a market Gracenote lists separately. Each lineup is fetched and merged; where two carry the same station, the first code wins.
- **Test** next to the ZIP/postal code reports each code's channel count and lists any of your tuner's channels that none of them cover.
- Hide single subchannels: in Settings → Stations, open a station (▸) and hide e.g. 7.2 while 7.1 stays in the guide. The station's box is half-ticked when only some of its channels are hidden.

## [3.2.0] - 2026-09-29

### Added
- Canadian postal codes: a week of Gracenote over-the-air listings in Canada (e.g. `M5V 3L9`). Border areas get stations from both sides, as US ZIPs near the border already did.
- Hide stations: Settings → Stations has a **Hide** box beside **Out of market** for each station (saved as you tick), and **Hide channel** in a show's details hides a single channel. Hidden channels leave the guide, answers, searches and new-episode series but can still be recorded by number. After **Check signal**, Settings offers to hide the weak ones.
- XMLTV export at `/guide.xml`: the merged guide (Gracenote + SiliconDust, without hidden channels) for Jellyfin, Plex, Channels or anything else that reads XMLTV.

## [3.1.0] - 2026-09-27

### Added
- Closed captions are saved as `<recording>.en.srt` beside each recording, so Jellyfin, Plex and Kodi offer them as subtitles. They're read from the broadcast as it airs. Turn off with `recording.captions: false`.
- The status card says "Finishing…" while a stopped or ended recording is being saved.
- SiliconDust's guide for your tuner (the HDHomeRun app's) is merged into Gracenote's: series IDs, original air dates, artwork, and listings for channels Gracenote lacks. Without a ZIP code it's the whole guide, so LineDrive works outside the US.
- Recordings resume after a restart: whatever should be recording (scheduled, "Record the rest" or manual) is picked up again as `<name> (2)`, and shows missed while LineDrive was off are started if they're still on.
- Signal strength per channel: a scan on a spare tuner (weekly, or Settings → Check signal) plus live readings. The guide shows bars and warns about weak channels; "Check now" re-measures one.
- Settings → Recording quality: Best, Standard, Smaller, 720p or Original. Replaces the CRF/speed fields on the home page.

### Changed
- MP4 recordings are fragmented, so one cut off by a crash or restart still plays, and there's no slow index rewrite when a recording ends.
- An airing whose original air date is the day it airs counts as new, even without a "New" flag.
- The ZIP code is optional.

## [3.0.0] - 2026-09-27

A rebuilt LineDrive: Docker-first, a real program guide, and a DVR you can talk to.

### Added
- **Program guide**: a week of over-the-air listings by channel and time, with search, a now-line, one-tap Record / Series, and a TV mode for Fire TV Silk (D-pad, rewind/fast-forward).
- **Ask LineDrive**: offline answers to plain-English guide questions ("when's the next basketball game?", "what's on NBC at 9?", "is Jeopardy on tomorrow?") and commands ("record SNL every Saturday", "record Jeopardy, new episodes only", "record Abbott Elementary when it comes back").
- **Series options**: new-episodes-only series that follow the guide across channels and preemptions; rerun skipping; skipping episodes already recorded; watches for shows not in the guide yet.
- **Media-server naming**: `TV/<Show>/Season NN/Show - SxxEyy - Title.mp4`, `Movies/<Title (Year)>/`, and `.nfo` metadata.
- **Settings page** with tuner discovery, guide and connection tests; first launch opens it.
- **Integrations**: Jellyfin (instant library refresh), Jellyseerr (request movies/shows), Home Assistant (MQTT auto-discovery: sensors and buttons).
- **Tuner awareness**: busy-tuner checks, failure reporting, recording in-progress shows, and a kill switch for streams other apps leave open.
- **Docker image** for amd64/arm64 on GHCR, example `docker-compose.yml`, tests and CI.

### Changed
- New home page and web layout; waitress web server; port 5050 by default.
- The guide uses the correct Gracenote lineup (`USA-OTA<zip>-DEFAULT`) and fields (descriptions, categories, season/episode, New/Live flags).
- The scheduler tolerates late loop iterations and guide refreshes no longer run inside it.
- Guide times follow the machine's time zone (or `TZ` in Docker) unless one is configured.
- Torrent search/download/VPN commands are off by default (`features.torrent_downloads`).

### Fixed
- HDHomeRun discovery (invalid discovery packet; virtual network adapters).
- Two copies of LineDrive could record the same show into the same file, producing unplayable recordings.
- Concurrent recordings on two tuners watched each other's ffmpeg process.
- Schedule IDs could collide after deletions, so cancelling one recording could remove another.

### Removed
- Windows-only desktop/console setup wizards, watchdog, service wrapper, Wake-on-LAN and batch scripts.

## [2.0.0] - 2025-09-28

### Added
- **LineDrive Branding**: Complete rebrand from "TV Recorder" to "LineDrive"
- **Generic VPN Manager**: Support for NordVPN, ExpressVPN, ProtonVPN, Surfshark, and custom providers
- **Generic Indexer Manager**: Support for Prowlarr, Jackett, and Torznab indexers
- **LineDrive Logo**: Professional logo integration in web interface and documentation
- **Trademark Compliance**: Comprehensive legal notices and disclaimers
- **Interactive Setup Wizards**: User-friendly configuration for VPN and indexer providers
- **Configuration Management**: JSON-based configuration system with templates

### Removed
- **BiratePay Integration**: Removed proprietary system in favor of generic indexer support
- **ProtonVPN Hard-coding**: Replaced with provider-agnostic VPN system
- **Test Files**: Cleaned up unnecessary test files and dependencies

### Changed
- **Repository Name**: Updated from TV_Recorder_pub to LineDrive
- **Configuration Directory**: Changed from `.tv_recorder` to `.linedrive`
- **Web Interface**: Updated branding, added logo, improved legal compliance notices
- **Documentation**: Comprehensive updates for new provider-agnostic architecture

## [1.0.0] - Previous

### Added
- Initial TV recording functionality
- HDHomeRun integration
- Basic web interface
- Support for environment-based configuration
- Automatic directory creation during setup
- HDHomeRun device auto-discovery
- FFmpeg installation validation and auto-detection

### Changed
- Removed all hardcoded API keys, IP addresses, and file paths
- Replaced hardcoded values with configuration system
- Improved error handling and user feedback
- Modernized code structure and organization

### Removed
- All test files (`test_*.py`)
- Debug scripts (`debug_*.py`, `check_*.py`)
- Personal configuration data
- Hardcoded credentials and paths

### Security
- Removed exposed API keys from source code
- Implemented secure configuration management
- Added validation for user input and file paths

## [Previous Versions]

Previous versions of this project were private development builds and are not documented in this changelog. The first public release incorporates all major features developed during private development.