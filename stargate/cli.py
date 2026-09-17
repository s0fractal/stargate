"""Both console entry points use this CLI."""
import argparse

from . import CONTRACT_STATUS, KELVIN, __version__


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="sg",
        description="Stargate — Python successor to Sigma-Glyph and Warrant. "
                    "Bootstrap only; evaluation and record verification are not implemented.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"Stargate build {__version__} · {KELVIN}K ({CONTRACT_STATUS})",
    )
    parser.parse_args(argv)
    parser.print_help()
    return 0
