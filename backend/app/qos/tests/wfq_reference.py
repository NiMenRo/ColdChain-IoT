"""Small independent WFQ/GPS oracle used only by scheduler tests.

It deliberately has no dependency on application schedulers. ``arrival`` is
the GPS virtual time observed by a packet at admission; tests choose it
explicitly so the oracle can cover simultaneous arrivals and reactivation
without wall-clock timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Hashable, Iterable


@dataclass(frozen=True)
class ReferencePacket:
    flow: Hashable
    arrival: Fraction
    sequence: int
    weight: Fraction
    label: str


def wfq_reference_order(packets: Iterable[ReferencePacket]) -> list[str]:
    """Return packet labels by GPS-derived finish tag, then admission sequence."""
    last_finish: dict[Hashable, Fraction] = {}
    tagged: list[tuple[Fraction, int, str]] = []
    for packet in packets:
        if packet.weight <= 0:
            raise ValueError("weight must be positive")
        previous = last_finish.get(packet.flow, Fraction())
        finish = max(previous, packet.arrival) + Fraction(1, 1) / packet.weight
        last_finish[packet.flow] = finish
        tagged.append((finish, packet.sequence, packet.label))
    return [label for _, _, label in sorted(tagged)]
