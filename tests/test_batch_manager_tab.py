"""Tests for src/gui/batch_manager_tab.py

Test with mocked GUI (no actual tkinter window):
- Mock ctk widgets
- Test _create_batch_card() returns correct data structure
- Test _populate_detail_panel() sets correct labels
- Test action methods call correct BatchHistoryManager methods
- Keep tests simple — focus on logic not GUI rendering

NOTE: These tests require a display (Tk initialization).
They are skipped in headless/CI environments.
"""
import pytest
import sys
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime
from pathlib import Path

from contracts.batch_state import (
    BatchState, BatchSettings, FileState, BatchStatistics,
    TranscriptionStatusEnum, BatchStatus
)

# Skip entire module if customtkinter cannot initialize (headless environment)
try:
    import customtkinter  # noqa: F401
    _ctk_available = True
except Exception:
    _ctk_available = False

pytestmark = pytest.mark.skipif(
    not _ctk_available,
    reason="CustomTkinter not available (headless environment)"
)


@pytest.fixture
def mock_parent():
    """Mock CustomTkinter parent widget."""
    parent = MagicMock()
    return parent


@pytest.fixture
def mock_api_manager():
    """Mock APIManager."""
    manager = MagicMock()
    manager.get_api_key.return_value = "test-key"
    return manager


@pytest.fixture
def mock_main_window():
    """Mock MainWindow."""
    window = MagicMock()
    window.tab_selector = MagicMock()
    window._resume_batch = MagicMock()
    return window


@pytest.fixture
def sample_batch_state():
    """Create a sample BatchState for testing."""
    settings = BatchSettings(
        output_format="txt",
        output_dir="/output",
        language="en",
        diarize=False,
        smart_format=True,
        max_concurrent_workers=3
    )

    files = [
        FileState(
            source_path="/path/to/audio1.mp3",
            status=TranscriptionStatusEnum.PENDING
        ),
        FileState(
            source_path="/path/to/audio2.mp3",
            status=TranscriptionStatusEnum.FAILED,
            error_message="Network error"
        ),
        FileState(
            source_path="/path/to/audio3.mp3",
            status=TranscriptionStatusEnum.COMPLETED,
            output_path="/path/to/audio3.txt",
            duration_seconds=120.5,
            completed_at=datetime.now()
        )
    ]

    statistics = BatchStatistics(
        total_files=3,
        completed=1,
        failed=1,
        pending=1,
        total_duration_seconds=120.5
    )

    return BatchState(
        batch_id="test-batch-123",
        created_at=datetime.now(),
        last_updated=datetime.now(),
        settings=settings,
        files=files,
        statistics=statistics,
        status=BatchStatus.ACTIVE,
        completed_at=None
    )


class TestBatchManagerTabInitialization:
    """Test BatchManagerTab initialization."""

    @patch('src.gui.batch_manager_tab.ctk.CTkFrame.__init__')
    @patch('src.gui.batch_manager_tab.BatchManagerTab._create_widgets')
    @patch('src.gui.batch_manager_tab.BatchManagerTab._load_batches')
    @patch('src.gui.batch_manager_tab.BatchManagerTab._start_auto_refresh')
    def test_init_creates_widgets_and_loads_batches(
        self, mock_refresh, mock_load, mock_create, mock_frame_init,
        mock_parent, mock_api_manager, mock_main_window
    ):
        """Test that __init__ creates widgets and loads batches."""
        # Import here to avoid early initialization
        from src.gui.batch_manager_tab import BatchManagerTab

        # Act
        tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)

        # Assert
        mock_create.assert_called_once()
        mock_load.assert_called_once()
        mock_refresh.assert_called_once()


