"""Tests for local IPv6 address selection."""

from src.core.network_addresses import _select_preferred_ipv6


def test_ipv6_selection_prefers_matched_interface_then_dns_eligibility():
    selected = _select_preferred_ipv6(
        [
            ("fe80::1", True, True),
            ("2606:4700:4700::1001", False, True),
            ("2606:4700:4700::1001", True, False),
            ("2606:4700:4700::1111", True, True),
        ]
    )

    assert selected == "2606:4700:4700::1111"
