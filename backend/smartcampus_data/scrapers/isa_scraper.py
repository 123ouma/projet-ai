"""Scraper for ISA — International School of Architecture."""

from __future__ import annotations

from scrapers.base_scraper import BaseScraper


class ISAScraper(BaseScraper):
    establishment_id = "ISA"

    def __init__(self, config: dict, defaults: dict, dry_run: bool = False):
        super().__init__(config, defaults, dry_run=dry_run)
