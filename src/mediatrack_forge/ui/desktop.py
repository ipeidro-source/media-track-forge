"""Desktop entry point; GUI dependencies are imported only when launching it."""

import sys


def main() -> int:
    try:
        from mediatrack_forge.ui.window import DesktopWindow

        window = DesktopWindow()
        window.root.mainloop()
        return 0
    except ImportError:
        print(
            "Desktop dependencies are unavailable. Install the project requirements.",
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(
            "The desktop could not start. Check the native Tk installation and display.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
