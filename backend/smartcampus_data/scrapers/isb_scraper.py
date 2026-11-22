"""Scraper for ISB — International School of Business."""

from __future__ import annotations

from scrapers.base_scraper import BaseScraper


class ISBScraper(BaseScraper):
    establishment_id = "ISB"

    def __init__(self, config: dict, defaults: dict, dry_run: bool = False):
        super().__init__(config, defaults, dry_run=dry_run)
