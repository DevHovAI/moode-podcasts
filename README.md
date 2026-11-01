# moode-podcasts

A podcast, radio and music player page for the [moOde audio player](https://moodeaudio.org).

It runs on the moOde device and serves a mobile-friendly web page on port 8090.
The page is a remote control: it drives moOde's MPD, so sound comes out of
your hi-fi, and every phone, tablet or PC sees the same state. moOde itself is
not modified.

- **Start**: a home screen you assemble from blocks (saved for later,
  continue listening, new episodes, a podcast, favourite stations, a radio
  genre or language, recently added music, a music genre or artist), shared by
  all devices
- **Podcasts**: one tab with New, My podcasts (grouped by genre), Continue
  listening and Discover, each a short preview with 'show all'
- **Player**: seek bar, ±30 s, chapter list (tap to jump), shownotes,
  next/previous jump between chapters, the queue ("Warteschlange")
- **Saved for later** ("Vorgemerkt"): a starred list of episodes, tracks and
  albums kept on the device; finished episodes drop out by themselves
- **Resume**: remembers where you stopped in every episode, shows progress and
  "played"
- **Radio**: all of moOde's stations with their logos, favourites first,
  grouped by genre, language or broadcaster
- **Music**: moOde's local library: artists (A–Z), albums, genres, recently
  added; play or queue albums and tracks; covers come from moOde
- **Search** across subscriptions, episodes, radio stations and music
- **Themes**: six colour schemes, light/dark/automatic, any accent colour or
  moOde's own
- **Discover**: curated recommendations (German-language, mostly public
  broadcasters: ARD, Deutschlandfunk, ORF, SRF), search via the iTunes
  directory, paste any RSS feed
- **OPML** import and export, the format AntennaPod, gPodder, Kasts, Podcast
  Addict, Pocket Casts and others use for their subscriptions
- live updates in the page (server-sent events), feeds refresh every two hours,
  episodes are streamed
- standard library only, no pip install on the device
- the page is in German for now

## Installation

On the moOde device (SSH in, `git` is preinstalled):

```sh
git clone https://github.com/DevHovAI/moode-podcasts.git
cd moode-podcasts
sudo sh deploy/install.sh
```

Then open `http://moode.local:8090` (or your device's address). On a phone,
"add to home screen" makes it feel like an app.

From a development machine with SSH access you can also run
`just deploy pi@moode`.

To remove it again: `sudo sh deploy/uninstall.sh`.

## How it works

| What | Where |
|---|---|
| program | `/opt/moode-podcasts` |
| subscriptions and episode lists | `/var/lib/moode-podcasts/feeds.json` |
| listening progress | `/var/lib/moode-podcasts/progress.json` |
| saved for later | `/var/lib/moode-podcasts/marked.json` |
| theme and home screen (all devices) | `/var/lib/moode-podcasts/settings.json` |
| resized cover images | `/var/lib/moode-podcasts/img/` |
| services | `moode-podcasts-web.service`, `moode-podcasts-sync.timer` |

- **Playback** uses MPD's queue. Playing an episode inserts it right after the
  current item, so whatever else is queued in moOde stays; the queue keeps
  playing when the page is closed.
- **Chapters** come from the feed (Podlove Simple Chapters, `podcast:chapters`)
  or the ID3 chapter frames at the start of the file. They are looked up for
  the newest episodes during the refresh, for older ones when first played.
- **Radio stations** are read (never written) from moOde's station table; the
  logos are served by moOde itself.
- **Music** comes from MPD's database (`list`/`find`/`search`); album covers
  are served by moOde's `coverart.php`. Add music sources (NAS, USB) in moOde's
  library settings as usual.
- The services run as root but without any capabilities, inside a systemd
  sandbox with write access to `/var/lib/moode-podcasts` only, at low priority
  and limited to half a CPU core (a Raspberry Pi with a weak power supply can
  reset under sustained full load).

Command line, on the device:

```sh
cd /opt/moode-podcasts
sudo python3 -m moode_podcasts list
sudo python3 -m moode_podcasts add https://example.org/feed.xml
sudo python3 -m moode_podcasts sync
```

## Limits

- Far jumps can take a while: moOde's MPD decodes MP3 with `mad`, which reads
  up to the target position (about 20 s for a jump of an hour). The page shows
  "Springe …" meanwhile. MPD's `mpg123` decoder seeks in about a second; you
  can switch to it with moOde's developer tweak (`/etc/mpd.custom.conf`:
  `decoder { plugin "mad" enabled "no" }`). moode-podcasts does not change
  moOde's configuration itself.
- Seeking needs a podcast host with HTTP range requests (nearly all have them).
- No login, like moOde itself – keep it in your home network.

## Development

```sh
just              # list the recipes
just check        # lint, format check, tests — everything the CI runs
just run serve    # run the page locally (point MOODE_PODCASTS_* at test data/MPD)
just recommendations   # rebuild the recommendation list (needs network)
```

Environment variables for local runs: `MOODE_PODCASTS_DATA`,
`MOODE_PODCASTS_DB` (moOde's database, for the stations),
`MOODE_PODCASTS_MPD_HOST`, `MOODE_PODCASTS_MPD_PORT`. A silent MPD with
`audio_output { type "null" }` on another port is handy for testing.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## License

MIT
