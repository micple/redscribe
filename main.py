"""
Transkryptor - Audio/Video Transcription Application

Main entry point for the application.
"""
import sys
import os

# Fix Tcl/Tk path issue on Windows
if sys.platform == "win32":
    python_dir = os.path.dirname(sys.executable)
    # Handle both venv and direct Python installation
    if "venv" in python_dir.lower() or "scripts" in python_dir.lower():
        # venv - go up to find the base Python installation
        import struct
        # Find Python installation from registry or common paths
        possible_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", f"Python{sys.version_info.major}{sys.version_info.minor}"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Python", f"Python{sys.version_info.major}{sys.version_info.minor}"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Python", f"Python{sys.version_info.major}{sys.version_info.minor}"),
        ]
        for path in possible_paths:
            tcl_path = os.path.join(path, "tcl", "tcl8.6")
            tk_path = os.path.join(path, "tcl", "tk8.6")
            if os.path.exists(tcl_path) and os.path.exists(tk_path):
                os.environ["TCL_LIBRARY"] = tcl_path
                os.environ["TK_LIBRARY"] = tk_path
                break
    else:
        # Direct Python installation
        tcl_path = os.path.join(python_dir, "tcl", "tcl8.6")
        tk_path = os.path.join(python_dir, "tcl", "tk8.6")
        if os.path.exists(tcl_path) and os.path.exists(tk_path):
            os.environ["TCL_LIBRARY"] = tcl_path
            os.environ["TK_LIBRARY"] = tk_path

# Add FFmpeg to PATH if installed via winget
if sys.platform == "win32":
    import glob
    localappdata = os.environ.get("LOCALAPPDATA", "")
    ffmpeg_patterns = [
        os.path.join(localappdata, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "ffmpeg-*", "bin"),
        os.path.join(localappdata, "Microsoft", "WinGet", "Links"),
        r"C:\ffmpeg\bin",
        r"C:\Program Files\ffmpeg\bin",
    ]
    for pattern in ffmpeg_patterns:
        matches = glob.glob(pattern)
        for match in matches:
            if os.path.isdir(match) and match not in os.environ.get("PATH", ""):
                os.environ["PATH"] = match + os.pathsep + os.environ.get("PATH", "")
                break

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    """Main entry point."""
    # Configure logging
    import logging
    from config import LOGS_DIR

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(LOGS_DIR / 'redscribe.log'),
            logging.StreamHandler(),  # Console output
        ]
    )

    try:
        from src.gui.main_window import MainWindow

        app = MainWindow()
        app.mainloop()

    except ImportError as e:
        # Handle missing dependencies
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()

        missing_module = str(e).split("'")[-2] if "'" in str(e) else str(e)
        messagebox.showerror(
            "Missing Dependencies",
            f"Cannot start the application.\n\n"
            f"Missing module: {missing_module}\n\n"
            f"Install required packages:\n"
            f"pip install -r requirements.txt"
        )
        sys.exit(1)

    except Exception as e:
        # Handle other errors
        import tkinter as tk
        from tkinter import messagebox
        import traceback

        root = tk.Tk()
        root.withdraw()

        error_details = traceback.format_exc()
        messagebox.showerror(
            "Application Error",
            f"An unexpected error occurred:\n\n{str(e)}\n\n"
            f"Details:\n{error_details[:500]}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
