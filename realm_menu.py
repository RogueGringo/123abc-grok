#!/usr/bin/env python3
"""Navigator entrypoint: Job OS smoke/wizard, catalog, dynamical topology, docs.

Usage:
  python realm_menu.py
  echo 0 | python realm_menu.py   # exit immediately

Pin is never editable. Measure/control paths do not rewrite soft_T / mono ε.
"""

from __future__ import annotations

from realm.menu.app import main

if __name__ == "__main__":
    raise SystemExit(main())
