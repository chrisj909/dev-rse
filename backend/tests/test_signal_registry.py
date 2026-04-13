"""
Tests for SignalEngine pluggable registry — Sprint 7, Task 15.
app/signals/engine.py (SignalEngine class-level registry)

Strategy:
  - Tests are isolated: each test that mutates the class registry restores
    it via a pytest fixture that saves and restores _registry before/after.
  - No DB calls needed; we patch _upsert_signal where required.

Covers:
  - SignalEngine.register() — adds signals, callable validation
  - SignalEngine.deregister() — removes signals, KeyError for unknown names
  - SignalEngine.registered_signals() — returns snapshot list
  - Registration order — signals run in registration order
  - Replacing an existing signal — same name, new function
  - Custom signals are detected and return results via process()
    - Default registry includes all expected signals
  - Stub signals (tax_delinquent, probate, code_violation, pre_foreclosure) return False
  - process() includes all registered signals in result dict
  - process_batch() counts custom registered signals
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.signals.engine import (
    SignalEngine,
    _absentee_owner_detector,
    _long_term_owner_detector,
)


# ── Fixture: isolated registry ────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_registry():
    """
    Save and restore the class-level registry around every test in this module.
    Prevents test pollution when tests add/remove signals.
    """
    original = dict(SignalEngine._registry)
    yield
    SignalEngine._registry.clear()
    SignalEngine._registry.update(original)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_prop(
    *,
    address: str | None = "123 MAIN ST",
    city: str | None = "HOOVER",
    state: str = "AL",
    zip_code: str | None = "35244",
    mailing_address: str | None = None,
    last_sale_date: date | None = None,
) -> MagicMock:
    prop = MagicMock()
    prop.id = uuid.uuid4()
    prop.parcel_id = "SC-TEST-0001"
    prop.address = address
    prop.city = city
    prop.state = state
    prop.zip = zip_code
    prop.mailing_address = mailing_address
    prop.last_sale_date = last_sale_date
    return prop


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


# ── SignalEngine.register() ───────────────────────────────────────────────────

class TestRegister:
    """Tests for SignalEngine.register() class method."""

    def test_register_adds_signal(self):
        """register() adds a new signal to the class registry."""
        fn = lambda p: True  # noqa: E731
        SignalEngine.register("my_signal", fn)
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert "my_signal" in names

    def test_register_replaces_existing_signal(self):
        """Registering with an existing name replaces the detector."""
        fn_v1 = lambda p: False  # noqa: E731
        fn_v2 = lambda p: True   # noqa: E731
        SignalEngine.register("replaceable", fn_v1)
        SignalEngine.register("replaceable", fn_v2)
        registry = dict(SignalEngine.registered_signals())
        assert registry["replaceable"] is fn_v2

    def test_register_callable_validation(self):
        """register() raises TypeError for non-callable detector."""
        with pytest.raises(TypeError, match="must be callable"):
            SignalEngine.register("bad_signal", "not_a_function")  # type: ignore[arg-type]

    def test_register_int_raises_type_error(self):
        """register() raises TypeError when fn is an int."""
        with pytest.raises(TypeError):
            SignalEngine.register("int_signal", 42)  # type: ignore[arg-type]

    def test_register_preserves_name(self):
        """Registered signal name is preserved exactly."""
        fn = lambda p: False  # noqa: E731
        SignalEngine.register("exact_name_signal", fn)
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert "exact_name_signal" in names

    def test_register_multiple_signals(self):
        """Multiple signals can be registered."""
        for i in range(5):
            SignalEngine.register(f"multi_{i}", lambda p: False)
        names = [n for n, _ in SignalEngine.registered_signals()]
        for i in range(5):
            assert f"multi_{i}" in names

    def test_register_returns_none(self):
        """register() returns None (no return value)."""
        result = SignalEngine.register("void_signal", lambda p: False)
        assert result is None


# ── SignalEngine.deregister() ─────────────────────────────────────────────────

class TestDeregister:
    """Tests for SignalEngine.deregister() class method."""

    def test_deregister_removes_signal(self):
        """deregister() removes a signal from the registry."""
        SignalEngine.register("to_remove", lambda p: True)
        SignalEngine.deregister("to_remove")
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert "to_remove" not in names

    def test_deregister_unknown_name_raises_key_error(self):
        """deregister() raises KeyError for an unregistered name."""
        with pytest.raises(KeyError):
            SignalEngine.deregister("nonexistent_signal_xyz")

    def test_deregister_only_removes_named_signal(self):
        """Deregistering one signal does not affect others."""
        SignalEngine.register("keep_me", lambda p: True)
        SignalEngine.register("remove_me", lambda p: False)
        SignalEngine.deregister("remove_me")
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert "keep_me" in names
        assert "remove_me" not in names

    def test_deregister_after_replace_removes_latest(self):
        """Deregister after replace removes the signal entirely."""
        SignalEngine.register("cycle_signal", lambda p: True)
        SignalEngine.register("cycle_signal", lambda p: False)
        SignalEngine.deregister("cycle_signal")
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert "cycle_signal" not in names

    def test_deregister_returns_none(self):
        """deregister() returns None."""
        SignalEngine.register("disposable", lambda p: False)
        result = SignalEngine.deregister("disposable")
        assert result is None


# ── SignalEngine.registered_signals() ─────────────────────────────────────────

class TestRegisteredSignals:
    """Tests for SignalEngine.registered_signals() class method."""

    def test_returns_list(self):
        """registered_signals() returns a list."""
        assert isinstance(SignalEngine.registered_signals(), list)

    def test_returns_list_of_tuples(self):
        """Each entry is a (name, callable) tuple."""
        for item in SignalEngine.registered_signals():
            assert isinstance(item, tuple)
            assert len(item) == 2
            name, fn = item
            assert isinstance(name, str)
            assert callable(fn)

    def test_returns_snapshot_not_live_reference(self):
        """registered_signals() returns a snapshot — modifying it doesn't change the registry."""
        snapshot = SignalEngine.registered_signals()
        original_len = len(snapshot)
        snapshot.append(("mutant", lambda p: True))
        assert len(SignalEngine.registered_signals()) == original_len

    def test_registration_order_preserved(self):
        """Signals are returned in registration order."""
        # Clear registry and add in known order
        SignalEngine._registry.clear()
        for name in ["first", "second", "third"]:
            SignalEngine.register(name, lambda p: False)
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert names == ["first", "second", "third"]

    def test_default_registry_has_expected_signals(self):
        """Default registry contains the expected implemented and placeholder signals."""
        names = {n for n, _ in SignalEngine.registered_signals()}
        expected = {
            "absentee_owner",
            "long_term_owner",
            "out_of_state_owner",
            "corporate_owner",
            "tax_delinquent",
            "probate",
            "eviction",
            "code_violation",
            "pre_foreclosure",
        }
        assert expected.issubset(names)

    def test_absentee_owner_is_first(self):
        """absentee_owner is the first registered signal in default registry."""
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert names[0] == "absentee_owner"

    def test_long_term_owner_is_second(self):
        """long_term_owner is the second registered signal in default registry."""
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert names[1] == "long_term_owner"

    def test_out_of_state_owner_is_third(self):
        names = [n for n, _ in SignalEngine.registered_signals()]
        assert names[2] == "out_of_state_owner"


