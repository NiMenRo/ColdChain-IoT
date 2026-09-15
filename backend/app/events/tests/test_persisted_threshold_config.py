from __future__ import annotations

import uuid
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.acquisition.normalizer import NormalizedReading
from app.database.infrastructure.base import Base
from app.database.infrastructure.models import SystemConfigORM
from app.database.infrastructure.repositories import SystemConfigRepository
from app.events.application.rule_engine import RuleEngine
from app.events.domain import ThresholdConfig


class PersistedThresholdConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_threshold_config_is_built_from_system_config(self) -> None:
        self.session.add(
            SystemConfigORM(
                id=uuid.uuid4(),
                min_temperature=10.0,
                max_temperature=12.0,
                min_humidity=40.0,
                max_humidity=60.0,
                qos_algorithm="wfq",
                qos_enabled=True,
            )
        )
        self.session.commit()

        persisted = SystemConfigRepository().get_current(self.session)
        config = ThresholdConfig.from_persisted_config(persisted)

        self.assertEqual(config.min_temperature, 10.0)
        self.assertEqual(config.max_temperature, 12.0)
        self.assertEqual(config.min_humidity, 40.0)
        self.assertEqual(config.max_humidity, 60.0)

    def test_rule_engine_uses_changed_persisted_thresholds(self) -> None:
        persisted = SystemConfigORM(
            id=uuid.uuid4(),
            min_temperature=10.0,
            max_temperature=12.0,
            min_humidity=40.0,
            max_humidity=60.0,
            qos_algorithm="wfq",
            qos_enabled=True,
        )
        config = ThresholdConfig.from_persisted_config(persisted)
        reading = NormalizedReading(
            device_code="CAVA-001",
            device_type="cold_room",
            sensor_name="temperature",
            value=5.0,
            timestamp="2026-09-14T00:00:00+00:00",
            raw_value=5.0,
        )

        evaluation = RuleEngine(config).evaluate([reading])[0]

        self.assertTrue(evaluation.breached)
        self.assertEqual(evaluation.threshold, (10.0, 12.0))


if __name__ == "__main__":
    unittest.main()
