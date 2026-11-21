from fractions import Fraction

import pytest

from app.qos.tests.wfq_reference import ReferencePacket, wfq_reference_order


def packet(flow, arrival, sequence, weight, label):
    return ReferencePacket(
        flow=flow, arrival=Fraction(arrival), sequence=sequence,
        weight=Fraction(weight), label=label,
    )


def test_equal_weight_flows_alternate_by_finish_tags():
    packets = [
        packet("a", 0, 0, 1, "a1"), packet("b", 0, 1, 1, "b1"),
        packet("a", 0, 2, 1, "a2"), packet("b", 0, 3, 1, "b2"),
    ]
    assert wfq_reference_order(packets) == ["a1", "b1", "a2", "b2"]


def test_two_to_one_weights_receive_shorter_finish_tags():
    packets = [
        packet("a", 0, 0, 2, "a1"), packet("b", 0, 1, 1, "b1"),
        packet("a", 0, 2, 2, "a2"), packet("a", 0, 3, 2, "a3"),
        packet("b", 0, 4, 1, "b2"),
    ]
    assert wfq_reference_order(packets) == ["a1", "b1", "a2", "a3", "b2"]


def test_equal_finish_tags_use_global_admission_sequence():
    packets = [
        packet("a", 0, 9, 1, "a-late"), packet("b", 0, 3, 1, "b-early"),
    ]
    assert wfq_reference_order(packets) == ["b-early", "a-late"]


def test_reactivated_flow_uses_its_arrival_virtual_time_not_old_idle_time():
    packets = [
        packet("a", 0, 0, 1, "a1"),
        packet("b", 0, 1, 1, "b1"),
        packet("a", 3, 2, 1, "a2-after-idle"),
        packet("b", 0, 3, 1, "b2"),
    ]
    assert wfq_reference_order(packets) == ["a1", "b1", "b2", "a2-after-idle"]


def test_oracle_rejects_non_positive_weight():
    with pytest.raises(ValueError, match="positive"):
        wfq_reference_order([packet("a", 0, 0, 0, "bad")])
