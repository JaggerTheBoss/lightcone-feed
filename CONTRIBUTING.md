# Contributing to lightcone-feed

Thanks for your interest in contributing. lightcone is intentionally small and focused — please read this short guide before opening a PR.

## Scope

lightcone is **the data layer**: it delivers OHLCV bars one at a time in strict timestamp order with structural lookahead prevention. It is NOT a full backtest framework, an indicator library, an order/portfolio manager, or a strategy framework.

Changes that fit the scope:

- Bug fixes
- Performance improvements that preserve the contract
- New hardening tests
- Documentation improvements
- New `LightconeConfig` presets if there's a clear use case
- A future `LiveLightcone` wrapper for WebSocket sources

Changes that probably don't fit:

- Indicator computation (RSI, MACD, etc.)
- Order/portfolio management
- Strategy templates
- Specific exchange adapters (build them in a separate package that depends on lightcone-feed)

If unsure, open an issue first.

## Development

```bash
git clone https://github.com/JaggerTheBoss/lightcone-feed
cd lightcone-feed
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest lightcone/tests/
```

All 95+ tests must pass.

## Pull requests

- Keep PRs focused — one logical change per PR.
- Add tests for any new behavior. Tests that demonstrate a bug before the fix are especially welcome.
- Follow the existing code style (no formatter config — match what's there).
- Update `CHANGELOG.md` under an "Unreleased" section.

## The contract is sacred

The package's value proposition is the no-lookahead guarantee. Changes that weaken it (e.g., allowing peek-ahead via a new method, exposing internals, relaxing field enforcement) will not be accepted. If you have a use case that seems to need lookahead, please open an issue first to discuss whether it fits in a different layer.

## License

By contributing, you agree your contributions will be licensed under Apache-2.0 (same as the project).
