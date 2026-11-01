# moode-podcasts

Podcast subscriptions for the [moOde audio player](https://moodeaudio.org).

moOde has no podcast feature and no plugin interface. It does, however, read
episode titles and cover images from its playlists (moOde 10.3+). This small
service uses exactly that: for every podcast you subscribe to, it writes a
playlist with the newest episodes and the podcast's cover. They show up as
tiles in moOde's **Playlists** view — nothing in moOde itself is modified, so
moOde updates cannot break it.

- web page on port 8090 to manage subscriptions
- curated recommendations (German-language, mostly public broadcasters: ARD,
  Deutschlandfunk, ORF, SRF) — subscribe with one click
- search via the iTunes podcast directory, or paste any RSS feed address
- import and export **OPML**, the format AntennaPod, gPodder, Kasts, Podcast
  Addict, Pocket Casts and others use for their subscriptions
- feeds refresh every two hours; episodes are streamed, nothing is downloaded
- standard library only, no pip install on the device
- the web page is in German for now

## Installation

On the moOde device (SSH in, `git` is preinstalled):

```sh
git clone https://github.com/DevHovAI/moode-podcasts.git
cd moode-podcasts
sudo sh deploy/install.sh
```

Then open `http://moode.local:8090` (or your device's address).

From a development machine with SSH access you can also run
`just deploy pi@moode`.

To remove everything again, including the generated playlists and covers:

```sh
sudo sh deploy/uninstall.sh
```

## How it works

| What | Where |
|---|---|
| program | `/opt/moode-podcasts` |
| subscriptions | `/var/lib/moode-podcasts/feeds.json` |
| playlists | `/var/lib/mpd/playlists/<Podcast>.m3u` |
| covers | `/var/local/www/imagesw/playlist-covers/<Podcast>.jpg` |
| episode names and covers | `cfg_radio` rows with type `p`, `/var/local/www/imagesw/radio-logos/` |
| services | `moode-podcasts-web.service`, `moode-podcasts-sync.timer`, `moode-podcasts-reload.path` |

A playlist looks like this; moOde shows the `#EXTINF` text as the episode
title:

```
#EXTGENRE:Podcast
#EXTIMG:local
#EXTINF:-1,2026-10-30 · Episode title
https://example.org/episode.mp3
```

Playlists that were not created by moode-podcasts are never touched; on a
name clash a number is appended.

moOde only knows names and logos of stream URLs from its station table
`cfg_radio`. So every current episode also gets a row there, with type `p`,
which moOde's Radio view does not display — the same trick moOde's own radio
browser uses for streams it plays. That gives the play queue the episode name
and the player the episode cover. A small watcher additionally sets the
`Title`, `Artist` and `Album` tags of queued episodes in MPD (`addtagid`), and
a path unit reloads moOde's PHP session as `www-data` whenever the station
table changed. Rows of episodes that drop out of the newest ones are removed
again (unless they are still queued).

To find podcasts in moOde, use the filter field of the **Playlists** view:
moOde's search only covers the local music library.

The services run as root so the files belong to root like moOde's own, but
inside a systemd sandbox without any capabilities, at low priority, limited to
half a CPU core, and with write access to the directories above only.

Command line, on the device:

```sh
cd /opt/moode-podcasts
sudo python3 -m moode_podcasts list
sudo python3 -m moode_podcasts add https://example.org/feed.xml
sudo python3 -m moode_podcasts sync
```

## Limits

moOde treats episodes like radio streams:

- while playing, the second line reads "Radio station" (fixed in moOde)
- no resume position, no "played" marker
- seeking only works if the podcast host supports HTTP range requests (most do)
- the web page has no login, like moOde itself — keep it in your home network

## Development

```sh
just              # list the recipes
just check        # lint, format check, tests — everything the CI runs
just run serve    # run the web page locally (set the MOODE_PODCASTS_* paths first)
just recommendations   # rebuild the recommendation list (needs network)
```

Local runs can be pointed at scratch directories with
`MOODE_PODCASTS_DATA`, `MOODE_PODCASTS_PLAYLISTS` and `MOODE_PODCASTS_COVERS`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## License

MIT
