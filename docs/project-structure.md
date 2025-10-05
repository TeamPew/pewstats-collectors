# Python Project Structure

## Overview

This document defines the project structure for the PewStats collectors Python implementation.

## Design Principles

1. **Separation of Concerns** - Core components, services, and workers are clearly separated
2. **Testability** - Structure supports unit and integration testing
3. **Configuration Management** - Centralized configuration with environment variable support
4. **Reusability** - Shared utilities and base classes
5. **Type Safety** - Full type hints and Pydantic models
6. **Standard Python Practices** - Follows PEP 8 and common Python project conventions

---

## Directory Structure

```
pewstats-collectors/
├── .claude/                    # Claude AI context files
│   └── claude.md
├── docs/                       # Documentation
│   ├── pubg-api-schemas.md
│   ├── database-schemas.md
│   └── project-structure.md
├── src/                        # Source code
│   └── pewstats_collectors/   # Main package
│       ├── __init__.py
│       ├── __main__.py        # Entry point for CLI
│       │
│       ├── core/              # Core components (reusable)
│       │   ├── __init__.py
│       │   ├── api_key_manager.py
│       │   ├── pubg_client.py
│       │   ├── database.py
│       │   └── rabbitmq.py
│       │
│       ├── services/          # Service orchestrators
│       │   ├── __init__.py
│       │   ├── base_service.py
│       │   └── match_discovery.py
│       │
│       ├── workers/           # Event-driven workers
│       │   ├── __init__.py
│       │   ├── base_worker.py
│       │   ├── match_summary_worker.py
│       │   ├── telemetry_download_worker.py
│       │   └── telemetry_processing_worker.py
│       │
│       ├── models/            # Data models (Pydantic)
│       │   ├── __init__.py
│       │   ├── api.py         # PUBG API response models
│       │   ├── database.py    # Database models (SQLAlchemy)
│       │   └── messages.py    # RabbitMQ message models
│       │
│       ├── utils/             # Utilities
│       │   ├── __init__.py
│       │   ├── constants.py   # All constant dictionaries
│       │   ├── logging.py     # Logging configuration
│       │   └── helpers.py     # Helper functions
│       │
│       └── config/            # Configuration
│           ├── __init__.py
│           └── settings.py    # Settings (environment variables)
│
├── tests/                     # Tests
│   ├── __init__.py
│   ├── unit/                  # Unit tests
│   │   ├── __init__.py
│   │   ├── test_api_key_manager.py
│   │   ├── test_pubg_client.py
│   │   ├── test_database.py
│   │   └── test_rabbitmq.py
│   ├── integration/           # Integration tests
│   │   ├── __init__.py
│   │   ├── test_match_discovery.py
│   │   └── test_workers.py
│   └── fixtures/              # Test fixtures
│       ├── __init__.py
│       ├── mock_api_responses.py
│       └── mock_telemetry.py
│
├── scripts/                   # Utility scripts
│   ├── create_tables.py       # Initialize database
│   ├── seed_players.py        # Seed test data
│   └── run_worker.py          # Run individual worker
│
├── alembic/                   # Database migrations
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
│
├── .env.example               # Example environment variables
├── .gitignore
├── pyproject.toml             # Project metadata and dependencies
├── requirements.txt           # Pip requirements (generated from pyproject.toml)
├── README.md
└── Dockerfile                 # Container definition

```

---

## Package Details

### 1. Core Components (`src/pewstats_collectors/core/`)

**Purpose:** Reusable components used across services and workers.

#### `api_key_manager.py`

```python
"""API Key Manager - Round-robin selection with per-key rate limiting"""

class APIKey:
    """Represents a single API key with rate limiting state"""
    key: str
    rpm_limit: int
    request_times: List[datetime]

class APIKeyManager:
    """Manages pool of API keys with round-robin selection"""
    def __init__(self, keys: List[Dict[str, Any]])
    def select_key(self) -> APIKey
    def record_request(self, key: APIKey) -> None
    def wait_if_needed(self, key: APIKey) -> None
    def can_make_request(self, key: APIKey) -> bool
```

#### `pubg_client.py`

```python
"""PUBG API Client - HTTP wrapper for PUBG API"""

class PUBGClient:
    """Client for PUBG API with rate limiting and retries"""
    def __init__(self, api_key_manager: APIKeyManager, platform: str = "steam")
    def get_players(self, player_names: List[str]) -> PlayerResponse
    def get_match(self, match_id: str) -> MatchResponse
    def _make_request(self, endpoint: str, params: Dict) -> Dict
    def _handle_rate_limit(self, response: Response) -> None
```