# ── Stub signal behavior ──────────────────────────────────────────────────────

class TestStubSignals:
    """Stub signals (tax_delinquent, probate, eviction, code_violation, pre_foreclosure) must return False."""

    @pytest.mark.asyncio
    async def test_tax_delinquent_stub_returns_false(self):
        """tax_delinquent stub returns False for any property."""
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("tax_delinquent") is False

    @pytest.mark.asyncio
    async def test_probate_stub_returns_false(self):
        """probate stub returns False for any property."""
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("probate") is False

    @pytest.mark.asyncio
    async def test_eviction_stub_returns_false(self):
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("eviction") is False

    @pytest.mark.asyncio
    async def test_code_violation_stub_returns_false(self):
        """code_violation stub returns False for any property."""
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("code_violation") is False

    @pytest.mark.asyncio
    async def test_pre_foreclosure_stub_returns_false(self):
        """pre_foreclosure stub returns False for any property."""
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("pre_foreclosure") is False

    @pytest.mark.asyncio
    async def test_all_stub_signals_in_result(self):
        """All four stub signals appear in the result dict from process()."""
        prop = _make_prop()
        session = _make_session()
        stubs = {"tax_delinquent", "probate", "code_violation", "pre_foreclosure"}

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        for stub in stubs:
            assert stub in flags, f"Missing stub signal {stub!r} in result"


