"""
File browser dialog for selecting media files.
"""
import customtkinter as ctk
from typing import Optional, Callable
from pathlib import Path

from src.models.media_file import MediaFile, DirectoryNode
from src.gui.styles import FONTS, PADDING, COLORS, SPACING, DIMENSIONS, ICONS, get_file_icon, Tooltip

# Maximum total items (files + directories) to display before showing "Show all" option
MAX_TOTAL_ITEMS = 500


def _set_dialog_icon(dialog):
    """Set the dialog window icon."""
    icon_path = Path(__file__).parent.parent.parent / "assets" / "icon.ico"
    if icon_path.exists():
        try:
            dialog.after(200, lambda: dialog.iconbitmap(str(icon_path)))
        except Exception:
            pass


class FileTreeItem(ctk.CTkFrame):
    """Single item in the file tree (file or directory)."""

    def __init__(
        self,
        parent,
        item: MediaFile | DirectoryNode,
        indent_level: int = 0,
        on_select_change: Optional[Callable] = None,
        is_directory: bool = False,
        row_index: int = 0,
        expanded: bool = True,
        on_toggle_expand: Optional[Callable] = None,
    ):
        # Alternating background colors
        bg_color = COLORS["surface"] if row_index % 2 == 0 else COLORS["background"]
        super().__init__(parent, fg_color=bg_color, corner_radius=0)

        self.item = item
        self.indent_level = indent_level
        self.on_select_change = on_select_change
        self.is_directory = is_directory
        self.tooltip = None
        self.expanded = expanded
        self.on_toggle_expand = on_toggle_expand
        self.icon_label = None

        self._create_widgets()

    def _create_widgets(self):
        """Create item widgets."""
        # Use grid for better control
        self.grid_columnconfigure(2, weight=1)  # Name column expands

        col = 0

        # Indent spacer
        indent = self.indent_level * 20
        if indent > 0:
            spacer = ctk.CTkFrame(self, width=indent, height=1, fg_color="transparent")
            spacer.grid(row=0, column=col, sticky="w")
            col += 1

        # Checkbox
        self.checkbox_var = ctk.BooleanVar(value=self.item.selected)
        self.checkbox = ctk.CTkCheckBox(
            self,
            text="",
            variable=self.checkbox_var,
            width=24,
            command=self._on_checkbox_change,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            border_color=COLORS["border"],
        )
        self.checkbox.grid(row=0, column=col, sticky="w")
        col += 1

        # Icon
        if self.is_directory:
            icon = ICONS["folder"] if self.expanded else ICONS["folder_collapsed"]
        else:
            icon = get_file_icon(self.item.is_video)

        self.icon_label = ctk.CTkLabel(
            self,
            text=icon,
            font=FONTS["body"],
            width=20,
        )
        self.icon_label.grid(row=0, column=col, sticky="w", padx=(2, 4))

        # Make folder icon clickable
        if self.is_directory:
            self.icon_label.configure(cursor="hand2")
            self.icon_label.bind("<Button-1>", self._on_icon_click)

        col += 1

        # Name - truncate if too long, bold for directories
        full_name = self.item.name
        max_name_len = 45
        display_name = full_name
        if len(full_name) > max_name_len:
            display_name = full_name[:max_name_len-3] + "..."

        # Use bold font for directories
        name_font = FONTS["body_medium"] if self.is_directory else FONTS["body"]

        name_label = ctk.CTkLabel(
            self,
            text=display_name,
            font=name_font,
            anchor="w",
        )
        name_label.grid(row=0, column=col, sticky="w", padx=(PADDING["small"], PADDING["medium"]))
        col += 1

        # Add tooltip with full name if truncated
        if len(full_name) > max_name_len:
            self.tooltip = Tooltip(name_label, full_name, delay=300)

        # Size (for files only) - fixed width column on the right
        if not self.is_directory:
            size_label = ctk.CTkLabel(
                self,
                text=self.item.size_formatted,
                font=FONTS["small"],
                text_color=COLORS["text_secondary"],
                width=70,
                anchor="e",
            )
            size_label.grid(row=0, column=10, sticky="e", padx=(0, PADDING["small"]))

    def _on_checkbox_change(self):
        """Handle checkbox state change."""
        selected = self.checkbox_var.get()
        self.item.selected = selected

        # If this is a directory, propagate selection to all children
        if self.is_directory:
            self.item.select_children(selected)

        if self.on_select_change:
            self.on_select_change()

    def update_selection(self, selected: bool):
        """Update the selection state."""
        self.checkbox_var.set(selected)
        self.item.selected = selected

    def _on_icon_click(self, event):
        """Handle click on folder icon."""
        if self.is_directory and self.on_toggle_expand:
            self.on_toggle_expand(self)

    def set_expanded(self, expanded: bool):
        """Update the expanded state and icon."""
        self.expanded = expanded
        if self.icon_label and self.is_directory:
            icon = ICONS["folder"] if expanded else ICONS["folder_collapsed"]
            self.icon_label.configure(text=icon)