#### `database.py`

```python
"""Database Manager - PostgreSQL connection and operations"""

class DatabaseManager:
    """Manages PostgreSQL connections and queries"""
    def __init__(self, connection_string: str)
    def get_connection(self) -> Connection
    def health_check(self) -> bool

    # Player queries
    def get_tracked_players(self) -> List[Player]
    def get_existing_match_ids(self) -> Set[str]

    # Match operations
    def insert_match(self, metadata: MatchMetadata) -> None
    def update_match_status(self, match_id: str, status: str, error: str = None) -> None
    def update_processing_flags(self, match_id: str, **flags) -> None

    # Match summaries
    def insert_match_summaries(self, summaries: List[MatchSummary]) -> None
    def match_summaries_exist(self, match_id: str) -> bool

    # Telemetry data
    def insert_landings(self, landings: List[Landing]) -> None
    def insert_kill_positions(self, kills: List[KillPosition]) -> None
    def insert_damage_events(self, events: List[DamageEvent]) -> None
    def insert_weapon_kills(self, kills: List[WeaponKill]) -> None
    def insert_circles(self, circles: List[CirclePosition]) -> None
```

#### `rabbitmq.py`

```python
"""RabbitMQ Publisher - Message publishing"""

class RabbitMQPublisher:
    """Publishes messages to RabbitMQ exchanges"""
    def __init__(self, connection_string: str)
    def connect(self) -> None
    def health_check(self) -> bool
    def publish(self, exchange: str, routing_key: str, message: Dict) -> bool
    def close(self) -> None
```

---

### 2. Services (`src/pewstats_collectors/services/`)

**Purpose:** Scheduled services that orchestrate workflows.

#### `base_service.py`

```python
"""Base Service - Common service functionality"""

class BaseService:
    """Base class for all services"""
    def __init__(self, db: DatabaseManager, rabbitmq: RabbitMQPublisher, logger: Logger)
    def pre_flight_check(self) -> bool
    def run(self) -> None  # Abstract method
    def log_summary(self, stats: Dict) -> None
```

#### `match_discovery.py`

```python
"""Match Discovery Service - Discover new matches from PUBG API"""

class MatchDiscoveryService(BaseService):
    """Discovers new matches for tracked players"""
    def __init__(
        self,
        db: DatabaseManager,
        rabbitmq: RabbitMQPublisher,
        pubg_client: PUBGClient,
        logger: Logger
    )

    def run(self) -> None:
        """Main discovery loop"""
        # 1. Pre-flight checks (DB + RabbitMQ)
        # 2. Get tracked players
        # 3. Get existing match IDs
        # 4. Process players in batches
        # 5. Discover new matches
        # 6. Insert to DB and publish to RabbitMQ
        # 7. Log summary

    def discover_matches_for_players(self, players: List[Player]) -> List[str]
    def process_player_batch(self, batch: List[Player], existing_ids: Set[str]) -> List[MatchMetadata]
    def fetch_match_details(self, match_id: str) -> MatchMetadata
```

---

### 3. Workers (`src/pewstats_collectors/workers/`)

**Purpose:** Event-driven workers that consume RabbitMQ messages.

#### `base_worker.py`

```python
"""Base Worker - Common worker functionality"""

class BaseWorker:
    """Base class for all workers"""
    def __init__(
        self,
        worker_id: str,
        db: DatabaseManager,
        rabbitmq_consumer: RabbitMQConsumer,
        logger: Logger
    )

    def start(self) -> None
    def stop(self) -> None
    def process_message(self, message: Dict) -> bool  # Abstract method
    def acknowledge_message(self, delivery_tag: str) -> None
    def reject_message(self, delivery_tag: str, requeue: bool = False) -> None
    def update_health_status(self) -> None
```

#### `match_summary_worker.py`

```python
"""Match Summary Worker - Process match participant data"""

class MatchSummaryWorker(BaseWorker):
    """Processes match.discovered messages"""
    def __init__(self, worker_id: str, db: DatabaseManager, pubg_client: PUBGClient, ...)

    def process_message(self, message: MatchDiscoveredMessage) -> bool:
        # 1. Check if summaries already exist
        # 2. Fetch match data from PUBG API
        # 3. Extract telemetry URL
        # 4. Parse match summaries
        # 5. Insert to database
        # 6. Publish to telemetry queue
        # 7. Update match status

    def parse_match_summaries(self, match_data: MatchResponse) -> List[MatchSummary]
    def extract_telemetry_url(self, match_data: MatchResponse) -> str
```