class TestBatchCardCreation:
    """Test batch card creation logic."""

    @patch('src.gui.batch_manager_tab.ctk.CTkFrame')
    @patch('src.gui.batch_manager_tab.ctk.CTkLabel')
    def test_create_batch_card_structure(self, mock_label, mock_frame, mock_parent, mock_api_manager, mock_main_window):
        """Test that _create_batch_card creates expected structure."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.batch_list = MagicMock()

        batch_data = {
            "batch_id": "test-123",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "total_files": 10,
            "completed_files": 5
        }

        # Act
        tab._create_batch_card(batch_data)

        # Assert - verify frame created
        assert mock_frame.called

    def test_create_batch_card_with_active_status(self, mock_parent, mock_api_manager, mock_main_window):
        """Test that active status shows green badge."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.batch_list = MagicMock()

        batch_data = {
            "batch_id": "test-123",
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "total_files": 10,
            "completed_files": 5
        }

        # Act & Assert (should not crash)
        with patch('src.gui.batch_manager_tab.ctk.CTkFrame'):
            with patch('src.gui.batch_manager_tab.ctk.CTkLabel'):
                tab._create_batch_card(batch_data)


class TestDetailPanelPopulation:
    """Test detail panel population."""

    @patch('src.gui.batch_manager_tab.BatchHistoryManager.load_batch_by_id')
    def test_show_batch_detail_loads_batch(self, mock_load, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _show_batch_detail loads batch by ID."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_load.return_value = sample_batch_state

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.detail_frame = MagicMock()
                    tab.detail_header = MagicMock()
                    tab.metadata_frame = MagicMock()
                    tab.settings_frame = MagicMock()
                    tab.file_list = MagicMock()
                    tab.resume_all_btn = MagicMock()
                    tab.resume_selected_btn = MagicMock()

        # Act
        tab._show_batch_detail("test-batch-123")

        # Assert
        mock_load.assert_called_once_with("test-batch-123")
        assert tab.selected_batch == sample_batch_state

    @patch('src.gui.batch_manager_tab.BatchHistoryManager.load_batch_by_id')
    @patch('src.gui.batch_manager_tab.messagebox.showerror')
    def test_show_batch_detail_handles_missing_batch(self, mock_error, mock_load, mock_parent, mock_api_manager, mock_main_window):
        """Test that _show_batch_detail handles missing batch gracefully."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_load.return_value = None

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)

        # Act
        tab._show_batch_detail("nonexistent-batch")

        # Assert
        mock_error.assert_called_once()


class TestActionButtons:
    """Test action button methods."""

    def test_on_resume_all_calls_main_window(self, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_resume_all calls MainWindow._resume_batch."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state

        # Act
        tab._on_resume_all()

        # Assert
        mock_main_window._resume_batch.assert_called_once_with(sample_batch_state, selected_files=None)

    def test_on_resume_selected_with_checked_files(self, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_resume_selected calls with selected files."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state

                    # Mock checkboxes
                    checkbox1 = MagicMock()
                    checkbox1.file_state = sample_batch_state.files[0]
                    checkbox1.checkbox_var = MagicMock()
                    checkbox1.checkbox_var.get.return_value = True

                    checkbox2 = MagicMock()
                    checkbox2.file_state = sample_batch_state.files[1]
                    checkbox2.checkbox_var = MagicMock()
                    checkbox2.checkbox_var.get.return_value = False

                    tab.file_checkboxes = [checkbox1, checkbox2]

        # Act
        tab._on_resume_selected()

        # Assert
        expected_files = ["/path/to/audio1.mp3"]
        mock_main_window._resume_batch.assert_called_once_with(sample_batch_state, selected_files=expected_files)

    @patch('src.gui.batch_manager_tab.messagebox.showwarning')
    def test_on_resume_selected_warns_when_no_selection(self, mock_warning, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_resume_selected warns when no files selected."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state

                    # Mock unchecked checkbox
                    checkbox = MagicMock()
                    checkbox.checkbox_var = MagicMock()
                    checkbox.checkbox_var.get.return_value = False
                    tab.file_checkboxes = [checkbox]

        # Act
        tab._on_resume_selected()

        # Assert
        mock_warning.assert_called_once()
        mock_main_window._resume_batch.assert_not_called()

    @patch('src.gui.batch_manager_tab.filedialog.asksaveasfilename')
    @patch('builtins.open', create=True)
    @patch('src.gui.batch_manager_tab.messagebox.showinfo')
    def test_on_export_csv_creates_file(self, mock_info, mock_open, mock_saveas, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_export_csv creates CSV file."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_saveas.return_value = "/path/to/export.csv"
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state

        # Act
        with patch('csv.writer') as mock_writer:
            tab._on_export_csv()

        # Assert
        mock_saveas.assert_called_once()
        mock_info.assert_called_once()

    @patch('src.gui.batch_manager_tab.BatchHistoryManager.delete_batch')
    @patch('src.gui.batch_manager_tab.messagebox.askyesno')
    @patch('src.gui.batch_manager_tab.messagebox.showinfo')
    def test_on_delete_calls_delete_batch(self, mock_info, mock_confirm, mock_delete, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_delete calls BatchHistoryManager.delete_batch."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_confirm.return_value = True

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state
                    tab.detail_frame = MagicMock()

        # Act
        with patch.object(tab, '_load_batches'):
            tab._on_delete()

        # Assert
        mock_delete.assert_called_once_with("test-batch-123")
        mock_info.assert_called_once()

    @patch('src.gui.batch_manager_tab.messagebox.askyesno')
    @patch('src.gui.batch_manager_tab.BatchHistoryManager.delete_batch')
    def test_on_delete_does_not_delete_when_cancelled(self, mock_delete, mock_confirm, mock_parent, mock_api_manager, mock_main_window, sample_batch_state):
        """Test that _on_delete does not delete when user cancels."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_confirm.return_value = False

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.selected_batch = sample_batch_state

        # Act
        tab._on_delete()

        # Assert
        mock_delete.assert_not_called()


class TestFilterAndRefresh:
    """Test filter and refresh functionality."""

    @patch('src.gui.batch_manager_tab.BatchHistoryManager.list_batches')
    def test_on_filter_change_reloads_batches(self, mock_list, mock_parent, mock_api_manager, mock_main_window):
        """Test that _on_filter_change reloads batch list."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_list.return_value = []

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.batch_list = MagicMock()
                    tab.filter_var = MagicMock()
                    tab.filter_var.get.return_value = "Completed"

        # Act
        tab._on_filter_change("Completed")

        # Assert
        mock_list.assert_called()

    @patch('src.gui.batch_manager_tab.BatchHistoryManager.has_active_batch')
    @patch('src.gui.batch_manager_tab.BatchHistoryManager.list_batches')
    def test_auto_refresh_reloads_when_active_batch_exists(self, mock_list, mock_has_active, mock_parent, mock_api_manager, mock_main_window):
        """Test that _auto_refresh reloads when active batch exists."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        mock_has_active.return_value = True
        mock_list.return_value = []

        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.batch_list = MagicMock()
                    tab.after = MagicMock()

        # Act
        tab._auto_refresh()

        # Assert
        mock_has_active.assert_called_once()
        # Should schedule next refresh
        tab.after.assert_called_once()


class TestBatchCardClick:
    """Test batch card click behavior."""

    @patch('src.gui.batch_manager_tab.BatchManagerTab._show_batch_detail')
    @patch('src.gui.batch_manager_tab.BatchManagerTab._load_batches')
    def test_on_batch_card_click_shows_detail(self, mock_load, mock_show, mock_parent, mock_api_manager, mock_main_window):
        """Test that clicking a batch card shows details."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)

        # Act
        tab._on_batch_card_click("test-batch-123")

        # Assert
        assert tab.selected_batch_id == "test-batch-123"
        mock_load.assert_called_once()
        mock_show.assert_called_once_with("test-batch-123")


class TestDestroy:
    """Test cleanup on destroy."""

    def test_destroy_cancels_auto_refresh(self, mock_parent, mock_api_manager, mock_main_window):
        """Test that destroy cancels auto-refresh timer."""
        from src.gui.batch_manager_tab import BatchManagerTab

        # Arrange
        with patch.object(BatchManagerTab, '_create_widgets'):
            with patch.object(BatchManagerTab, '_load_batches'):
                with patch.object(BatchManagerTab, '_start_auto_refresh'):
                    tab = BatchManagerTab(mock_parent, mock_api_manager, mock_main_window)
                    tab.auto_refresh_id = "test-id"
                    tab.after_cancel = MagicMock()

        # Mock super().destroy()
        with patch('src.gui.batch_manager_tab.ctk.CTkFrame.destroy'):
            # Act
            tab.destroy()

        # Assert
        tab.after_cancel.assert_called_once_with("test-id")
