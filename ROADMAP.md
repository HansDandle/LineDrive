# Roadmap

What's planned for LineDrive. Nothing here is promised or dated; order is roughly the order of work.
Shipped features move to [CHANGELOG.md](CHANGELOG.md). Ideas and requests are welcome as issues.

4.0 shipped Sonarr handoff, Comskip, graphics-card encoding, several HDHomeRun boxes and live TV in
the guide. Reports from Linux machines with a graphics card
([#1](https://github.com/HansDandle/LineDrive/issues/1)) and from setups with more than one
HDHomeRun are especially welcome: both were built and tested without that hardware.

## Later

### Automatic clash resolution (to evaluate)
When more recordings overlap than there are tuners, move one to another airing of the same episode
(a later time or a sister station) or use per-series priorities, as NextPVR does. Today LineDrive
warns and badges the recording that won't get a tuner.

### Per-box channel lineups in clash warnings
Clash warnings count every box's tuners together, which is right when the boxes share an antenna.
Boxes on different antennas (different channels) can still clash on a channel only one of them
carries.

## Smaller items for any release

- **Skip episodes already in Jellyfin.** Before recording, ask Jellyfin whether that episode is in
  any library and skip it if so. Mostly helps with reruns.
