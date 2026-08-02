"""Local network-address helpers used to enrich portal session details."""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

from PySide6.QtNetwork import QNetworkAddressEntry, QNetworkInterface


def _select_preferred_ipv6(
    candidates: Iterable[tuple[str, bool, bool]],
) -> str:
    """Select a global IPv6, preferring the IPv4-matched interface and DNS use."""
    valid: list[tuple[int, str]] = []
    for address, same_interface, dns_eligible in candidates:
        normalized = address.split("%", 1)[0]
        try:
            parsed = ipaddress.IPv6Address(normalized)
        except ipaddress.AddressValueError:
            continue
        if not parsed.is_global:
            continue
        score = (2 if same_interface else 0) + (1 if dns_eligible else 0)
        valid.append((score, normalized))
    if not valid:
        return ""
    return max(valid, key=lambda item: item[0])[1]


def find_local_ipv6(ipv4_hint: str = "") -> str:
    """Return a usable IPv6 from an active Windows interface."""
    candidates: list[tuple[str, bool, bool]] = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not (
            flags & QNetworkInterface.InterfaceFlag.IsUp
            and flags & QNetworkInterface.InterfaceFlag.IsRunning
        ):
            continue
        entries = interface.addressEntries()
        same_interface = bool(
            ipv4_hint
            and any(entry.ip().toString() == ipv4_hint for entry in entries)
        )
        for entry in entries:
            dns_eligible = (
                entry.dnsEligibility()
                == QNetworkAddressEntry.DnsEligibilityStatus.DnsEligible
            )
            candidates.append(
                (entry.ip().toString(), same_interface, dns_eligible)
            )
    return _select_preferred_ipv6(candidates)
