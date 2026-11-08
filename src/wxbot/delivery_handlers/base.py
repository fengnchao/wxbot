"""Shared in-process handler lifecycle; the pump remains the sole queue/UI owner."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..delivery import DeliveryPump


@dataclass
class ActiveDelivery:
    delivery: object
    chat: object
    typing: object
    baseline: list
    deadline: float | None = None
    authorization_paused_at: float | None = None


class DeliveryHandler:
    def __init__(self, pump: 'DeliveryPump'):
        self.pump = pump

    @property
    def preparing(self):
        return False

    def start(self, delivery):
        raise NotImplementedError

    def sync_input(self, active, row):
        """Return False if input was stopped before the next UI step."""
        return True

    def complete(self, active, state):
        raise NotImplementedError

    def poll(self):
        """Return True when background preparation consumed this service turn."""
        return False

    def prepare_finish(self, delivery, state, details):
        """Adjust type-specific failure policy before persisting the result."""
        return state

    def failure_details(self, active, state):
        """Defaults merged before the UI session's more specific diagnostics."""
        return {}

    def after_finish(self, delivery, state, error, original_state):
        pass

    def close(self):
        pass
