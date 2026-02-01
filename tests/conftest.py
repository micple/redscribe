import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock
import os
import sys

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def sample_audio_file(tmp_path):
    file_path = tmp_path / "test_audio.mp3"
    file_path.write_bytes(b"fake mp3 content " + b"x" * 1024)
    return file_path


@pytest.fixture
def sample_video_file(tmp_path):
    file_path = tmp_path / "test_video.mp4"
    file_path.write_bytes(b"fake mp4 content " + b"x" * 1024)
    return file_path


@pytest.fixture
def mock_api_manager():
    manager = MagicMock()
    manager.load_api_key.return_value = "test-api-key-123"
    manager.has_api_key.return_value = True
    manager.get_model.return_value = "nova-2"
    manager.get_specialization.return_value = "general"
    manager.get_model_string.return_value = "nova-2"
    manager.get_preference.return_value = None
    return manager
