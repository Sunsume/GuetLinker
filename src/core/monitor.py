"""GuetLinker network monitor.

Uses QTimer to periodically check network connectivity and
automatically triggers re-authentication when disconnected.
"""

from __future__ import annotations

import enum
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace

import httpx
from PySide6.QtCore import QObject, QTimer, Signal, Slot

from src.core.network_addresses import find_local_ipv6
from src.core.portal import PortalPageState, PortalSession, parse_portal_page

logger = logging.getLogger("guetlinker.monitor")

STATUS_POLL_INTERVAL_MS = 500
PORTAL_REFRESH_HEADERS = {
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
}


class NetworkStatus(enum.Enum):
    """Network connectivity status."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _ProbeResult:
    portal_session: PortalSession
    external_reachable: bool | None = None


class NetworkMonitor(QObject):
    """Periodic network connectivity monitor.

    Checks connectivity by:
        1. HTTP GET to an external site (baidu.com)
        2. HTTP GET to the portal gateway (10.0.1.5)

    Only triggers status change after consecutive failures to
    avoid false positives from transient network issues.

    Signals:
        status_changed: Emitted when network status changes.
    """

    status_changed = Signal(object)  # NetworkStatus
    reconnect_requested = Signal()
    portal_session_changed = Signal(object)  # PortalSession
    check_completed = Signal()
    _probe_completed = Signal(object)

    # HTTPS endpoints with a well-defined 204 response. Any redirect or
    # unexpected response is treated as a captive-portal/disconnected state.
    CHECK_URLS = [
        "https://connectivitycheck.gstatic.com/generate_204",
        "https://www.msftconnecttest.com/connecttest.txt",
    ]
    EXPECTED_STATUS_CODES = {204, 200}

    def __init__(
        self,
        portal_url: str = "http://10.0.1.5/",
        check_interval: int = 30,
        failure_threshold: int = 2,
        timeout: float = 5.0,
        status_poll_interval_ms: int = STATUS_POLL_INTERVAL_MS,
    ) -> None:
        super().__init__()
        self.portal_url = portal_url
        self.check_interval = check_interval
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.status_poll_interval_ms = max(100, status_poll_interval_ms)

        self._status = NetworkStatus.UNKNOWN
        self._portal_session = PortalSession()
        self._consecutive_failures = 0
        self._reconnect_in_progress = False
        self._probe_in_progress = False
        self._probe_generation = 0
        self._closed = False

        # A fast timer detects browser-side login/logout transitions. A separate
        # slower timer controls external-network probes and reconnect retries.
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(self.status_poll_interval_ms)
        self._status_timer.timeout.connect(self._on_status_timeout)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._probe_completed.connect(self._on_probe_completed)
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="guetlinker-network",
        )

        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=False,
            # Campus portal traffic must bypass environment proxies.
            trust_env=False,
            headers=PORTAL_REFRESH_HEADERS,
        )

    # ── Public API ────────────────────────────────────────────────

    @property
    def status(self) -> NetworkStatus:
        return self._status

    @property
    def is_running(self) -> bool:
        """Whether periodic network monitoring is active."""
        return self._status_timer.isActive()

    @property
    def portal_session(self) -> PortalSession:
        """Latest public session information parsed from the portal."""
        return self._portal_session

    def start(self) -> None:
        """Start periodic network monitoring."""
        logger.info(
            "Starting network monitor (status_poll=%dms, external_interval=%ds, threshold=%d)",
            self.status_poll_interval_ms, self.check_interval, self.failure_threshold,
        )
        self._status_timer.start()
        self._timer.start(self.check_interval * 1000)
        # Schedule an immediate non-blocking first check.
        self._schedule_probe(include_external=True, request_reconnect=True)

    def stop(self) -> None:
        """Stop monitoring."""
        self._status_timer.stop()
        self._timer.stop()
        logger.info("Network monitor stopped")

    def set_interval(self, seconds: int) -> None:
        """Update the check interval (takes effect on next timer tick)."""
        self.check_interval = max(10, min(300, seconds))
        if self._timer.isActive():
            self._timer.setInterval(self.check_interval * 1000)

    def begin_reconnect(self) -> bool:
        """Mark a login attempt in progress unless one is already running."""
        if self._reconnect_in_progress:
            return False
        self._reconnect_in_progress = True
        self._set_status(NetworkStatus.RECONNECTING)
        return True

    def finish_reconnect(self) -> None:
        """Allow a subsequent periodic check to request another reconnect."""
        self._reconnect_in_progress = False

    def cancel_reconnect(self) -> None:
        """Leave reconnecting state after a cancelled or failed login."""
        self._reconnect_in_progress = False
        if self._portal_session.state == PortalPageState.LOGIN_REQUIRED:
            self._set_status(NetworkStatus.DISCONNECTED)
        else:
            self._set_status(NetworkStatus.UNKNOWN)

    def request_check(self) -> None:
        """Schedule a non-blocking full network check."""
        self._schedule_probe(include_external=True, request_reconnect=True)

    def accept_verified_session(self, session: PortalSession) -> None:
        """Immediately publish a session already verified by AuthClient."""
        if not session.is_online:
            return
        self._consecutive_failures = 0
        self._set_portal_session(session)
        self._set_status(NetworkStatus.CONNECTED)

    def invalidate_pending_probe(self) -> None:
        """Ignore any portal result that started before a user action."""
        self._probe_generation += 1

    def check_network(self) -> NetworkStatus:
        """Synchronously check connectivity now.

        Returns:
            Current network status after check.
        """
        result = self._run_probe(include_external=True)
        self._apply_probe_result(result, request_reconnect=True)
        return self._status

    # ── Private ───────────────────────────────────────────────────

    def _run_probe(self, include_external: bool) -> _ProbeResult:
        """Perform HTTP work without touching Qt widgets or timers."""
        portal_session = self._fetch_portal_session()
        external_reachable = None
        if include_external and portal_session.state == PortalPageState.UNKNOWN:
            external_reachable = self._check_external()
        return _ProbeResult(
            portal_session=portal_session,
            external_reachable=external_reachable,
        )

    def _apply_probe_result(
        self,
        result: _ProbeResult,
        request_reconnect: bool,
    ) -> None:
        """Apply one completed probe on the monitor's Qt thread."""
        portal_session = result.portal_session
        self._set_portal_session(portal_session)

        if portal_session.is_online:
            self._consecutive_failures = 0
            self._set_status(NetworkStatus.CONNECTED)
            logger.debug("Network check: CONNECTED (portal session online)")
        elif result.external_reachable is True:
            self._consecutive_failures = 0
            self._set_status(NetworkStatus.CONNECTED)
            logger.debug("Network check: CONNECTED (external reachable)")
        elif (
            portal_session.state == PortalPageState.LOGIN_REQUIRED
            or result.external_reachable is False
        ):
            self._consecutive_failures += 1
            logger.debug(
                "Network check: failed (consecutive=%d, portal_state=%s)",
                self._consecutive_failures, portal_session.state.value,
            )

            if self._consecutive_failures >= self.failure_threshold:
                if portal_session.state == PortalPageState.LOGIN_REQUIRED:
                    if not self._reconnect_in_progress:
                        became_disconnected = (
                            self._status != NetworkStatus.DISCONNECTED
                        )
                        self._set_status(NetworkStatus.DISCONNECTED)
                        if became_disconnected or request_reconnect:
                            self.reconnect_requested.emit()
                else:
                    self._set_status(NetworkStatus.UNKNOWN)
        # A fast portal-only probe that cannot reach/classify the portal leaves
        # the current state untouched until the slower full probe runs.

        self.check_completed.emit()

    def _on_timeout(self) -> None:
        """Slower full probe and reconnect-retry tick."""
        self._schedule_probe(include_external=True, request_reconnect=True)

    def _on_status_timeout(self) -> None:
        """500 ms portal-session poll used for real-time UI updates."""
        self._schedule_probe(include_external=False, request_reconnect=False)

    def _schedule_probe(
        self,
        include_external: bool,
        request_reconnect: bool,
    ) -> None:
        """Schedule at most one background network request at a time."""
        if self._closed or self._probe_in_progress:
            return
        self._probe_in_progress = True
        generation = self._probe_generation
        future = self._executor.submit(self._run_probe, include_external)
        future.add_done_callback(
            lambda completed: self._forward_probe_result(
                completed,
                request_reconnect,
                generation,
            )
        )

    def _forward_probe_result(
        self,
        future: Future[_ProbeResult],
        request_reconnect: bool,
        generation: int,
    ) -> None:
        """Forward a worker result through a Qt signal to the owning thread."""
        try:
            result = future.result()
        except Exception:
            logger.exception("Background network probe failed")
            result = _ProbeResult(portal_session=PortalSession())
        if not self._closed:
            self._probe_completed.emit(
                (result, request_reconnect, generation)
            )

    @Slot(object)
    def _on_probe_completed(self, payload: object) -> None:
        """Apply a worker result in the QObject's thread."""
        self._probe_in_progress = False
        result, request_reconnect, generation = payload
        if generation != self._probe_generation:
            return
        self._apply_probe_result(result, request_reconnect)

    def _set_status(self, status: NetworkStatus) -> None:
        """Update status and emit signal if changed."""
        if self._status != status:
            old = self._status
            self._status = status
            logger.info("Status changed: %s → %s", old.value, status.value)
            self.status_changed.emit(status)

    def _check_external(self) -> bool:
        """Check whether an external connectivity probe returns its expected result."""
        for url in self.CHECK_URLS:
            try:
                response = self._client.get(url)
                # A captive portal commonly responds with a redirect or a login
                # page. Neither is evidence that public connectivity is working.
                if response.is_redirect:
                    continue
                if response.status_code == 204:
                    return True
                if response.status_code == 200 and url.endswith("connecttest.txt"):
                    if "Microsoft Connect Test" in response.text:
                        return True
            except httpx.HTTPError:
                continue
        return False

    def _fetch_portal_session(self) -> PortalSession:
        """Fetch and classify the portal page without emitting Qt signals."""
        try:
            response = self._client.get(self.portal_url)
            if response.status_code != 200:
                session = PortalSession()
            else:
                session = parse_portal_page(response.text, self.portal_url)
                if session.is_online and not session.ipv6:
                    session = replace(
                        session,
                        ipv6=find_local_ipv6(session.ipv4),
                    )
        except httpx.HTTPError:
            session = PortalSession()
        return session

    def _check_portal(self) -> PortalSession:
        """Synchronously fetch, store, and return portal session data."""
        session = self._fetch_portal_session()
        self._set_portal_session(session)
        return session

    def mark_disconnected(self) -> None:
        """Record a confirmed manual logout without triggering auto-reconnect."""
        self._consecutive_failures = self.failure_threshold
        self._set_portal_session(
            PortalSession(state=PortalPageState.LOGIN_REQUIRED)
        )
        self._set_status(NetworkStatus.DISCONNECTED)

    def _set_portal_session(self, session: PortalSession) -> None:
        """Update parsed portal session details and emit when they change."""
        if self._portal_session != session:
            self._portal_session = session
            self.portal_session_changed.emit(session)

    def close(self) -> None:
        """Clean up resources."""
        self.stop()
        self._closed = True
        self._client.close()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
