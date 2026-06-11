"""Shared data types."""
from dataclasses import dataclass


@dataclass
class FloorPriceResult:
    lowest_price: float
    section: str
    floor_listing_count: int
    total_listing_count: int
