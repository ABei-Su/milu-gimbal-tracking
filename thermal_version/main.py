"""Integrated app: thermal by default, original modes via --mode."""

import sys


def main():
    if any(arg == "--mode" or arg.startswith("--mode=") for arg in sys.argv[1:]):
        from base_main import main as entry
    else:
        from thermal_main import main as entry
    entry()


if __name__ == "__main__":
    main()
