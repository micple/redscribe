"""Tests for src/utils/api_manager.py"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import httpx
from src.utils.api_manager import APIManager, SALT_LENGTH
import src.utils.api_manager as api_mod


@pytest.fixture
def fresh_manager(tmp_path):
    config_file = tmp_path / "config.json"
    with patch.object(api_mod, "CONFIG_FILE", config_file):
        manager = APIManager()
        yield manager, config_file


class TestSaltCreation:
    def test_salt_is_created_on_first_call(self, fresh_manager):
        manager, cf = fresh_manager
        salt = manager._get_or_create_salt()
        assert isinstance(salt, bytes)
        assert len(salt) == SALT_LENGTH

    def test_salt_persistence_returns_same_salt(self, fresh_manager):
        manager, cf = fresh_manager
        salt1 = manager._get_or_create_salt()
        salt2 = manager._get_or_create_salt()
        assert salt1 == salt2

    def test_salt_stored_as_hex_in_config(self, fresh_manager):
        manager, cf = fresh_manager
        salt = manager._get_or_create_salt()
        raw = json.loads(cf.read_text())
        assert "_salt" in raw
        assert bytes.fromhex(raw["_salt"]) == salt


class TestApiKeyEncryptionDecryption:
    def test_api_key_round_trip(self, fresh_manager):
        manager, cf = fresh_manager
        manager.save_api_key("dg-test-key-abc123")
        loaded = manager.load_api_key()
        assert loaded == "dg-test-key-abc123"

    def test_encrypted_key_differs_from_plaintext(self, fresh_manager):
        manager, cf = fresh_manager
        manager.save_api_key("dg-test-key-abc123")
        raw = json.loads(cf.read_text())
        assert raw["api_key"] != "dg-test-key-abc123"

    def test_load_api_key_returns_none_when_no_key(self, fresh_manager):
        manager, cf = fresh_manager
        result = manager.load_api_key()
        assert result is None

    def test_has_api_key_false_when_no_key(self, fresh_manager):
        manager, cf = fresh_manager
        assert manager.has_api_key() is False

    def test_has_api_key_true_after_saving(self, fresh_manager):
        manager, cf = fresh_manager
        manager.save_api_key("test-key")
        assert manager.has_api_key() is True

    def test_delete_api_key_removes_key(self, fresh_manager):
        manager, cf = fresh_manager
        manager.save_api_key("test-key")
        manager.delete_api_key()
        assert manager.load_api_key() is None


class TestPreferences:
    def test_get_preference_default_value(self, fresh_manager):
        manager, cf = fresh_manager
        result = manager.get_preference("nonexistent", "default_val")
        assert result == "default_val"

    def test_set_and_get_preference(self, fresh_manager):
        manager, cf = fresh_manager
        manager.set_preference("theme", "dark")
        assert manager.get_preference("theme") == "dark"

    def test_get_model_returns_default(self, fresh_manager):
        manager, cf = fresh_manager
        assert manager.get_model() == "nova-2"

    def test_set_and_get_model(self, fresh_manager):
        manager, cf = fresh_manager
        manager.set_model("nova-3")
        assert manager.get_model() == "nova-3"

    def test_get_model_string_general_returns_base(self, fresh_manager):
        manager, cf = fresh_manager
        assert manager.get_model_string(language="en") == "nova-2"

    def test_get_model_string_with_specialization(self, fresh_manager):
        manager, cf = fresh_manager
        manager.set_specialization("meeting")
        assert manager.get_model_string(language="en") == "nova-2-meeting"

    def test_get_model_string_non_english_ignores_spec(self, fresh_manager):
        manager, cf = fresh_manager
        manager.set_specialization("meeting")
        assert manager.get_model_string(language="pl") == "nova-2"


class TestValidateApiKey:
    def test_validate_valid_key(self, fresh_manager):
        manager, cf = fresh_manager
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(get=Mock(return_value=mock_resp)))
            mc.return_value.__exit__ = Mock(return_value=False)
            valid, msg = manager.validate_api_key("good-key")
            assert valid is True

    def test_validate_invalid_key_401(self, fresh_manager):
        manager, cf = fresh_manager
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(get=Mock(return_value=mock_resp)))
            mc.return_value.__exit__ = Mock(return_value=False)
            valid, msg = manager.validate_api_key("bad-key")
            assert valid is False

    def test_validate_key_timeout(self, fresh_manager):
        manager, cf = fresh_manager
        with patch("httpx.Client") as mc:
            mc.return_value.__enter__ = Mock(return_value=MagicMock(
                get=Mock(side_effect=httpx.TimeoutException("timeout"))))
            mc.return_value.__exit__ = Mock(return_value=False)
            valid, msg = manager.validate_api_key("key")
            assert valid is False
            assert "timeout" in msg.lower()


class TestSaltSaveFailure:
    def test_salt_save_failure_raises_runtime_error(self, fresh_manager):
        """Bug #1: If salt save fails, RuntimeError should be raised instead of returning invalid salt."""
        manager, cf = fresh_manager
        with patch.object(manager, "_save_config_raw", side_effect=PermissionError("No write access")):
            with pytest.raises(RuntimeError, match="failed to save salt"):
                manager._get_or_create_salt()

    def test_salt_save_failure_does_not_persist_salt(self, fresh_manager):
        """Bug #1: Failed save should not leave partial state."""
        manager, cf = fresh_manager
        with patch.object(manager, "_save_config_raw", side_effect=OSError("Disk full")):
            with pytest.raises(RuntimeError):
                manager._get_or_create_salt()
        # Config should not contain a salt
        config = manager._load_config_raw()
        assert "_salt" not in config


class TestGetBalance:
    def test_get_balance_no_api_key_returns_none(self, fresh_manager):
        manager, cf = fresh_manager
        result = manager.get_balance()
        assert result is None
