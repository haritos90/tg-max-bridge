"""Entry point: poll both messengers, relay between them."""

import logging
import signal
import sys
import threading
import time

from . import __version__, config
from .bridge import Bridge
from .messengers import Max, Telegram
from .state import State

log = logging.getLogger("tg_max_bridge")

MAX_BACKOFF = 60


def poll_forever(messenger, bridge, stop):
    backoff = 1
    while not stop.is_set():
        try:
            for ev in messenger.poll():
                bridge.handle(ev)
            backoff = 1
        except Exception as e:
            log.error("%s poll failed: %s", messenger.name, e)
            stop.wait(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--version" in argv:
        print(__version__)
        return 0
    try:
        cfg = config.load()
    except config.ConfigError as e:
        print("configuration error: %s" % e, file=sys.stderr)
        return 2
    logging.basicConfig(level=cfg.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    tg = Telegram(cfg.tg_token)
    mx = Max(cfg.max_token, cfg.max_api_url, cfg.max_ca_file)
    bots = {}
    for m in (tg, mx):
        info = m.whoami()
        bots[m.name] = info.get("username") or info.get("name") or "unknown"
        log.info("%s bot: %s", m.name, bots[m.name])
    state = State(cfg.state_file).load()
    bridge = Bridge(cfg, state, {tg.name: tg, mx.name: mx})
    bridge.bots = bots
    bridge.resend_pending()

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threads = [threading.Thread(target=poll_forever, args=(m, bridge, stop),
                                name=m.name, daemon=True) for m in (tg, mx)]
    for t in threads:
        t.start()
    log.info("bridge %s running, state in %s", __version__, cfg.state_file)
    while not stop.is_set():
        time.sleep(0.5)
    log.info("stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
