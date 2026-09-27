# Changelog

All notable changes to LineDrive will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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