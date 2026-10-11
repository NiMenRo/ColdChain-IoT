"""tsk0594_integrity_checks

TSK-059.4 — integrity hardening over critical data (thresholds,
classification, QoS ranges, energy). Pre-checks abort without silently
normalizing incompatible rows.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b72d1f4c4403"
down_revision: Union[str, Sequence[str], None] = "a41c8e9d3202"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_PRECHECKS = [
    (
        "system_configs",
        "min_temperature > max_temperature OR min_humidity > max_humidity",
    ),
    (
        "traffic_classifications",
        "criticality < 3 OR criticality > 9",
    ),
    (
        "traffic_classifications",
        "priority NOT IN ('low','medium','high')",
    ),
    (
        "traffic_classifications",
        "queue NOT IN ('FIFO','Round Robin','WFQ')",
    ),
    (
        "qos_metrics",
        "latency < 0 OR throughput < 0 OR jitter < 0",
    ),
    (
        "qos_metrics",
        "pdr < 0 OR pdr > 100 OR packet_loss < 0 OR packet_loss > 100",
    ),
    (
        "sensor_readings",
        "energy IS NOT NULL AND energy NOT IN ('on','off')",
    ),
]

_CHECKS = [
    (
        "system_configs",
        "ck_system_config_temp_range",
        "min_temperature <= max_temperature",
    ),
    (
        "system_configs",
        "ck_system_config_hum_range",
        "min_humidity <= max_humidity",
    ),
    (
        "traffic_classifications",
        "ck_tc_criticality",
        "criticality >= 3 AND criticality <= 9",
    ),
    (
        "traffic_classifications",
        "ck_tc_priority",
        "priority IN ('low','medium','high')",
    ),
    (
        "traffic_classifications",
        "ck_tc_queue",
        "queue IN ('FIFO','Round Robin','WFQ')",
    ),
    ("qos_metrics", "ck_qos_latency", "latency >= 0"),
    (
        "qos_metrics",
        "ck_qos_packet_loss",
        "packet_loss >= 0 AND packet_loss <= 100",
    ),
    ("qos_metrics", "ck_qos_throughput", "throughput >= 0"),
    ("qos_metrics", "ck_qos_pdr", "pdr >= 0 AND pdr <= 100"),
    ("qos_metrics", "ck_qos_jitter", "jitter >= 0"),
    (
        "sensor_readings",
        "ck_readings_energy",
        "energy IS NULL OR energy IN ('on','off')",
    ),
]


def upgrade() -> None:
    from alembic import context as alembic_context

    # Pre-checks (no silent normalization) — online mode only
    if not alembic_context.is_offline_mode():
        bind = op.get_bind()
        if bind is not None:
            for table, condition in _PRECHECKS:
                count = bind.execute(
                    sa.text(f"SELECT COUNT(*) FROM {table} WHERE {condition}")
                ).scalar()
                if count:
                    raise RuntimeError(
                        f"tsk0594: table '{table}' has {count} row(s) violating "
                        f"'{condition}'; fix data manually before upgrading"
                    )
    for table, name, expression in _CHECKS:
        op.create_check_constraint(name, table, expression)


def downgrade() -> None:
    for table, name, _expression in reversed(_CHECKS):
        op.drop_constraint(name, table, type_="check")
