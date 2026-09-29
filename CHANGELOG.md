# Changelog

All notable changes to LineDrive will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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