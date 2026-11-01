# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

Entries are written for the people who use the program: what can you do now
that you could not do before. They are not a copy of the commit subjects.

## [Unreleased]

### Added

- Radio stations show a link to their website under "Shownotes" in the
  player. The link comes from the website field of moOde's station list.
- Mark radio stations as favourites and edit their stream address, website,
  genre, broadcaster, language and country: ⋯ on a station tile or in the
  player. moOde saves the change itself, as if made in its station editor.
- Backup and restore in the settings, like moOde's own: one zip with your
  subscriptions, listening progress, saved items, home screen and theme,
  together with moOde's backup (settings, radio stations including
  favourites and websites, playlists, CamillaDSP …). Pick what to save and
  what to restore. moOde's backup page accepts the same file.
- Sleep timer in the player: pause after 15 to 90 minutes or at the end of
  the current episode. It runs on the moOde device, so it works with the
  page closed, and every device sees the time left.
- Podcast search also covers the ARD Audiothek. A podcast found in both
  places is shown once. ARD shows that have no RSS feed of their own can be
  subscribed as well.

## [0.5.1] - 2026-11-01

### Removed

- The automatic clean-up of what versions 0.1 and 0.2 changed in moOde. To
  upgrade from one of those, install 0.5.0 first.

## [0.5.0] - 2026-11-01

### Added

- **Saved for later** ("Vorgemerkt", #10): star episodes, tracks and albums to
  keep them in a list on the device. Play the whole list or append it to the
  queue; finished episodes drop out of it on their own. Shown in the Podcasts
  tab, as a home block and on its own page.

### Changed

- "Vormerken" (append to MPD's queue) is now called "Warteschlange" (queue),
  in the buttons and in the player's tab.
- Changing views closes an open episode dialog.

## [0.4.0] - 2026-11-01

### Added

- Home screen assembled from blocks, editable in the page and shared by all
  devices (#8).
- Music tab for moOde's local library: artists, albums, genres, recently added;
  play or queue albums and tracks.
- Global search across subscriptions, episodes, radio stations and music.
- Colour themes with light/dark/automatic mode and a free or moOde-matched
  accent colour.
- Radio grouped by genre, language or broadcaster; subscriptions grouped by
  their iTunes category.

### Changed

- One Podcasts tab with the sections New, My podcasts, Continue listening and
  Discover.

## [0.3.0] - 2026-11-01

### Changed

- **The web page is now the player** (#6): newest episodes, podcast pages,
  a player with seek bar, ±30 s, chapter list, shownotes and queue, resume
  position and "played" markers, and moOde's radio stations. Playback still
  goes through moOde's MPD.
- **moOde is no longer modified.** The generated playlists, the hidden rows in
  moOde's station table and the tweak to `inc/mpd.php` are gone; upgrading
  removes them automatically.

### Removed

- Podcast playlists in moOde's Playlists view and chapter splitting in the queue.

## [0.2.0] - 2026-11-01

### Added

- Chapters: episodes with chapters (Podlove in the feed, `podcast:chapters`,
  or ID3 chapter frames in the file) become one queue entry per chapter, so
  moOde's next/previous buttons jump between chapters and the player shows the
  chapter title (#4).

### Fixed

- Seeking and pause work for episodes. This needs a small, reversible tweak to
  moOde's `inc/mpd.php` (#4).

## [0.1.0] - 2026-11-01

### Added

- Subscribe to podcasts on a moOde player; each podcast appears as a playlist
  tile named "Podcast · <name>", with cover and episode titles, in moOde's
  Playlists view.
- Episodes show their own title and cover in the play queue and in moOde's
  player (#2).
- Web page on port 8090 with curated recommendations, search, and paste-a-feed.
- Import subscriptions from podcast apps via OPML, and export them again.
- Install and uninstall scripts with a sandboxed systemd service and a refresh
  timer.

[Unreleased]: https://github.com/DevHovAI/moode-podcasts/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/DevHovAI/moode-podcasts/releases/tag/v0.5.1
