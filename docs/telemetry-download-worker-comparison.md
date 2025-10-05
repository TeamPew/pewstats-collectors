# Telemetry Download Worker: R vs Python Comparison

## Overview

The Telemetry Download Worker downloads telemetry JSON files from PUBG CDN URLs and stores them locally for processing.

**R Implementation:** `/opt/pewstats-platform/services/staging/pewstats-collectors-service-old/R/workers/telemetry-worker.R` (lines 284-413)
**Python Implementation:** `src/pewstats_collectors/workers/telemetry_download_worker.py` (to be created)

---

## R Implementation Analysis

### Core Functionality

The R `TelemetryWorker` is actually a **combined** worker that:
1. Downloads telemetry JSON from CDN
2. Cleans/flattens the telemetry (complex nested JSON → flat dataframe)
3. Stores as Parquet files (partitioned by matchID)
4. Publishes to stats queue

### Download Logic (`downloadTelemetry` method)

```r
downloadTelemetry = function(telemetry_url, match_id) {
  max_attempts <- 3
  for (attempt in seq_len(max_attempts)) {
    # Download JSON file
    download.file(telemetry_url, destfile = tmp_file, timeout = 120)

    # Check if already gzipped (magic number check)
    is_gzipped <- function(path) {
      con <- file(path, "rb")
      magic <- readBin(con, "raw", n = 2)
      close(con)
      identical(as.integer(magic), c(0x1f, 0x8b))
    }

    # Save raw gzipped JSON
    if (grepl("\\.gz$", telemetry_url) || is_gzipped(tmp_file)) {
      file.copy(tmp_file, raw_gz_path, overwrite = TRUE)
    } else {
      # Compress using base R gzip
      gzip_file_base(tmp_file, raw_gz_path)
    }

    # Parse JSON for cleaning
    telemetry_data <- jsonlite::fromJSON(json_parse_file)
    return(telemetry_data)
  }
}
```

### Key Features

#### 1. **File Storage Structure**

```
/opt/pewstats-platform/data/telemetry/
└── matchID=<match_id>/
    ├── raw.json.gz          # Raw gzipped JSON
    └── part-0.parquet       # Cleaned parquet (R implementation)
```

#### 2. **Download with Retry**

- **3 attempts** with exponential backoff (2^attempt seconds)
- **120-second timeout** per attempt
- Downloads to temp file first, then moves to final location

#### 3. **Compression Handling**

- Checks if URL ends with `.gz`
- Checks magic number (0x1f 0x8b) to detect gzip
- If not gzipped: compresses using base R gzip
- If already gzipped: just copy

#### 4. **Idempotency**

```r
if (self$telemetryExists(match_id)) {
  # File already exists, skip download
  # Still publish stats message
  return(list(success = TRUE, reason = "already_exists"))
}
```

Checks for existing file at: `data_path/matchID=<match_id>/part-0.parquet`

#### 5. **Message Processing Flow**

```
1. Validate match_id and telemetry_url
2. Check if telemetry already exists
   └─> If yes: update status to "completed", publish stats, return
3. Download telemetry JSON (with retry)
4. Clean telemetry (flatten JSON structure)
5. Store as Parquet file
6. Update match status to "completed"
7. Publish stats message (with player_ids)
8. Return success
```

#### 6. **Stats Publishing**

```r
publishStatsMessage = function(telemetry_data, match_id, original_message) {
  # Extract unique player names from telemetry
  all_player_names <- unique(telemetry_data$character_name[!is.na(telemetry_data$character_name)])

  # Filter to only tracked players
  tracked_players <- DBI::dbGetQuery(self$database, "SELECT player_name FROM players")$player_name
  player_ids <- all_player_names[all_player_names %in% tracked_players]

  # Create stats message
  stats_message <- list(
    match_id = match_id,
    player_ids = player_ids,
    processed_at = Sys.time(),
    map_name = original_message$map_name,
    game_mode = original_message$game_mode,
    telemetry_worker_id = self$worker_id
  )

  # Publish to match.stats queue
  publish_success <- self$publish_message("match", "stats", stats_message)
}
```

**Purpose:** Notify stats calculation worker which players were in this match.

---

## Python Implementation Plan

### Design Decisions

#### 1. **Simplification: Download-Only Worker**

