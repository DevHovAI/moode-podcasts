# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

Entries are written for the people who use the program: what can you do now
that you could not do before. They are not a copy of the commit subjects.

## [Unreleased]

### Added

- **Saved for later** ("Vorgemerkt", #10): star episodes, tracks and albums to
  keep them in a list on the device. Play the whole list or append it to the
  queue; finished episodes drop out of it on their own. Shown in the Podcasts
  tab, as a home block and on its own page.
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

- "Vormerken" (append to MPD's queue) is now called "Warteschlange" (queue),
  in the buttons and in the player's tab.
- Changing views closes an open episode dialog.
- One Podcasts tab with the sections New, My podcasts, Continue listening and
  Discover.

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

### Added

- Chapters: episodes with chapters (Podlove in the feed, `podcast:chapters`,
  or ID3 chapter frames in the file) become one queue entry per chapter, so
  moOde's next/previous buttons jump between chapters and the player shows the
  chapter title (#4).

### Fixed

- Seeking and pause work for episodes. This needs a small, reversible tweak to
  moOde's `inc/mpd.php`; see the README (#4).

### Fixed

- Episodes show their title instead of the raw link in the play queue, have
  their own cover, and the player shows episode title, podcast name and cover
  while playing (#2).
- Image processing uses a fraction of the CPU it did; a Raspberry Pi with a
  weak power supply could reset during the first refresh.

### Changed

- Podcast playlists are named "Podcast · <name>", so moOde's playlist filter
  finds all of them with "Podcast". Existing playlists are renamed on the next
  refresh.

### Added

- Subscribe to podcasts on a moOde player; each podcast appears as a playlist
  tile with cover and episode titles in moOde's Playlists view.
- Web page on port 8090 with curated recommendations, search, and paste-a-feed.
- Import subscriptions from podcast apps via OPML, and export them again.
- Install and uninstall scripts with a sandboxed systemd service and a refresh
  timer.
