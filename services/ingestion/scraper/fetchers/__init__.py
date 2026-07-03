"""Fetchers turn a jurisdiction into a list of :class:`SectionRecord`."""

from __future__ import annotations

from .amlegal import AmericanLegalFetcher
from .base import FetchResult, Fetcher, SectionRecord
from .ecode360 import ECode360Fetcher
from .encodeplus import EncodePlusFetcher
from .flippingbook import FlippingBookFetcher
from .generic_html import GenericHtmlFetcher
from .madcapflare import MadCapFlareFetcher
from .municipalcodeonline import MunicipalCodeOnlineFetcher
from .municode import MunicodeFetcher

__all__ = [
    "FetchResult",
    "Fetcher",
    "AmericanLegalFetcher",
    "ECode360Fetcher",
    "EncodePlusFetcher",
    "FlippingBookFetcher",
    "SectionRecord",
    "GenericHtmlFetcher",
    "MadCapFlareFetcher",
    "MunicipalCodeOnlineFetcher",
    "MunicodeFetcher",
]