The Python implementation will **split** the R worker into two separate workers:

1. **Telemetry Download Worker** (this worker):
   - Downloads raw JSON
   - Stores compressed locally
   - Publishes to `match.processing.telemetry` queue

2. **Telemetry Processing Worker** (next worker):
   - Reads raw JSON
   - Processes into database tables (landings, kills, circles, damage, etc.)
   - Updates match status

**Rationale:**
- **Cleaner separation of concerns**
- **No Parquet storage needed** - we process directly into PostgreSQL
- **Easier to test and maintain**
- **Better error isolation** - download failures vs. processing failures

#### 2. **File Storage**

```
/opt/pewstats-platform/data/telemetry/
└── matchID=<match_id>/
    └── raw.json.gz          # Only store gzipped raw JSON
```

**Changes from R:**
- **No Parquet files** - process raw JSON directly into database
- **Same directory structure** - compatible with existing data
- **Simpler storage** - just raw gzipped JSON

#### 3. **Download Implementation**

Use Python's `requests` library with:
- **Streaming download** for large files
- **Automatic compression detection** (Content-Encoding header)
- **Manual gzip** if not already compressed
- **Retry logic** with exponential backoff

```python
import requests
import gzip
import shutil

def download_telemetry(url: str, match_id: str, max_attempts: int = 3) -> Dict[str, Any]:
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, stream=True, timeout=120)
            response.raise_for_status()

            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp.write(chunk)
                tmp_path = tmp.name

            # Check if already gzipped
            if url.endswith('.gz') or is_gzipped(tmp_path):
                # Just move
                shutil.move(tmp_path, final_path)
            else:
                # Compress
                with open(tmp_path, 'rb') as f_in:
                    with gzip.open(final_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(tmp_path)

            return {"success": True, "size": os.path.getsize(final_path)}

        except Exception as e:
            if attempt == max_attempts:
                raise
            time.sleep(2 ** attempt)
```

#### 4. **Message Contract**

**Consumes from:** `match.telemetry.{env}`

**Expected message:**
```python
{
    "match_id": str,
    "telemetry_url": str,
    "map_name": str,
    "game_mode": str,
    "match_datetime": str,
    # ... other metadata from match summary worker
}
```

**Publishes to:** `match.processing.telemetry.{env}`

**Published message:**
```python
{
    "match_id": str,
    "file_path": str,              # Path to raw.json.gz
    "file_size_mb": float,          # File size in MB
    "map_name": str,
    "game_mode": str,
    "match_datetime": str,
    "downloaded_at": str,           # ISO 8601 timestamp
    "worker_id": str
}
```

**Note:** We're **NOT** publishing to stats queue here - that will be done by the processing worker after extracting events.

#### 5. **Error Handling**

```python
def process_message(self, data: Dict[str, Any]) -> Dict[str, Any]:
    match_id = data.get("match_id")
    telemetry_url = data.get("telemetry_url")

    try:
        # Validate inputs
        if not match_id or not telemetry_url:
            return {"success": False, "error": "Missing required fields"}

        # Check if already downloaded (idempotency)
        if self.telemetry_exists(match_id):
            self.logger.info(f"Telemetry already exists for {match_id}")
            # Still publish to processing queue
            self._publish_processing_message(match_id, data)
            return {"success": True, "reason": "already_exists"}

        # Download
        result = self.download_telemetry(telemetry_url, match_id)

        # Publish to processing queue
        self._publish_processing_message(match_id, data, result)

        self.processed_count += 1
        return {"success": True}

    except Exception as e:
        self.logger.error(f"Failed to download telemetry for {match_id}: {e}")
        self.error_count += 1
        return {"success": False, "error": str(e)}
```

---

## Feature Comparison

| Feature | R Implementation | Python Implementation |
|---------|------------------|----------------------|
| **Queue Consumption** | `match.telemetry` | `match.telemetry.{env}` |
| **Download Method** | `download.file()` | `requests.get()` with streaming |
| **Retry Logic** | 3 attempts, exponential backoff | Same |
| **Timeout** | 120 seconds | 120 seconds |
| **Compression Detection** | Magic number check + extension | Same |
| **Compression Method** | Base R gzip functions | Python gzip module |
| **File Storage** | `matchID=X/raw.json.gz` + `part-0.parquet` | `matchID=X/raw.json.gz` only |
| **Telemetry Cleaning** | Full flatten to dataframe | **NOT DONE** (separate worker) |
| **Parquet Storage** | Yes (via Arrow) | **NO** |
| **Idempotency Check** | Check for part-0.parquet | Check for raw.json.gz |
| **Queue Publishing** | `match.stats` | `match.processing.telemetry` |
| **Status Update** | Update to "completed" | **NOT DONE** (processing worker does this) |

