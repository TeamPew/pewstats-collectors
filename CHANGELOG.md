# Changelog

## [1.20.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.19.0...v1.20.0) (2025-10-18)


### Features

* add parallel processing support to run_backfill.sh ([ba6869c](https://github.com/TeamPew/pewstats-collectors/commit/ba6869cdc45d09d4d8399f2595cc7a12efddb703))
* add parallel processing support to run_backfill.sh ([b237729](https://github.com/TeamPew/pewstats-collectors/commit/b237729eae91a80c7d2ae4290a60a75060cc9c87))

## [1.19.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.18.1...v1.19.0) (2025-10-18)


### Features

* add parallel processing to backfill orchestrator ([952c6eb](https://github.com/TeamPew/pewstats-collectors/commit/952c6ebd40a23c130c2c9c725409ffa6b427377f))


### Bug Fixes

* remove unused functools.partial import ([3a5ca4f](https://github.com/TeamPew/pewstats-collectors/commit/3a5ca4f3a4c9aa8ab0f85e3b3579541bca44703f))

## [1.18.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.18.0...v1.18.1) (2025-10-18)


### Bug Fixes

* exclude novelty throwables (snowballs, apples) from throwables_used ([b228455](https://github.com/TeamPew/pewstats-collectors/commit/b228455acd64945b94098aee99e62658f6cae1b0))
* exclude novelty throwables (snowballs, apples) from throwables_used ([c050056](https://github.com/TeamPew/pewstats-collectors/commit/c050056c0d4fbbd7da271378f7a82390625cfeb9))

## [1.18.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.17.3...v1.18.0) (2025-10-18)


### Features

* improve time_outside_zone calculation using blue zone damage ticks ([17f921f](https://github.com/TeamPew/pewstats-collectors/commit/17f921fe0e0697b452af7c68948196670c366897))
* improve time_outside_zone calculation using blue zone damage ticks ([f6219f1](https://github.com/TeamPew/pewstats-collectors/commit/f6219f1528b30aea5ea82a54faec4a81867c3933))

## [1.17.3](https://github.com/TeamPew/pewstats-collectors/compare/v1.17.2...v1.17.3) (2025-10-18)


### Bug Fixes

* exclude flashbangs from smokes_thrown tracking ([e300e7f](https://github.com/TeamPew/pewstats-collectors/commit/e300e7f4d6c64eeb0c15871291360238693b4b9a))
* exclude flashbangs from smokes_thrown tracking ([871b6c0](https://github.com/TeamPew/pewstats-collectors/commit/871b6c03e81da5c202591c2fa06815d0f28b9c74))

## [1.17.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.17.1...v1.17.2) (2025-10-18)


### Bug Fixes

* correct killsteal detection logic ([26e97b9](https://github.com/TeamPew/pewstats-collectors/commit/26e97b9563aee5830edf84fe98cd0632a3163b71))
* track throwable usage from damage events ([981ee15](https://github.com/TeamPew/pewstats-collectors/commit/981ee15e74be7a751bdba618f74851db7262e8e3))
* track throwables from LogPlayerAttack events ([d5eea22](https://github.com/TeamPew/pewstats-collectors/commit/d5eea22731f1468cd8be3f07223cdc0a84941577))

## [1.17.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.17.0...v1.17.1) (2025-10-17)


### Bug Fixes

* rewrite circle tracking to use LogPlayerPosition events ([d40d152](https://github.com/TeamPew/pewstats-collectors/commit/d40d15295a00d42cfcdf99796693dd6f9ed4518a))
* rewrite circle tracking to use LogPlayerPosition events ([472dd98](https://github.com/TeamPew/pewstats-collectors/commit/472dd98df9923dafc592558f2abd619ca68ec427))

## [1.17.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.16.2...v1.17.0) (2025-10-17)


### Features

* add parallel processing for telemetry worker ([b671d5a](https://github.com/TeamPew/pewstats-collectors/commit/b671d5acd94df00d882195f6117add636f727ed6))

## [1.16.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.16.1...v1.16.2) (2025-10-17)


### Bug Fixes

* correct circle positions table column names ([5e60b83](https://github.com/TeamPew/pewstats-collectors/commit/5e60b83940609d3100e6fac3ce37bed8deba9cd4))
* correct circle positions table column names ([7fc7959](https://github.com/TeamPew/pewstats-collectors/commit/7fc7959e23899e661f2afecf9169c7455d26eb31))

## [1.16.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.16.0...v1.16.1) (2025-10-17)


### Bug Fixes

* remove unused variable in weapon_distribution extractor ([b23861e](https://github.com/TeamPew/pewstats-collectors/commit/b23861eb7df98de7c1d76086deb8cfe76ba75964))

## [1.16.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.15.1...v1.16.0) (2025-10-17)


### Features

* add tournaments table and tournament leaderboard API design ([7fec510](https://github.com/TeamPew/pewstats-collectors/commit/7fec5106fa26d30a676b6cf777870212ef3c9617))


### Bug Fixes

* validate division/group before assigning matches to rounds ([9c7b9d1](https://github.com/TeamPew/pewstats-collectors/commit/9c7b9d1bca65f2e46f258276c9c6fad4c06958b4))
* validate division/group before assigning matches to rounds ([733edb2](https://github.com/TeamPew/pewstats-collectors/commit/733edb2b817a11c125bcac1890a664ae2d8b0382))

## [1.15.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.15.0...v1.15.1) (2025-10-14)


### Bug Fixes

* add timezone support for tournament schedule and split API keys ([9425e93](https://github.com/TeamPew/pewstats-collectors/commit/9425e93cbdcd3bf27864006a6dba2d5fa5374dc3))

## [1.15.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.14.0...v1.15.0) (2025-10-14)


### Features

* add tournament rounds, seasons, and auto-population ([fcd2bc8](https://github.com/TeamPew/pewstats-collectors/commit/fcd2bc87e23aceaf95fb89c2cac82474ea5c5a55))
* add tournament rounds, seasons, and auto-population ([c2372d6](https://github.com/TeamPew/pewstats-collectors/commit/c2372d60c3158ded0025c28536010999bb555332))

## [1.14.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.13.0...v1.14.0) (2025-10-14)


### Features

* add tournament match discovery system ([8775f83](https://github.com/TeamPew/pewstats-collectors/commit/8775f832d3c98357d0dbb55ebfcf8a81f6e9a250))

## [1.13.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.12.0...v1.13.0) (2025-10-13)


### Features

* add RANKED_API_KEY environment variable to ranked-stats-collector ([7398426](https://github.com/TeamPew/pewstats-collectors/commit/7398426b131a97da010cf7f08deeb39446670414))
* add RANKED_API_KEY environment variable to ranked-stats-collector ([fb4e2bf](https://github.com/TeamPew/pewstats-collectors/commit/fb4e2bf2fdfc15a9dbad72b82edff316d065d575))

## [1.12.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.11.0...v1.12.0) (2025-10-13)


### Features

* rewrite ranked stats collector to use correct API endpoint ([a13dedd](https://github.com/TeamPew/pewstats-collectors/commit/a13dedde10050fefc0e0b25c19171c0845154b9c))


### Bug Fixes

* map steam platform to pc for season lookup ([210665b](https://github.com/TeamPew/pewstats-collectors/commit/210665bc14f32a4b30e3f26885dcb84068541e28))
* map steam platform to pc for season lookup ([9f37389](https://github.com/TeamPew/pewstats-collectors/commit/9f37389be690d98b12fb99c09c0ce8920347c6b4))
* remove undefined game_mode variable from debug log ([7daaf66](https://github.com/TeamPew/pewstats-collectors/commit/7daaf66f8a6bd83a4c4224e669e8af423a14abe9))

## [1.11.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.10.3...v1.11.0) (2025-10-12)


### Features

* filter player_damage_events to tracked players only ([aedeaa0](https://github.com/TeamPew/pewstats-collectors/commit/aedeaa0b3f971fa2562197ae9cf36b047cbb57f1))

## [1.10.3](https://github.com/TeamPew/pewstats-collectors/compare/v1.10.2...v1.10.3) (2025-10-12)


### Bug Fixes

* use DatabaseManager.execute_query instead of non-existent fetch_… ([502c868](https://github.com/TeamPew/pewstats-collectors/commit/502c8686f3d99af7587d1a23e94799b89de1bde1))
* use DatabaseManager.execute_query instead of non-existent fetch_one/fetch_all ([5566b6a](https://github.com/TeamPew/pewstats-collectors/commit/5566b6a97d003c02b46e3e1dea1325b0717bc792))

## [1.10.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.10.1...v1.10.2) (2025-10-12)


### Bug Fixes

* correct DatabaseManager parameter from 'database' to 'dbname' ([cdb79c2](https://github.com/TeamPew/pewstats-collectors/commit/cdb79c2c8f6248eae1222d4258ab1100eb703004))
* correct DatabaseManager parameter from 'database' to 'dbname' ([a8a0a6c](https://github.com/TeamPew/pewstats-collectors/commit/a8a0a6ced043dacb75f3b0f28cf3b1f4e09eac5b))

## [1.10.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.10.0...v1.10.1) (2025-10-12)


### Bug Fixes

* use prometheus_client directly instead of non-existent metric wr… ([2af111a](https://github.com/TeamPew/pewstats-collectors/commit/2af111a07fa86abac698c0183a7557e474522b14))
* use prometheus_client directly instead of non-existent metric wrappers ([253549f](https://github.com/TeamPew/pewstats-collectors/commit/253549fa00e010952a004a84113071bf33040b28))

## [1.10.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.9.0...v1.10.0) (2025-10-12)


### Features

* add ranked stats collector service ([f6a38c1](https://github.com/TeamPew/pewstats-collectors/commit/f6a38c11b590f2d9e420b1d0967dcdad32626a9f))


### Bug Fixes

* remove unused Set import from ranked_stats_collector ([03b44da](https://github.com/TeamPew/pewstats-collectors/commit/03b44da7d071677934ac42a44b385600b19138a7))

## [1.9.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.8.0...v1.9.0) (2025-10-12)


### Features

* add fight tracking v2 implementation with multi-core backfill ([41d5827](https://github.com/TeamPew/pewstats-collectors/commit/41d58279292d567d049edba7ab3232458525653a))


### Bug Fixes

* properly associate fight_participants with fight_id ([a069e42](https://github.com/TeamPew/pewstats-collectors/commit/a069e425059cfcbf08e663f9d6cda85d4544f6d9))
* resolve test failures and formatting issues ([c775fe1](https://github.com/TeamPew/pewstats-collectors/commit/c775fe11cda4d81c71a2d6f548c30dc931cd3296))


### Performance Improvements

* optimize memory usage in workers and database connections ([921a38d](https://github.com/TeamPew/pewstats-collectors/commit/921a38dc74c03a7a7396910a6a1ae445963098c6))

## [1.8.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.7.1...v1.8.0) (2025-10-10)


### Features

* add finishing metrics processing and backfill system ([7d22c15](https://github.com/TeamPew/pewstats-collectors/commit/7d22c1565b727b880cfa8332c3bb4cf42d461a37))

## [1.7.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.7.0...v1.7.1) (2025-10-10)


### Bug Fixes

* use correct column name stats_updated_at for player_damage_stats ([d78cb51](https://github.com/TeamPew/pewstats-collectors/commit/d78cb51af0d2856cde40267639cfb7a4b150f960))
* use correct column name stats_updated_at for player_damage_stats ([08c343e](https://github.com/TeamPew/pewstats-collectors/commit/08c343e2f5e865a671f5f83ebed8097f2d2e52a7))

## [1.7.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.6.2...v1.7.0) (2025-10-10)


### Features

* add stats aggregation worker for radar chart data ([46f3a7b](https://github.com/TeamPew/pewstats-collectors/commit/46f3a7b8b0fd9dd5252fc6dd89824edfa1548b6a))


### Bug Fixes

* include Unknown weapon kills in stats aggregation ([734c049](https://github.com/TeamPew/pewstats-collectors/commit/734c049a7cca36e24f99bb8297694b4cc935ee5f))

## [1.6.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.6.1...v1.6.2) (2025-10-09)


### Bug Fixes

* remove host port mappings for metrics to support multiple replicas ([ecac851](https://github.com/TeamPew/pewstats-collectors/commit/ecac8515b2ef1e82cb6e20c047034d4ba3b57491))
* remove host port mappings for metrics to support multiple replicas ([8fe359b](https://github.com/TeamPew/pewstats-collectors/commit/8fe359bf6ecc264e6faaa375517f0d84c1683db4))

## [1.6.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.6.0...v1.6.1) (2025-10-09)


### Bug Fixes

* move TELEMETRY_FILE_READ_DURATION to metrics.py ([e726e9c](https://github.com/TeamPew/pewstats-collectors/commit/e726e9c33cb2d6c3c647587de9a039e5b5d658bd))
* move TELEMETRY_FILE_READ_DURATION to metrics.py ([903f409](https://github.com/TeamPew/pewstats-collectors/commit/903f409eec24212622ba26e01318c553a98446e6))

## [1.6.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.5.0...v1.6.0) (2025-10-09)


### Features

* add Prometheus metrics instrumentation to collectors ([d22c18e](https://github.com/TeamPew/pewstats-collectors/commit/d22c18e7bbeedbab2c8724b155b15cd9c9fea3b8))


### Bug Fixes

* add prometheus-client to pyproject.toml dependencies ([3f13542](https://github.com/TeamPew/pewstats-collectors/commit/3f13542174a28fa540106e1ec644980e2eb80693))
* deduplicate Prometheus metrics definitions ([db3010f](https://github.com/TeamPew/pewstats-collectors/commit/db3010f71ddad19ad38019778db55a82667432b4))
* remove unused imports and variables ([7853676](https://github.com/TeamPew/pewstats-collectors/commit/785367632b0ad5262a068cb3d904671bfd6cc102))

## [1.5.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.6...v1.5.0) (2025-10-09)


### Features

* add tournament match discovery system ([980db43](https://github.com/TeamPew/pewstats-collectors/commit/980db43c1245bc32c71e2dc0440b5dac3e083606))


### Bug Fixes

* remove duplicate execute_query method in DatabaseManager ([af77fe1](https://github.com/TeamPew/pewstats-collectors/commit/af77fe1ef753b1c1e573ba2e8b3fb1dbff16a697))

## [1.4.6](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.5...v1.4.6) (2025-10-06)


### Bug Fixes

* use dict key access for psycopg3 rows with dict_row factory ([dfd5691](https://github.com/TeamPew/pewstats-collectors/commit/dfd5691a83b5b1345f56c68ac7655d81575359e4))
* use dict key access for psycopg3 rows with dict_row factory ([92349a6](https://github.com/TeamPew/pewstats-collectors/commit/92349a6fa8f9548e4449446905cc579d878005d2))

## [1.4.5](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.4...v1.4.5) (2025-10-06)


### Bug Fixes

* simplify database queries and improve error logging ([63a3b1c](https://github.com/TeamPew/pewstats-collectors/commit/63a3b1cf1ad2fee0b1420f7045362a59fdb73805))
* simplify database queries and improve error logging ([d5a1b2e](https://github.com/TeamPew/pewstats-collectors/commit/d5a1b2e835ff6c74a7e5c972908252cb977761fd))

## [1.4.4](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.3...v1.4.4) (2025-10-06)


### Bug Fixes

* use context manager correctly with explicit commit for read queries ([75d9adc](https://github.com/TeamPew/pewstats-collectors/commit/75d9adce27607053441af6b262be04bc19ce4c6a))
* use context manager correctly with explicit commit for read queries ([0e6e384](https://github.com/TeamPew/pewstats-collectors/commit/0e6e384b2ad736ea527882a0b006dab7a9ce5d4b))

## [1.4.3](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.2...v1.4.3) (2025-10-06)


### Bug Fixes

* correct database connection handling in telemetry worker ([71a09dd](https://github.com/TeamPew/pewstats-collectors/commit/71a09dd607b64c13a10a61cc3dfc7183e53aff37))
* correct database connection handling in telemetry worker ([5d4a696](https://github.com/TeamPew/pewstats-collectors/commit/5d4a69694220d4f932b6ee826700f84a462555d3))

## [1.4.2](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.1...v1.4.2) (2025-10-06)


### Bug Fixes

* correct kill extraction validation and add game_type filtering ([75bbb26](https://github.com/TeamPew/pewstats-collectors/commit/75bbb26cec00fbc3fbaa75d86fcdf81a9b3c9a74))
* use monkeypatch instead of mocker in telemetry tests ([dd3870c](https://github.com/TeamPew/pewstats-collectors/commit/dd3870c3e3007af7d2f8828c4ba0827264a3207c))

## [1.4.1](https://github.com/TeamPew/pewstats-collectors/compare/v1.4.0...v1.4.1) (2025-10-06)


### Bug Fixes

* handle None values in telemetry event extraction ([fc218df](https://github.com/TeamPew/pewstats-collectors/commit/fc218df837e14311fb06b8ae18c4df1bdd85ba72))
* handle None values in telemetry event extraction ([3406408](https://github.com/TeamPew/pewstats-collectors/commit/34064088e232e5ad16df5cb2df7ca50f0bc86a0f))

## [1.4.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.3.0...v1.4.0) (2025-10-06)


### Features

* add smart partial reprocessing for telemetry events ([10e5c40](https://github.com/TeamPew/pewstats-collectors/commit/10e5c4020b08d71b72b7fa98d1a79e1a6f2d06a0))
* add smart partial reprocessing for telemetry events ([01ea788](https://github.com/TeamPew/pewstats-collectors/commit/01ea788992b9d8b043a0c75650bb5c9bcc0cc744))

## [1.3.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.2.0...v1.3.0) (2025-10-06)


### Features

* add kill, weapon, and damage event extraction to telemetry processing ([c057850](https://github.com/TeamPew/pewstats-collectors/commit/c057850e2b1c0268079296514dce26a7c07015ae))


### Bug Fixes

* format telemetry_processing_worker.py with ruff ([6a1892a](https://github.com/TeamPew/pewstats-collectors/commit/6a1892a873d8e0aa666140f5e1a990ad8aa60c15))

## [1.2.0](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.10...v1.2.0) (2025-10-06)


### Features

* add script to republish lost telemetry messages ([52fa455](https://github.com/TeamPew/pewstats-collectors/commit/52fa4557a32663ae3cac15b37a799c9851707b0d))
* add script to republish lost telemetry messages ([0bf7ee7](https://github.com/TeamPew/pewstats-collectors/commit/0bf7ee7beabe171dd02ebf93ed8e5bedda1e9ccb))

## [1.1.10](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.9...v1.1.10) (2025-10-06)


### Bug Fixes

* correct PUBGClient method name in match summary worker ([fc1a031](https://github.com/TeamPew/pewstats-collectors/commit/fc1a0317be7eec0b6e1a3217d0a465bdae31a253))
* update tests to use correct PUBGClient method name ([9902e2a](https://github.com/TeamPew/pewstats-collectors/commit/9902e2ae5d4445c1f79f2a04bca28d7583f62ca1))

## [1.1.9](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.8...v1.1.9) (2025-10-06)


### Bug Fixes

* change RabbitMQ consumer to use manual acknowledgment ([bd5a583](https://github.com/TeamPew/pewstats-collectors/commit/bd5a5830328772b68ff596d34ff9d7b3391481f6))
* change RabbitMQ consumer to use manual acknowledgment ([a620e45](https://github.com/TeamPew/pewstats-collectors/commit/a620e459d2470211136a0ac41217c1cb14772ef8))

## [1.1.8](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.7...v1.1.8) (2025-10-06)


### Bug Fixes

* add discover-matches CLI entry point and fix Dockerfile install … ([99a79ac](https://github.com/TeamPew/pewstats-collectors/commit/99a79ac8e03a38f5f9466fb6ff2abc1d2b9bae06))
* add discover-matches CLI entry point and fix Dockerfile install order ([994d42f](https://github.com/TeamPew/pewstats-collectors/commit/994d42f75eb93b6fb3f686602adebb124d6cf87b))

## [1.1.7](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.6...v1.1.7) (2025-10-06)


### Bug Fixes

* correct queue names in all workers to match publisher workflow ([bce23a9](https://github.com/TeamPew/pewstats-collectors/commit/bce23a927b06a8c14ce901108b7604a7480e29d8))
* update match discovery service command to enable continuous mode ([d0bba4f](https://github.com/TeamPew/pewstats-collectors/commit/d0bba4fb82f77277115525043c9cc7b0370ba4f6))

## [1.1.6](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.5...v1.1.6) (2025-10-06)


### Bug Fixes

* add continuous mode to match discovery service ([a14695c](https://github.com/TeamPew/pewstats-collectors/commit/a14695c32ddf2b598c5718f600f6acfec9c5d903))
* correct parameter names in telemetry download worker initialization ([3d74e8e](https://github.com/TeamPew/pewstats-collectors/commit/3d74e8e53c501f9a33b2b8d5c324d569100b3dac))

## [1.1.5](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.4...v1.1.5) (2025-10-06)


### Bug Fixes

* remove unused storage_path parameter from telemetry processing w… ([6428ca2](https://github.com/TeamPew/pewstats-collectors/commit/6428ca2d0296f3059a829e6d775f7a2dc55b1624))
* remove unused storage_path parameter from telemetry processing worker ([eb7f8ad](https://github.com/TeamPew/pewstats-collectors/commit/eb7f8ad30214c5989e9820ad664751ff67df131c))

## [1.1.4](https://github.com/TeamPew/pewstats-collectors/compare/v1.1.3...v1.1.4) (2025-10-06)


### Bug Fixes

* add missing _build_exchange_name method to RabbitMQConsumer ([1f0ac37](https://github.com/TeamPew/pewstats-collectors/commit/1f0ac37ab7311a6fed767b758ff7f238ab471f76))
* add queue declaration to RabbitMQ publisher ([56bbda1](https://github.com/TeamPew/pewstats-collectors/commit/56bbda1cfd5f2bac59572b08f6cfb74e359dd00f))
* format match_discovery.py with ruff ([ed3a66b](https://github.com/TeamPew/pewstats-collectors/commit/ed3a66b782370299e4050326ca582768f3402f79))
* remove rate limiting from /matches endpoint ([71010d6](https://github.com/TeamPew/pewstats-collectors/commit/71010d6128bb54590d727ea81c4586949799b945))

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
