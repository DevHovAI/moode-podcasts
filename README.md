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
| services | `moode-podcasts-web.service`, `moode-podcasts-sync.timer` |

A playlist looks like this; moOde shows the `#EXTINF` text as the episode
title:

```
#EXTGENRE:Podcast
#EXTIMG:local
#EXTINF:-1,2026-10-30 · Episode title
https://example.org/episode.mp3
```

Playlists that were not created by moode-podcasts are never touched; on a
name clash the podcast gets a `(Podcast)` suffix.

The services run as root so the files belong to root like moOde's own, but
inside a systemd sandbox without any capabilities and with write access to the
three directories above only.

Command line, on the device:

```sh
cd /opt/moode-podcasts
sudo python3 -m moode_podcasts list
sudo python3 -m moode_podcasts add https://example.org/feed.xml
sudo python3 -m moode_podcasts sync
```

## Limits

moOde treats episodes like radio streams:

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
