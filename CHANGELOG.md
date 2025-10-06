# Changelog

## [1.1.3](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.2...v1.1.3) (2025-10-06)


### Bug Fixes

* Add queue/exchange declaration in RabbitMQConsumer ([e99abf2](https://github.com/TeamPew/pewstats-collectors/commit/e99abf2a1e3b08221376e1ac0dc5bf31385ed9c6))
* Implement even pacing for API requests ([75a57a7](https://github.com/TeamPew/pewstats-collectors/commit/75a57a75c9c2ea1625d3b2e88c8245a4dd2c8563))
* update unit tests to match new API key pacing behavior ([0d4e7ca](https://github.com/TeamPew/pewstats-collectors/commit/0d4e7ca9976a5644a752b8e95c97cd185089fdf6))

## [1.1.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.1...v1.1.2) (2025-10-06)


### Bug Fixes

* Correct RabbitMQConsumer usage in all workers ([9d14336](https://github.com/TeamPew/pewstats-collectors/commit/9d14336e55549a895b3c78e77f89a26e89d6dfd1))
* Worker crashes and API rate limiting ([c30b232](https://github.com/TeamPew/pewstats-collectors/commit/c30b2325b656cc57ba4b3b600e73ac6c6c54f0ec))

## [1.1.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.0...v1.1.1) (2025-10-06)


### Bug Fixes

* Re-apply RabbitMQ parameter fixes after merge ([9f61b6c](https://github.com/TeamPew/pewstats-collectors/commit/9f61b6cbe9e7a1edaecd84f2c1496ca9ffd19bf8))
* Re-apply RabbitMQ parameter fixes after merge ([cc3e6d8](https://github.com/TeamPew/pewstats-collectors/commit/cc3e6d8dd09f65aa6a1cb7212e067fd127b0e9d8))

## [1.1.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.0.4...v1.1.0) (2025-10-06)


### Features

* Add mandatory ruff format workflow rule ([4e690d9](https://github.com/TeamPew/pewstats-collectors/commit/4e690d983d6bb46e6ec6dbc6d0f2581fac90e57d))
* Add mandatory ruff format workflow rule ([9e5fd8d](https://github.com/TeamPew/pewstats-collectors/commit/9e5fd8d0543d8224e3b10ede44c9ba15b44d62cd))

## [1.0.4](https://github.com/TeamPew/pewstats-collectors/compare/v1.0.3...v1.0.4) (2025-10-05)


### Bug Fixes

* Correct MatchSummaryWorker initialization in __main__ ([ecade1f](https://github.com/TeamPew/pewstats-collectors/commit/ecade1f2c3591d5d879709d91c980dc7cd2da792))
* Implement proactive rate limit pacing instead of reactive waiting ([34093c0](https://github.com/TeamPew/pewstats-collectors/commit/34093c0bd59bb6d8e86def56a5130be3a279328a))

## [1.0.3](https://github.com/TeamPew/pewstats-collectors/compare/v1.0.2...v1.0.3) (2025-10-05)


### Bug Fixes

* Add __main__ blocks to workers and continuous loop to match_disc… ([3f04fde](https://github.com/TeamPew/pewstats-collectors/commit/3f04fde562ced77b69cedd44eb94f4ff8bbf6fa4))
* Add __main__ blocks to workers and continuous loop to match_discovery ([b5bd307](https://github.com/TeamPew/pewstats-collectors/commit/b5bd3074d63117a280ccf8ae4fdfd9673947be3d))

## [1.0.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.0.1...v1.0.2) (2025-10-05)


### Bug Fixes

* Use PUBG_API_KEYS and format code ([a703a42](https://github.com/TeamPew/pewstats-collectors/commit/a703a4295eb8c4856f79631be2795e5372a9db76))
* Use PUBG_API_KEYS and format code ([d8750e8](https://github.com/TeamPew/pewstats-collectors/commit/d8750e8257ed228918b34a462be8cb9822f6d5a2))

## [1.0.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.0.0...v1.0.1) (2025-10-05)


### Bug Fixes

* Update compose.yaml for production deployment ([1104a3f](https://github.com/TeamPew/pewstats-collectors/commit/1104a3f8cb6ac526c8374e7c93b9d3fd2c9a8d9f))
* Update compose.yaml for production deployment ([440c8b6](https://github.com/TeamPew/pewstats-collectors/commit/440c8b6721b7c6e0cfb8a312aa0e8bc0e31e4173))

## 1.0.0 (2025-10-05)


### ⚠ BREAKING CHANGES

* Complete rewrite of CI/CD workflows

### Features

* Add deployment configuration and documentation ([796bdd0](https://github.com/TeamPew/pewstats-collectors/commit/796bdd0a76fcfa367cb3b268df39b2328885800d))
* Add Docker Compose configuration for pewstats-collectors services ([3c51c3a](https://github.com/TeamPew/pewstats-collectors/commit/3c51c3a2fe9d078b6a5d4e2d363be782631eb6aa))
* Add production build workflow and fix linting issues ([2cbfb3b](https://github.com/TeamPew/pewstats-collectors/commit/2cbfb3b49710b9eb88bf1aef85e11a63c6860e0a))
* Complete Python implementation of pewstats-collectors service ([cc8658e](https://github.com/TeamPew/pewstats-collectors/commit/cc8658e7b03ec76fc46fce3bbe254b74837ec0b7))
* Implement proper CI/CD pipeline with release-please ([ba30f71](https://github.com/TeamPew/pewstats-collectors/commit/ba30f71a8bdf9d8201cf0e391604682b4e782885))


### Bug Fixes

* Re-add Path import to rabbitmq_publisher ([af7ede9](https://github.com/TeamPew/pewstats-collectors/commit/af7ede9ac1a750eb22e403d09ef9ce54f2889e28))
* Remove unused imports from test file ([bd441eb](https://github.com/TeamPew/pewstats-collectors/commit/bd441ebb0357fe9e1d17397b5733283aeea36145))
* Remove unused imports to fix linting errors ([d417081](https://github.com/TeamPew/pewstats-collectors/commit/d417081f2ad25f9ab1b4b00c2331e8495114600b))
* Resolve all linting errors (bare except, unused variables) ([14a12fc](https://github.com/TeamPew/pewstats-collectors/commit/14a12fc8971551a68ea9c9bcde9b8803e04d8bca))
