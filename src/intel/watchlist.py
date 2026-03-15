"""Watchlist definitions for monitored X accounts."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class WatchAccount:
    handle: str
    category: str
    priority: int = 2


WATCHLIST: tuple[WatchAccount, ...] = (
    WatchAccount("KobeissiLetter", "macro", 2),
    WatchAccount("anasalhajji", "energy", 1),
    WatchAccount("TheStudyofWar", "geopolitics", 1),
    WatchAccount("thewarzonewire", "osint", 2),
    WatchAccount("steverob", "geopolitics", 3),
    WatchAccount("DVIDSHub", "defense_official", 2),
    WatchAccount("gCaptain", "maritime", 1),
    WatchAccount("JavierBlas", "commodities", 1),
    WatchAccount("ianellisjones", "macro", 3),
    WatchAccount("johnkonrad", "maritime", 1),
    WatchAccount("LloydsList", "maritime", 1),
    WatchAccount("ed_fin", "macro", 3),
    WatchAccount("ChrisDMacro", "macro", 2),
    WatchAccount("BurggrabenH", "macro", 3),
    WatchAccount("TheMichaelEvery", "macro", 2),
    WatchAccount("ericnuttall", "energy", 1),
)


def handles(accounts: Iterable[WatchAccount] = WATCHLIST) -> list[str]:
    return [a.handle for a in accounts]
