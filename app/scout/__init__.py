"""Scout modülü — watchlist + alert + (ileride) similarity engine."""

from app.scout.watchlist import (
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
    update_watchlist_notes,
)

__all__ = [
    "add_to_watchlist",
    "list_watchlist",
    "remove_from_watchlist",
    "update_watchlist_notes",
]
