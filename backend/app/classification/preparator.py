from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.acquisition.normalizer import NormalizedReading


@dataclass
class ClassificationPacket:
    """Payload delivered to the traffic classification module."""

    reading: NormalizedReading
    metadata: dict[str, Any] = field(default_factory=dict)


class ClassificationPreparator:
    """Forwards normalized readings to the classification module in a stable format."""

    def __init__(self, consumer: Optional[Callable[[ClassificationPacket], None]] = None) -> None:
        self._consumer = consumer
        self._packets: list[ClassificationPacket] = []

    def prepare(self, readings: list[NormalizedReading]) -> list[ClassificationPacket]:
        packets = [
            ClassificationPacket(
                reading=reading,
                metadata={
                    "device_code": reading.device_code,
                    "device_type": reading.device_type,
                    "sensor_name": reading.sensor_name,
                    "timestamp": reading.timestamp,
                },
            )
            for reading in readings
        ]
        self._packets.extend(packets)
        if self._consumer is not None:
            for packet in packets:
                self._consumer(packet)
        return packets

    def get_packets(self) -> list[ClassificationPacket]:
        return list(self._packets)
