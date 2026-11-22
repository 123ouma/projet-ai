"""Scraper for IIT — Institut International de Technologie."""

from __future__ import annotations

from scrapers.base_scraper import BaseScraper


class IITScraper(BaseScraper):
    establishment_id = "IIT"

    def __init__(self, config: dict, defaults: dict, dry_run: bool = False):
        super().__init__(config, defaults, dry_run=dry_run)