#### `telemetry_download_worker.py`

```python
"""Telemetry Download Worker - Download telemetry files"""

class TelemetryDownloadWorker(BaseWorker):
    """Processes match.summary_complete messages"""
    def __init__(self, worker_id: str, db: DatabaseManager, storage_path: str, ...)

    def process_message(self, message: MatchSummaryCompleteMessage) -> bool:
        # 1. Download telemetry from URL
        # 2. Compress and store locally
        # 3. Publish to telemetry processing queue

    def download_telemetry(self, url: str) -> bytes
    def store_telemetry(self, match_id: str, data: bytes) -> str
```

#### `telemetry_processing_worker.py`

```python
"""Telemetry Processing Worker - Extract data from telemetry files"""

class TelemetryProcessingWorker(BaseWorker):
    """Processes match.telemetry_downloaded messages"""
    def __init__(self, worker_id: str, db: DatabaseManager, storage_path: str, ...)

    def process_message(self, message: TelemetryDownloadedMessage) -> bool:
        # 1. Load telemetry file
        # 2. Parse events (single pass)
        # 3. Extract landings
        # 4. Extract kills
        # 5. Extract damage
        # 6. Extract weapons
        # 7. Extract circles
        # 8. Insert all to database
        # 9. Update processing flags
        # 10. Publish completion message

    def load_telemetry(self, match_id: str) -> List[Dict]
    def extract_landings(self, events: List[Dict]) -> List[Landing]
    def extract_kills(self, events: List[Dict]) -> List[KillPosition]
    def extract_damage(self, events: List[Dict]) -> List[DamageEvent]
    def extract_weapons(self, events: List[Dict]) -> List[WeaponKill]
    def extract_circles(self, events: List[Dict]) -> List[CirclePosition]
```

---

### 4. Models (`src/pewstats_collectors/models/`)

**Purpose:** Type-safe data models using Pydantic and SQLAlchemy.

#### `api.py` - PUBG API Models

```python
"""Pydantic models for PUBG API responses"""

class PlayerAttributes(BaseModel):
    name: str
    shardId: str
    createdAt: datetime
    # ...

class PlayerData(BaseModel):
    type: str
    id: str
    attributes: PlayerAttributes
    relationships: dict

class PlayerResponse(BaseModel):
    data: List[PlayerData]
    links: dict
    meta: dict

class MatchAttributes(BaseModel):
    createdAt: datetime
    duration: int
    gameMode: str
    mapName: str
    # ...

class MatchResponse(BaseModel):
    data: dict
    included: List[dict]
    # ...
```

#### `database.py` - SQLAlchemy Models

```python
"""SQLAlchemy ORM models for database tables"""

class Player(Base):
    __tablename__ = "players"
    player_id: Mapped[str] = mapped_column(primary_key=True)
    player_name: Mapped[str]
    tracking_enabled: Mapped[bool]
    # ...

class Match(Base):
    __tablename__ = "matches"
    match_id: Mapped[str] = mapped_column(primary_key=True)
    map_name: Mapped[str]
    game_mode: Mapped[str]
    status: Mapped[str]
    # ...

class MatchSummary(Base):
    __tablename__ = "match_summaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[str]
    player_id: Mapped[str]
    # ...
```

#### `messages.py` - RabbitMQ Messages

```python
"""Pydantic models for RabbitMQ messages"""

class MatchDiscoveredMessage(BaseModel):
    match_id: str
    map_name: str
    game_mode: str
    match_datetime: datetime
    telemetry_url: Optional[str]

class MatchSummaryCompleteMessage(BaseModel):
    match_id: str
    telemetry_url: str
    participant_count: int
    # ...

class TelemetryDownloadedMessage(BaseModel):
    match_id: str
    file_path: str
    # ...
```

---

### 5. Configuration (`src/pewstats_collectors/config/`)

#### `settings.py`

```python
"""Configuration management using Pydantic Settings"""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str

    # RabbitMQ
    rabbitmq_url: str

    # PUBG API Keys
    pubg_api_keys: List[Dict[str, Any]]  # JSON string parsed to list
    pubg_platform: str = "steam"

    # Paths
    telemetry_storage_path: str = "/opt/pewstats-platform/data/telemetry"

    # Logging
    log_level: str = "INFO"

    # Match Discovery
    discovery_schedule_cron: str = "*/10 * * * *"
    player_batch_size: int = 10

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

### 6. Utilities (`src/pewstats_collectors/utils/`)

#### `constants.py`

```python
"""All constant dictionaries (maps, game modes, damage types, etc.)"""

