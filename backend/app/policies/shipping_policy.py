"""Deterministic shipping policy module."""

from app.config import get_settings


class ShippingPolicy:
    def __init__(self) -> None:
        self.settings = get_settings()

    def calculate_shipping(self, subtotal_inr: int) -> int:
        """
        Calculate deterministic shipping amount in INR.
        If the subtotal is >= the free shipping threshold, shipping is free.
        Otherwise, a flat rate is applied.
        """
        if subtotal_inr >= self.settings.shipping_free_threshold_inr:
            return 0
        return self.settings.shipping_flat_rate_inr
