"""Tests for GuetLinker network monitor."""

import pytest

from src.core.monitor import NetworkMonitor, NetworkStatus, _ProbeResult
from src.core.network_speed import NetworkSpeed
from src.core.portal import PortalPageState, PortalSession
from tests.test_portal import ONLINE_PAGE


LOGIN_REQUIRED = PortalSession(state=PortalPageState.LOGIN_REQUIRED)
ONLINE_SESSION = PortalSession(
    state=PortalPageState.ONLINE,
    user_id="20240001",
    ipv4="192.0.2.10",
)


class TestNetworkStatus:
    """Tests for NetworkStatus enum."""

    def test_values(self):
        assert NetworkStatus.CONNECTED.value == "connected"
        assert NetworkStatus.DISCONNECTED.value == "disconnected"
        assert NetworkStatus.RECONNECTING.value == "reconnecting"
        assert NetworkStatus.UNKNOWN.value == "unknown"


class TestNetworkMonitor:
    """Tests for the NetworkMonitor class."""

    def test_initial_status(self):
        """Monitor should start in UNKNOWN status."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        assert monitor.status == NetworkStatus.UNKNOWN

    def test_set_interval(self):
        """Interval should be updatable."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/", check_interval=30)
        assert monitor.check_interval == 30
        monitor.set_interval(60)
        assert monitor.check_interval == 60

    def test_status_signals(self, qapp):
        """Status changes should emit signals."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        received = []
        monitor.status_changed.connect(lambda s: received.append(s))

        # Directly set status
        monitor._set_status(NetworkStatus.CONNECTED)
        assert len(received) == 1
        assert received[0] == NetworkStatus.CONNECTED

        # Same status should not emit
        monitor._set_status(NetworkStatus.CONNECTED)
        assert len(received) == 1

        # Different status should emit
        monitor._set_status(NetworkStatus.DISCONNECTED)
        assert len(received) == 2
        assert received[1] == NetworkStatus.DISCONNECTED

    def test_consecutive_failures(self, monkeypatch):
        """Status should only change after consecutive failures reach threshold."""
        monitor = NetworkMonitor(
            portal_url="http://10.0.1.5/",
            failure_threshold=2,
        )
        monkeypatch.setattr(monitor, "_check_external", lambda: False)
        monkeypatch.setattr(monitor, "_fetch_portal_session", lambda: LOGIN_REQUIRED)
        monitor._status = NetworkStatus.CONNECTED

        assert monitor.check_network() == NetworkStatus.CONNECTED
        assert monitor.check_network() == NetworkStatus.DISCONNECTED

    def test_reconnect_requested_on_each_disconnected_check(self, monkeypatch):
        """Failed reconnects receive a new request on later monitor ticks."""
        monitor = NetworkMonitor(
            portal_url="http://10.0.1.5/",
            failure_threshold=1,
        )
        monkeypatch.setattr(monitor, "_check_external", lambda: False)
        monkeypatch.setattr(monitor, "_fetch_portal_session", lambda: LOGIN_REQUIRED)
        requests = []
        monitor.reconnect_requested.connect(lambda: requests.append(True))

        monitor.check_network()
        monitor.check_network()
        assert len(requests) == 2

    def test_reconnect_guard_prevents_concurrent_requests(self, monkeypatch):
        """An in-flight reconnect suppresses new reconnect signals."""
        monitor = NetworkMonitor(
            portal_url="http://10.0.1.5/",
            failure_threshold=1,
        )
        monkeypatch.setattr(monitor, "_check_external", lambda: False)
        monkeypatch.setattr(monitor, "_fetch_portal_session", lambda: LOGIN_REQUIRED)
        requests = []
        monitor.reconnect_requested.connect(lambda: requests.append(True))

        assert monitor.begin_reconnect() is True
        monitor.check_network()
        assert requests == []
        assert monitor.status == NetworkStatus.RECONNECTING
        monitor.finish_reconnect()
        monitor.check_network()
        assert requests == [True]

    def test_external_redirect_is_not_connected(self, monkeypatch):
        """Captive-portal redirects must not be accepted as public connectivity."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")

        class Response:
            is_redirect = True
            status_code = 302
            text = ""

        monkeypatch.setattr(monitor._client, "get", lambda _: Response())
        assert monitor._check_external() is False

    def test_online_portal_session_is_connected_without_external_probe(self, monkeypatch):
        """An authenticated portal page is enough to report the user online."""
        monitor = NetworkMonitor(
            portal_url="http://10.0.1.5/",
            failure_threshold=1,
        )
        external_calls = []
        monkeypatch.setattr(
            monitor,
            "_check_external",
            lambda: external_calls.append(True) or False,
        )
        monkeypatch.setattr(monitor, "_fetch_portal_session", lambda: ONLINE_SESSION)

        assert monitor.check_network() == NetworkStatus.CONNECTED
        assert external_calls == []

    def test_verified_login_session_is_published_immediately(self):
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        sessions = []
        monitor.portal_session_changed.connect(sessions.append)

        monitor.accept_verified_session(ONLINE_SESSION)

        assert monitor.status == NetworkStatus.CONNECTED
        assert monitor.portal_session == ONLINE_SESSION
        assert sessions == [ONLINE_SESSION]
        monitor.close()

    def test_online_probe_fills_delayed_ipv6_from_local_interface(
        self,
        monkeypatch,
    ):
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        html = ONLINE_PAGE.replace(
            "v6ip='2001:db8::1';",
            "v6ip='';",
        )

        class Response:
            status_code = 200
            text = html

        monkeypatch.setattr(monitor._client, "get", lambda *_: Response())
        monkeypatch.setattr(
            "src.core.monitor.find_local_ipv6",
            lambda ipv4: "2001:db8::8",
        )

        session = monitor._fetch_portal_session()

        assert session.is_online is True
        assert session.ipv6 == "2001:db8::8"
        monitor.close()

    def test_external_connection_is_connected_when_portal_is_unknown(self, monkeypatch):
        """A non-campus network remains connected even without a portal session."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        monkeypatch.setattr(monitor, "_fetch_portal_session", lambda: PortalSession())
        monkeypatch.setattr(monitor, "_check_external", lambda: True)

        assert monitor.check_network() == NetworkStatus.CONNECTED

    def test_interval_is_clamped(self):
        """Monitoring intervals remain within the UI-supported bounds."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        monitor.set_interval(0)
        assert monitor.check_interval == 10
        monitor.set_interval(999)
        assert monitor.check_interval == 300

    def test_status_poll_interval_defaults_to_500ms(self):
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        assert monitor.status_poll_interval_ms == 500
        assert monitor._status_timer.interval() == 500
        monitor.close()

    def test_speed_tick_publishes_current_throughput(self):
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        expected = NetworkSpeed(download_bps=2048, upload_bps=1024)
        received = []
        monitor._speed_sampler.sample = lambda: expected
        monitor.speed_changed.connect(received.append)

        monitor._on_speed_timeout()

        assert received == [expected]
        monitor.close()

    def test_realtime_poll_detects_browser_login_after_manual_disconnect(
        self,
        monkeypatch,
        qtbot,
    ):
        """A 500 ms background poll restores online state after Web login."""
        monitor = NetworkMonitor(
            portal_url="http://10.0.1.5/",
            status_poll_interval_ms=500,
        )
        monitor.mark_disconnected()
        monkeypatch.setattr(
            monitor,
            "_run_probe",
            lambda include_external: _ProbeResult(
                portal_session=ONLINE_SESSION,
            ),
        )

        monitor._on_status_timeout()
        qtbot.waitUntil(
            lambda: monitor.status == NetworkStatus.CONNECTED,
            timeout=2000,
        )

        assert monitor.portal_session == ONLINE_SESSION
        monitor.close()

    def test_probe_started_before_manual_action_is_ignored(self):
        """A stale pre-logout online result must not overwrite manual state."""
        monitor = NetworkMonitor(portal_url="http://10.0.1.5/")
        old_generation = monitor._probe_generation
        monitor.mark_disconnected()
        monitor.invalidate_pending_probe()

        monitor._on_probe_completed(
            (
                _ProbeResult(portal_session=ONLINE_SESSION),
                False,
                old_generation,
            )
        )

        assert monitor.status == NetworkStatus.DISCONNECTED
        assert monitor.portal_session.state == PortalPageState.LOGIN_REQUIRED
        monitor.close()
