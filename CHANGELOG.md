# Changelog

All notable changes to this project will be documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-05-14

Initial release.

### Added
- `Lightcone` strict-ordering bar feed with state-machine + token-validated contract
- `Bar` (frozen dataclass) and `BarView` (field-restricted read-only proxy)
- `LightconeConfig` with `CLOSE_ONLY`, `OHLCV`, `FULL_TAPE` presets and `custom()` builder
- Multi-stream time-priority heap for synchronized backtests across assets/timeframes
- `simulate_fill` for limit / stop / market order fills against `Bar` OHLC
- `from_ohlcv_rows` convenience constructor for Binance/HL-style row data
- Exception hierarchy: `LightconeError`, `NotConfirmed`, `BadToken`, `FieldNotDeclared`, `FeedExhausted`
- 95 tests covering state machine, field enforcement, view hardening, time ordering, no-lookahead invariant, fill simulation, performance, adversarial inputs, mutation isolation, API surface
- Documentation: `docs/CONTRACT.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/EXAMPLES.md`, `docs/LIVE.md`