class FileBrowserDialog(ctk.CTkToplevel):
    """Dialog for browsing and selecting media files."""

    def __init__(
        self,
        parent,
        root_node: DirectoryNode,
        on_confirm: Optional[Callable[[list[MediaFile]], None]] = None,
    ):
        super().__init__(parent)

        self.root_node = root_node
        self.on_confirm = on_confirm
        self.file_items: list[FileTreeItem] = []
        self.expanded_state: dict[str, bool] = {}  # path -> expanded
        self.node_items: dict[str, FileTreeItem] = {}  # path -> directory FileTreeItem
        self.node_children: dict[str, list[FileTreeItem]] = {}  # path -> direct children items
        self.all_expanded = True  # Track global expand state for toggle button
        self.show_all_mode = False  # Display all files (no limit)
        self._stats_update_id = None  # For debouncing stats updates

        # Window configuration
        self.title("Select Files to Transcribe")
        self.geometry("700x550")
        self.resizable(True, True)
        self.minsize(550, 400)
        self.transient(parent)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 700) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 550) // 2
        x = max(0, x)
        y = max(0, y)
        self.geometry(f"+{x}+{y}")

        self._create_widgets()
        _set_dialog_icon(self)

        # Show loading indicator and load files after window is displayed
        self._show_loading()
        self.after(50, self._refresh_display)

    def _create_widgets(self):
        """Create dialog widgets."""
        # Main frame
        main_frame = ctk.CTkFrame(self, fg_color=COLORS["surface"])
        main_frame.pack(fill="both", expand=True)

        # Content with padding
        content_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(1, weight=1)

        # Header with select/deselect buttons
        header_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, SPACING["sm"]))
        header_frame.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(
            header_frame,
            text=f"Files in: {self.root_node.name}",
            font=FONTS["heading"],
        )
        header_label.grid(row=0, column=0, sticky="w")

        btn_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        self.toggle_expand_btn = ctk.CTkButton(
            btn_frame,
            text="Collapse All",
            width=95,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._toggle_all_directories,
        )
        self.toggle_expand_btn.pack(side="left", padx=(0, SPACING["xs"]))

        select_all_btn = ctk.CTkButton(
            btn_frame,
            text="Select All",
            width=85,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._select_all,
        )
        select_all_btn.pack(side="left", padx=(0, SPACING["xs"]))

        deselect_all_btn = ctk.CTkButton(
            btn_frame,
            text="Clear All",
            width=80,
            height=DIMENSIONS["button_height_sm"],
            font=FONTS["small"],
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text"],
            corner_radius=DIMENSIONS["corner_radius"],
            border_width=1,
            border_color=COLORS["border"],
            command=self._deselect_all,
        )
        deselect_all_btn.pack(side="left")

        # Scrollable file list
        self.file_list_frame = ctk.CTkScrollableFrame(
            content_frame,
            fg_color=COLORS["background"],
            corner_radius=8,
        )
        self.file_list_frame.grid(row=1, column=0, sticky="nsew")

        # Stats label
        self.stats_label = ctk.CTkLabel(
            content_frame,
            text="",
            font=FONTS["small"],
            text_color=COLORS["text_secondary"],
        )
        self.stats_label.grid(row=2, column=0, sticky="w", pady=(SPACING["sm"], 0))

        # Buttons frame
        buttons_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        buttons_frame.grid(row=3, column=0, sticky="ew", pady=(SPACING["lg"], 0))

        cancel_btn = ctk.CTkButton(
            buttons_frame,
            text="Cancel",
            width=100,
            fg_color=COLORS["surface_elevated"],
            hover_color=COLORS["border"],
            text_color=COLORS["text_secondary"],
            border_width=1,
            border_color=COLORS["border"],
            command=self.destroy,
        )
        cancel_btn.pack(side="right")

        confirm_btn = ctk.CTkButton(
            buttons_frame,
            text="Confirm Selection",
            width=140,
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._on_confirm,
        )
        confirm_btn.pack(side="right", padx=(0, SPACING["sm"]))

    def _show_loading(self):
        """Show loading indicator while files are being loaded."""
        self.loading_label = ctk.CTkLabel(
            self.file_list_frame,
            text="Loading files...",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        )
        self.loading_label.pack(pady=50)

    def _show_hidden_files_banner(self, hidden_count: int):
        """Show banner when files are hidden due to display limit."""
        banner_frame = ctk.CTkFrame(
            self.file_list_frame,
            fg_color=COLORS["surface_elevated"],
            corner_radius=8,
        )
        banner_frame.pack(fill="x", pady=SPACING["md"], padx=SPACING["sm"])

        info_label = ctk.CTkLabel(
            banner_frame,
            text=f"{hidden_count} more files not displayed (use 'Select All' to include them)",
            font=FONTS["body"],
            text_color=COLORS["text_secondary"],
        )
        info_label.pack(side="left", padx=SPACING["md"], pady=SPACING["sm"])

        show_all_btn = ctk.CTkButton(
            banner_frame,
            text="Show all (may be slow)",
            width=160,
            height=28,
            font=FONTS["body"],
            fg_color=COLORS["primary"],
            hover_color=COLORS["primary_hover"],
            text_color="#FFFFFF",
            command=self._show_all_files,
        )
        show_all_btn.pack(side="right", padx=SPACING["md"], pady=SPACING["sm"])

    def _refresh_display(self):
        """Refresh the file list display."""
        # Remove loading label if exists
        if hasattr(self, 'loading_label') and self.loading_label:
            self.loading_label.destroy()
            self.loading_label = None

        # Clear existing items
        for item in self.file_items:
            item.destroy()
        self.file_items.clear()
        self.node_items.clear()
        self.node_children.clear()

        if not self.root_node or self.root_node.total_files == 0:
            empty_label = ctk.CTkLabel(
                self.file_list_frame,
                text="No audio/video files found in this directory",
                font=FONTS["body"],
                text_color=COLORS["text_secondary"],
            )
            empty_label.pack(pady=SPACING["2xl"])
            self._update_stats()
            return

        # Build tree view - directories always shown, files limited
        self._row_counter = 0
        self._files_counter = 0  # Separate counter for files only
        self._add_node_to_display(self.root_node, 0)

        # Hide collapsed directories' children (skip root - its children always visible)
        root_path = self.root_node.name
        for node_path, is_expanded in self.expanded_state.items():
            if not is_expanded and node_path != root_path:
                self._set_children_visible(node_path, False)

        # Show "hidden files" banner if file limit was reached
        total_files = self.root_node.total_files
        if not self.show_all_mode and total_files > self._files_counter:
            hidden_count = total_files - self._files_counter
            self._show_hidden_files_banner(hidden_count)

        self._update_stats()

    def _add_node_to_display(self, node: DirectoryNode, indent: int, parent_path: str = ""):
        """Recursively add directory node to display. Directories always shown, files limited."""
        node_path = f"{parent_path}/{node.name}" if parent_path else node.name

        # Initialize expanded state if not set
        if node_path not in self.expanded_state:
            self.expanded_state[node_path] = True

        is_expanded = self.expanded_state[node_path]

        # Add directory item (except for root) - ALWAYS show directories
        if indent > 0:
            dir_item = FileTreeItem(
                self.file_list_frame,
                node,
                indent_level=indent - 1,
                on_select_change=self._on_item_select_change,
                is_directory=True,
                row_index=self._row_counter,
                expanded=is_expanded,
                on_toggle_expand=lambda item, p=node_path: self._toggle_directory(p),
            )
            dir_item.pack(fill="x", pady=0)
            self.file_items.append(dir_item)
            self.node_items[node_path] = dir_item
            self._row_counter += 1

        # Initialize children list for this node
        self.node_children[node_path] = []

        # Add files (respecting global limit - only for FILES, not directories)
        for media_file in node.files:
            if not self.show_all_mode and self._files_counter >= MAX_TOTAL_ITEMS:
                break

            file_item = FileTreeItem(
                self.file_list_frame,
                media_file,
                indent_level=indent,
                on_select_change=self._on_item_select_change,
                is_directory=False,
                row_index=self._row_counter,
            )
            file_item.pack(fill="x", pady=0)
            self.file_items.append(file_item)
            self.node_children[node_path].append(file_item)
            self._row_counter += 1
            self._files_counter += 1

        # Add subdirectories - ALWAYS process all directories
        for subdir in node.subdirs:
            subdir_path = f"{node_path}/{subdir.name}"
            self._add_node_to_display(subdir, indent + 1, node_path)
            # Add the subdir item to this node's children
            if subdir_path in self.node_items:
                self.node_children[node_path].append(self.node_items[subdir_path])

    def _toggle_directory(self, node_path: str):
        """Toggle expand/collapse state for a directory."""
        # Toggle state
        self.expanded_state[node_path] = not self.expanded_state.get(node_path, True)
        is_expanded = self.expanded_state[node_path]

        # Update icon on directory item
        if node_path in self.node_items:
            self.node_items[node_path].set_expanded(is_expanded)

        # Show/hide children
        self._set_children_visible(node_path, is_expanded)

    def _set_children_visible(self, node_path: str, visible: bool):
        """Show or hide all children of a directory."""
        if node_path not in self.node_children:
            return

        for child in self.node_children[node_path]:
            if visible:
                child.pack(fill="x", pady=0)
            else:
                child.pack_forget()

            # If child is a directory, also handle its children
            if child.is_directory:
                child_path = f"{node_path}/{child.item.name}"
                # If hiding parent, hide all descendants
                # If showing parent, only show if child is expanded
                if not visible:
                    self._set_children_visible(child_path, False)
                elif self.expanded_state.get(child_path, True):
                    self._set_children_visible(child_path, True)

    def _toggle_all_directories(self):
        """Toggle expand/collapse state for all directories."""
        self.all_expanded = not self.all_expanded

        # Set all directories to the new state
        for path in self.expanded_state:
            self.expanded_state[path] = self.all_expanded

        # Update button text
        btn_text = "Collapse All" if self.all_expanded else "Expand All"
        self.toggle_expand_btn.configure(text=btn_text)

        # Rebuild display to maintain correct order
        # (pack_forget/pack doesn't preserve order, so we need full refresh for bulk operation)
        self._refresh_display()

    def _show_all_files(self):
        """Show all files (remove display limit)."""
        self.show_all_mode = True
        self._refresh_display()

    def _on_item_select_change(self):
        """Handle item selection change with debounce."""
        self._refresh_all_checkboxes()

        # Debounce stats update for better performance
        if self._stats_update_id:
            self.after_cancel(self._stats_update_id)
        self._stats_update_id = self.after(100, self._update_stats)

    def _refresh_all_checkboxes(self):
        """Refresh all checkbox states to match model."""
        for item in self.file_items:
            item.checkbox_var.set(item.item.selected)

    def _update_stats(self):
        """Update the stats label."""
        if not self.root_node:
            self.stats_label.configure(text="")
            return

        all_files = self.root_node.get_all_files()
        selected_files = self.root_node.get_selected_files()

        total_count = len(all_files)
        selected_count = len(selected_files)
        selected_size = sum(f.size_bytes for f in selected_files)

        size_str = self._format_size(selected_size)
        self.stats_label.configure(
            text=f"Selected: {selected_count} of {total_count} files ({size_str})"
        )

    def _format_size(self, size_bytes: int) -> str:
        """Format size in bytes to human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _select_all(self):
        """Select all files."""
        if self.root_node:
            self.root_node.select_all(True)
            self._refresh_all_checkboxes()
            self._update_stats()

    def _deselect_all(self):
        """Deselect all files."""
        if self.root_node:
            self.root_node.select_all(False)
            self._refresh_all_checkboxes()
            self._update_stats()

    def _on_confirm(self):
        """Handle confirm button click."""
        if self.on_confirm and self.root_node:
            selected_files = self.root_node.get_selected_files()
            self.on_confirm(selected_files)
        self.destroy()