---

## Critical Business Logic to Preserve

### 1. **Idempotency**

```python
def telemetry_exists(self, match_id: str) -> bool:
    """Check if telemetry file already downloaded"""
    file_path = os.path.join(
        self.data_path,
        f"matchID={match_id}",
        "raw.json.gz"
    )
    return os.path.exists(file_path)
```

### 2. **Retry with Exponential Backoff**

```python
max_attempts = 3
for attempt in range(1, max_attempts + 1):
    try:
        # Download logic
        break
    except Exception as e:
        if attempt == max_attempts:
            raise
        wait_time = 2 ** attempt
        time.sleep(wait_time)
```

### 3. **Compression Handling**

```python
def is_gzipped(file_path: str) -> bool:
    """Check if file is gzipped using magic number"""
    with open(file_path, 'rb') as f:
        magic = f.read(2)
    return magic == b'\\x1f\\x8b'
```

### 4. **Directory Creation**

```python
match_dir = os.path.join(self.data_path, f"matchID={match_id}")
os.makedirs(match_dir, exist_ok=True)
```

---

## Implementation Improvements

### 1. **Streaming Download**

```python
# More memory efficient for large files
response = requests.get(url, stream=True, timeout=120)
with open(tmp_path, 'wb') as f:
    for chunk in response.iter_content(chunk_size=8192):
        if chunk:
            f.write(chunk)
```

### 2. **File Size Validation**

```python
file_size = os.path.getsize(file_path)
if file_size == 0:
    raise ValueError("Downloaded file is empty")
```

### 3. **Atomic File Operations**

```python
# Download to temp file first, then move
# Prevents partial files if process crashes
tmp_path = tempfile.mktemp(suffix='.json.gz')
# ... download to tmp_path ...
shutil.move(tmp_path, final_path)
```

### 4. **Better Logging**

```python
self.logger.info(
    f"[{self.worker_id}] Downloaded telemetry for {match_id}: "
    f"{file_size_mb:.2f} MB in {elapsed:.2f}s"
)
```

---

## Testing Strategy

### Unit Tests

1. **test_download_telemetry_success**
   - Mock requests.get
   - Verify file created
   - Verify compression

2. **test_download_telemetry_already_gzipped**
   - Mock gzipped response
   - Verify no recompression

3. **test_download_telemetry_retry**
   - Mock failures
   - Verify retry logic
   - Verify exponential backoff

4. **test_telemetry_exists**
   - File exists: return True
   - File missing: return False

5. **test_process_message_success**
   - Complete flow
   - Verify publish to processing queue

6. **test_process_message_already_exists**
   - Idempotency
   - Still publish to queue

7. **test_process_message_missing_url**
   - Validation
   - Return error

8. **test_process_message_download_failure**
   - Download fails
   - Error handling

### Integration Tests

1. **test_download_real_telemetry** (if CDN URL available)
   - Real download
   - Verify file integrity

---

## Migration Notes

- **Data path:** Use `/opt/pewstats-platform/data/telemetry` (same as R)
- **File structure:** Compatible with R (same matchID=X directory structure)
- **Queue names:** Use environment-aware naming (`.prod`, `.staging`, etc.)
- **No status updates:** Leave match status updates to processing worker

---

## Summary

The Telemetry Download Worker is a **simplified** version of the R TelemetryWorker that focuses solely on downloading and storing raw telemetry JSON files. The complex cleaning/flattening logic is moved to a separate processing worker that will directly extract database records from the raw JSON.

**Key simplifications:**
1. **No Parquet storage** - not needed
2. **No telemetry cleaning** - done in processing worker
3. **No stats publishing** - done in processing worker after extracting player data
4. **No status updates** - done in processing worker after successful processing

This makes the worker simpler, easier to test, and follows the single-responsibility principle.