MAP_NAMES = { ... }
GAME_MODES = { ... }
GAME_TYPES = { ... }
DAMAGE_TYPE_CATEGORIES = { ... }
DAMAGE_CAUSER_NAMES = { ... }
```

#### `logging.py`

```python
"""Logging configuration"""

def setup_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Configure structured logging"""
    # JSON logging for production
    # Human-readable for development
```

#### `helpers.py`

```python
"""Helper functions"""

def translate_map_name(internal_name: str) -> str:
    """Translate internal map name to display name"""

def chunk_list(items: List, chunk_size: int) -> Iterator[List]:
    """Split list into chunks"""
```

---

## Entry Points

### CLI Entry Point (`src/pewstats_collectors/__main__.py`)

```python
"""CLI entry point for running services and workers"""

import click

@click.group()
def cli():
    """PewStats Collectors CLI"""
    pass

@cli.command()
def match-discovery():
    """Run match discovery service"""
    # Initialize and run MatchDiscoveryService

@cli.command()
@click.option('--worker-id', required=True)
def match-summary-worker(worker_id: str):
    """Run match summary worker"""
    # Initialize and run MatchSummaryWorker

@cli.command()
@click.option('--worker-id', required=True)
def telemetry-download-worker(worker_id: str):
    """Run telemetry download worker"""
    # Initialize and run TelemetryDownloadWorker

@cli.command()
@click.option('--worker-id', required=True)
def telemetry-processing-worker(worker_id: str):
    """Run telemetry processing worker"""
    # Initialize and run TelemetryProcessingWorker

if __name__ == "__main__":
    cli()
```

**Usage:**
```bash
# Run match discovery
python -m pewstats_collectors match-discovery

# Run workers
python -m pewstats_collectors match-summary-worker --worker-id worker-1
python -m pewstats_collectors telemetry-download-worker --worker-id worker-1
python -m pewstats_collectors telemetry-processing-worker --worker-id worker-1
```

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "pewstats-collectors"
version = "0.1.0"
description = "PUBG match data collectors for PewStats"
requires-python = ">=3.11"

dependencies = [
    "requests>=2.31.0",           # HTTP client
    "pydantic>=2.5.0",            # Data validation
    "pydantic-settings>=2.1.0",   # Settings management
    "psycopg[binary]>=3.1.0",     # PostgreSQL adapter
    "sqlalchemy>=2.0.0",          # ORM
    "alembic>=1.13.0",            # Database migrations
    "pika>=1.3.0",                # RabbitMQ client
    "click>=8.1.0",               # CLI framework
    "python-dotenv>=1.0.0",       # .env file support
    "tenacity>=8.2.0",            # Retry logic
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "pytest-asyncio>=0.21.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]

[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.mypy]
python_version = "3.11"
strict = true
```

---

## Testing Structure

### Unit Tests (`tests/unit/`)

Test individual components in isolation with mocked dependencies.

```python
# tests/unit/test_api_key_manager.py
def test_round_robin_selection():
    """Test round-robin key selection"""

def test_rate_limit_enforcement():
    """Test rate limiting blocks when limit reached"""

# tests/unit/test_pubg_client.py
@mock.patch('requests.get')
def test_get_players_success(mock_get):
    """Test successful player fetch"""

def test_get_match_retry_on_429():
    """Test retry logic on rate limit"""
```

### Integration Tests (`tests/integration/`)

Test end-to-end workflows with real dependencies (test database, test RabbitMQ).

```python
# tests/integration/test_match_discovery.py
def test_match_discovery_flow(test_db, test_rabbitmq):
    """Test complete match discovery workflow"""
```

---

## Docker Support

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install -e .

# Copy source code
COPY src/ ./src/

# Run service
CMD ["python", "-m", "pewstats_collectors", "match-discovery"]
```

### `docker-compose.yml` (for development)

```yaml
version: '3.8'

services:
  match-discovery:
    build: .
    command: python -m pewstats_collectors match-discovery
    env_file: .env
    depends_on:
      - postgres
      - rabbitmq

  match-summary-worker:
    build: .
    command: python -m pewstats_collectors match-summary-worker --worker-id worker-1
    env_file: .env
    depends_on:
      - postgres
      - rabbitmq
```

---

## Next Steps

1. Create directory structure
2. Implement core components (API Key Manager, PUBG Client, etc.)
3. Implement services (Match Discovery)
4. Implement workers
5. Write tests
6. Create Docker images
7. Deploy and monitor
