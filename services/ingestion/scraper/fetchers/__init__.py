"""Fetchers turn a jurisdiction into a list of :class:`SectionRecord`."""

from __future__ import annotations

from .base import FetchResult, Fetcher, SectionRecord
from .flippingbook import FlippingBookFetcher
from .generic_html import GenericHtmlFetcher
from .municode import MunicodeFetcher

__all__ = [
    "FetchResult",
    "Fetcher",
    "FlippingBookFetcher",
    "SectionRecord",
    "GenericHtmlFetcher",
    "MunicodeFetcher",
]
