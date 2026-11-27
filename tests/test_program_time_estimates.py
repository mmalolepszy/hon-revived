"""Program time estimates are anchored to device observations."""

# pylint: disable=protected-access,redefined-outer-name

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from custom_components.hon import switch


@pytest.fixture
def setup_switch():
    now = datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    values = {
        "remainingTimeMM": 60,
        "delayTime": 30,
        "prCode": 10,
        "prPosition": 1,
        "programName": "cotton",
        "machMode": 5,
        "prPhase": 0,
        "active": False,
        "pause": False,
    }
    device = SimpleNamespace(
        get=lambda key, default=None: values.get(key, default),
        connection=True,
        unique_id="device",
    )
    coordinator = SimpleNamespace(last_update_success=True)
    hass = SimpleNamespace(
        data={"hon": {"entry": {"coordinator": coordinator, "hon": None}}}
    )
    entry = SimpleNamespace(unique_id="entry")
    with patch.object(switch, "datetime") as clock:
        clock.now.return_value = now
        entities = [
            switch.HonControlSwitchEntity(
                hass, entry, device, switch.HonControlSwitchEntityDescription(key=key)
            )
            for key in ("active", "pause")
        ]
        for entity in entities:
            entity.schedule_update_ha_state = Mock()
        yield SimpleNamespace(
            now=now,
            values=values,
            device=device,
            coordinator=coordinator,
            clock=clock,
            entities=entities,
        )


def observe(context, **changes):
    context.values.update(changes)
    for entity in context.entities:
        entity._handle_coordinator_update(False)
    return context.entities[0].extra_state_attributes


def test_initial_estimates_and_unchanged_reads_stay_stable(setup_switch):
    ctx = setup_switch
    first = ctx.entities[0].extra_state_attributes
    assert first == {
        "start_time": ctx.now + timedelta(minutes=30),
        "end_time": ctx.now + timedelta(minutes=90),
    }
    assert ctx.entities[1].extra_state_attributes == first
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=9)
    assert observe(ctx) == first
    assert ctx.entities[0].extra_state_attributes == first
    ctx.entities[0].extra_state_attributes.clear()
    assert ctx.entities[0].extra_state_attributes == first


def test_countdown_correction_and_new_program(setup_switch):
    ctx = setup_switch
    first = ctx.entities[0].extra_state_attributes
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=1)
    assert observe(ctx, delayTime=29) == first
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=2)
    result = observe(ctx, remainingTimeMM=75, delayTime=35)
    assert result["start_time"] == ctx.now + timedelta(minutes=37)
    assert result["end_time"] == ctx.now + timedelta(minutes=112)
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=4)
    assert observe(ctx, prCode=11)["end_time"] == ctx.now + timedelta(minutes=114)


def test_running_pause_resume_and_unavailable(setup_switch):
    ctx = setup_switch
    running = observe(ctx, machMode=2, delayTime=0, active=True)
    assert "start_time" not in running
    assert running["end_time"] == ctx.now + timedelta(minutes=60)
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=5)
    assert observe(ctx, machMode=3, pause=True) == {}
    ctx.clock.now.return_value = ctx.now + timedelta(minutes=10)
    assert observe(ctx, machMode=2, pause=False)["end_time"] == ctx.now + timedelta(
        minutes=70
    )
    ctx.coordinator.last_update_success = False
    assert observe(ctx) == {}
    ctx.coordinator.last_update_success = True
    ctx.device.connection = False
    assert observe(ctx) == {}
    ctx.device.connection = True
    assert observe(ctx)["end_time"] == ctx.now + timedelta(minutes=70)
    assert observe(ctx, remoteCtrValid=0) == {}
    assert "end_time" in observe(ctx, remoteCtrValid=1)


@pytest.mark.parametrize(
    "invalid", [None, False, True, "bad", float("nan"), float("inf"), -1, 0]
)
def test_invalid_remaining_durations_are_unknown(setup_switch, invalid):
    assert observe(setup_switch, remainingTimeMM=invalid) == {}


@pytest.mark.parametrize(
    "invalid", [None, False, True, "bad", float("nan"), float("inf"), -1]
)
def test_invalid_delay_durations_are_unknown(setup_switch, invalid):
    assert observe(setup_switch, delayTime=invalid) == {}


def test_numeric_strings_and_boolean_replacing_integer(setup_switch):
    ctx = setup_switch
    assert "end_time" in observe(ctx, remainingTimeMM="60", delayTime="30")
    assert "end_time" in observe(ctx, remainingTimeMM=1, delayTime=0)
    assert observe(ctx, remainingTimeMM=True) == {}
    assert "end_time" in observe(ctx, remainingTimeMM=60, delayTime=1)
    assert observe(ctx, delayTime=True) == {}