# ── Custom signal integration ─────────────────────────────────────────────────

class TestCustomSignalIntegration:
    """Custom signals registered at class level run during process()."""

    @pytest.mark.asyncio
    async def test_custom_signal_runs_during_process(self):
        """A newly registered custom signal is invoked by process()."""
        call_log = []

        def custom_fn(prop):
            call_log.append(prop.parcel_id)
            return True

        SignalEngine.register("custom_active", custom_fn)
        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert "custom_active" in flags
        assert flags["custom_active"] is True
        assert prop.parcel_id in call_log

    @pytest.mark.asyncio
    async def test_deregistered_signal_not_in_result(self):
        """A deregistered signal no longer appears in process() output."""
        SignalEngine.register("temp_signal", lambda p: True)
        SignalEngine.deregister("temp_signal")

        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert "temp_signal" not in flags

    @pytest.mark.asyncio
    async def test_replaced_signal_uses_new_fn(self):
        """After replace, process() uses the new detector function."""
        SignalEngine.register("mutable_signal", lambda p: False)
        SignalEngine.register("mutable_signal", lambda p: True)  # replace

        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert flags.get("mutable_signal") is True

    @pytest.mark.asyncio
    async def test_instance_override_ignores_class_registry(self):
        """Instance with signals= override ignores class-level custom signals."""
        SignalEngine.register("ignored_class_signal", lambda p: True)

        prop = _make_prop()
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            # Instance explicitly uses only one custom signal
            engine = SignalEngine(signals=[("instance_only", lambda p: True)])
            flags = await engine.process(prop, session)

        assert "instance_only" in flags
        assert "ignored_class_signal" not in flags

    @pytest.mark.asyncio
    async def test_process_batch_counts_custom_signal(self):
        """process_batch() counts True results for custom registered signals."""
        SignalEngine.register("batch_custom", lambda p: True)

        properties = [_make_prop(address=f"PROP {i}") for i in range(4)]
        session = _make_session()

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            counts = await engine.process_batch(properties, session)

        assert counts.get("batch_custom") == 4

    @pytest.mark.asyncio
    async def test_process_includes_all_six_default_signals(self):
        """Default engine process() result includes all 6 signals."""
        prop = _make_prop()
        session = _make_session()
        expected = {
            "absentee_owner",
            "long_term_owner",
            "tax_delinquent",
            "probate",
            "code_violation",
            "pre_foreclosure",
        }

        with patch.object(SignalEngine, "_upsert_signal", new_callable=AsyncMock):
            engine = SignalEngine()
            flags = await engine.process(prop, session)

        assert expected.issubset(set(flags.keys()))

    @pytest.mark.asyncio
    async def test_instance_signals_property_returns_override(self):
        """_signals property on override instance returns the override list."""
        custom = [("x", lambda p: False)]
        engine = SignalEngine(signals=custom)
        assert engine._signals is custom

    @pytest.mark.asyncio
    async def test_instance_signals_property_returns_class_registry(self):
        """_signals property on default instance returns class registry snapshot."""
        engine = SignalEngine()
        snap = engine._signals
        class_snap = SignalEngine.registered_signals()
        assert snap == class_snap
