"""
Transkryptor - Audio/Video Transcription Application

Main entry point for the application.
"""
import sys
import os

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    """Main entry point."""
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
