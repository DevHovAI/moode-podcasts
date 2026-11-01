"""Aufruf: python -m moode_podcasts {serve,sync,add,remove,list}"""

import argparse
import logging
import sys

from moode_podcasts import __version__, sync, web
from moode_podcasts.store import Store


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="moode-podcasts", description="Podcasts for moOde")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-v", "--verbose", action="store_true")
    cmd = ap.add_subparsers(dest="cmd", required=True)
    s = cmd.add_parser("serve", help="start the web page")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8090)
    cmd.add_parser("sync", help="refresh all subscriptions")
    a = cmd.add_parser("add", help="subscribe to a feed")
    a.add_argument("url")
    r = cmd.add_parser("remove", help="unsubscribe from a feed")
    r.add_argument("url")
    cmd.add_parser("list", help="show subscriptions")
    args = ap.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    store = Store()
    if args.cmd == "serve":
        web.serve(args.host, args.port, store)
    elif args.cmd == "sync":
        return 1 if sync.sync_all(store) else 0
    elif args.cmd == "add":
        sub = sync.subscribe(store, args.url)
        print(f"{sub.get('title')}: {len(sub.get('episodes', []))} episodes")
    elif args.cmd == "remove":
        return 0 if sync.unsubscribe(store, args.url) else 1
    elif args.cmd == "list":
        for sub in store.load():
            state = (
                f"ERROR {sub['error']}"
                if sub.get("error")
                else f"{len(sub.get('episodes', []))} episodes"
            )
            print(f"{sub.get('title')}\t{state}\t{sub['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
