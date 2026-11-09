"""Module entrypoint for `python -m storytelling`."""

import sys

from storytelling.cli import main

if __name__ == "__main__":
    sys.exit(main())
