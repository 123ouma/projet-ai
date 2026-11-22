"""Scraper for 2I2S — École Internationale des Sciences de Santé."""

from __future__ import annotations

from scrapers.base_scraper import BaseScraper


class I2SScraper(BaseScraper):
    establishment_id = "2I2S"

    def __init__(self, config: dict, defaults: dict, dry_run: bool = False):
        super().__init__(config, defaults, dry_run=dry_run)
