"""Entry point so ``python3 -m evidence.gateway --config gw.json`` works."""

from evidence.gateway.proxy import main

if __name__ == "__main__":
    raise SystemExit(main())
