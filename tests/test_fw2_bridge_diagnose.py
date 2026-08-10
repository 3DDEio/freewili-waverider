import pytest

from tools.fw2_bridge_diagnose import require_healthy_bridge


def test_bridge_health_accepts_clean_current_boot():
    require_healthy_bridge(
        "ActiveState=active SubState=running MainPID=412 ExecMainStatus=0 NRestarts=0",
        "Started fwcm0-bridge.service",
    )


@pytest.mark.parametrize(
    "state",
    [
        "ActiveState=failed SubState=failed MainPID=0 ExecMainStatus=1 NRestarts=4",
        "ActiveState=activating SubState=auto-restart MainPID=0 ExecMainStatus=1 NRestarts=4",
    ],
)
def test_bridge_health_rejects_non_running_state(state):
    with pytest.raises(RuntimeError, match="not healthy"):
        require_healthy_bridge(state, "")


def test_bridge_health_rejects_router_timeout_after_latest_start():
    state = "ActiveState=active SubState=running MainPID=412 ExecMainStatus=0 NRestarts=2"
    with pytest.raises(RuntimeError, match="most recent start"):
        require_healthy_bridge(
            state,
            "Started fwcm0-bridge.service - bridge~error: router timeout",
        )


def test_bridge_health_accepts_main_reset_recovery_after_older_timeout():
    state = "ActiveState=active SubState=running MainPID=412 ExecMainStatus=0 NRestarts=72"
    require_healthy_bridge(
        state,
        "error: router timeout~Failed with result 'exit-code'~"
        "Started fwcm0-bridge.service - bridge~session opened for user pi",
    )
