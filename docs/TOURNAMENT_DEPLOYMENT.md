# Tournament Discovery - Komodo Deployment Guide

**Last Updated**: 2025-10-14
**Deployment Method**: Docker Compose + Komodo
**Stack**: pewstats-collectors-prod (same as existing services)

---

## ✅ What Was Done

I've added the `tournament-discovery` service to your existing `compose.yaml` file. This means:

- ✅ **Same stack** as other pewstats-collectors services
- ✅ **Same Docker image** (ghcr.io/teampew/pewstats-collectors)
- ✅ **Same network** (pewstats-network)
- ✅ **Same environment variables** (POSTGRES_*, PUBG_API_KEYS, etc.)
- ✅ **Consistent resource limits** (512MB max, 256MB reserved)

---

## 🚀 Deployment Steps

### Prerequisites

Before deploying, ensure the tournament database migration has been applied:

```sql
-- Check if tables exist
\dt tournament*

-- If not, apply migration:
psql -h localhost -U pewstats_prod_user -d pewstats_production -f migrations/001_create_tournament_tables.sql
```

### Step 1: Update Your Docker Image

The tournament discovery service code needs to be included in your Docker image.

**Option A: Rebuild and Push Image**

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

# Build new image with tournament code
docker build -t ghcr.io/teampew/pewstats-collectors:latest .

# Push to registry
docker push ghcr.io/teampew/pewstats-collectors:latest

# Or tag as production
docker tag ghcr.io/teampew/pewstats-collectors:latest ghcr.io/teampew/pewstats-collectors:production
docker push ghcr.io/teampew/pewstats-collectors:production
```

**Option B: Use Existing CI/CD**

If you have GitHub Actions or similar CI/CD:
1. Commit the changes (compose.yaml + tournament code)
2. Push to your repository
3. Let CI/CD build and push the image
4. Tag the release appropriately

### Step 2: Deploy in Komodo

1. **Navigate to your Stack**
   - Open Komodo dashboard
   - Go to "Stacks" → "pewstats-collectors-prod"

2. **Update Stack Configuration**
   - Komodo should detect the updated `compose.yaml` automatically
   - Or manually trigger a stack update/redeploy

3. **Verify Environment Variables**

   Ensure these are set in your Komodo stack environment:
   ```env
   # Database (should already exist)
   POSTGRES_HOST=your_db_host
   POSTGRES_PORT=5432
   POSTGRES_DB=pewstats_production
   POSTGRES_USER=pewstats_prod_user
   POSTGRES_PASSWORD=your_password

   # PUBG API (should already exist)
   PUBG_API_KEYS=key1,key2,key3
   PUBG_PLATFORM=steam

   # Optional: Image tag
   IMAGE_TAG=production  # or latest

   # Optional: Logging
   LOG_LEVEL=INFO
   ENVIRONMENT=production
   ```

4. **Deploy the Stack**
   - Click "Deploy" or "Update" in Komodo
   - Komodo will pull the new image and start all services
   - The `tournament-discovery` service will start alongside existing services

### Step 3: Verify Deployment

#### Check Service Status in Komodo

1. Go to "Containers" in Komodo
2. Look for `tournament-discovery` container
3. Verify it's "Running"

#### Check Logs

In Komodo:
1. Click on `tournament-discovery` container
2. View logs
3. Look for:
   ```
   INFO - Initializing tournament match discovery service...
   INFO - Starting tournament match discovery pipeline
   INFO - Sampled X players from tournament roster
   ```

#### Verify Data

Connect to your database and check:

```sql
-- Check if service is discovering matches
SELECT COUNT(*) as match_count, MAX(discovered_at) as last_discovery
FROM tournament_matches;

-- Should see matches increasing every 60 seconds (if players are active)
```

---

## 📊 Service Configuration

### Default Settings

The service is configured with:

```yaml
command: ["python3", "-m", "pewstats_collectors.services.tournament_match_discovery",
          "--continuous", "--interval", "60", "--sample-size", "6"]
```

**What this means**:
- `--continuous`: Runs indefinitely (doesn't exit after one run)
- `--interval 60`: Checks for new matches every 60 seconds
- `--sample-size 6`: Samples 6 players per lobby (stratified sampling)

### Resource Limits

```yaml
resources:
  limits:
    cpus: "0.5"        # Max 50% of one CPU core
    memory: 512M       # Max 512MB RAM
  reservations:
    cpus: "0.25"       # Guaranteed 25% of one CPU
    memory: 256M       # Guaranteed 256MB RAM
```

This is lightweight - the service should use ~100-200MB RAM in practice.

### Restart Policy

```yaml
restart_policy:
  condition: on-failure  # Only restart if it crashes
  delay: 10s            # Wait 10s before restarting
  max_attempts: 3       # Try max 3 times before giving up
```

---

## 🔧 Scheduling Configuration

### Current Schedule (Default)

The service is **pre-configured** to run only during tournament hours:

```yaml
--schedule-enabled
--schedule-days "0,1,2,3,6"    # Mon, Tue, Wed, Thu, Sun (0=Monday, 6=Sunday)
--schedule-start "18:00"       # Start at 6:00 PM
--schedule-end "00:00"         # End at midnight
```

**Active Hours**: Monday-Thursday and Sunday from 18:00 to 00:00 (6 PM to midnight)

**Behavior**:
- Container runs 24/7 but only discovers matches during tournament hours
- Outside tournament hours: Logs "Outside tournament schedule" and sleeps for 5 minutes
- Automatically activates when 18:00 arrives on active days

### To Change the Schedule

Edit `compose.yaml` and modify the command parameters:

```yaml
tournament-discovery:
  command: [
    "python3", "-m", "pewstats_collectors.services.tournament_match_discovery",
    "--continuous",
    "--interval", "60",
    "--sample-size", "6",
    "--schedule-enabled",
    "--schedule-days", "0,1,2,3,4,5,6",  # All days (0=Mon, 6=Sun)
    "--schedule-start", "12:00",         # Noon
    "--schedule-end", "23:00"            # 11 PM
  ]
```

### To Disable Scheduling (Run 24/7)

Remove the schedule parameters:

```yaml
command: [
  "python3", "-m", "pewstats_collectors.services.tournament_match_discovery",
  "--continuous",
  "--interval", "60",
  "--sample-size", "6"
]
```

Then redeploy the stack in Komodo

---

## 📈 Monitoring

### View Logs in Komodo

1. Go to "Containers" → `tournament-discovery`
2. Click "Logs"
3. Look for:
   - `INFO - Sampled X players from tournament roster`
   - `INFO - Found X new tournament matches to process`
   - `INFO - Stored match XYZ with N participants`

### Check Service Health

**In Komodo Dashboard**:
- Container status should be "Running"
- No restart loops (restarts = 0 or low number)

**Via Database**:
```sql
-- Last discovery time
SELECT MAX(discovered_at) as last_run FROM tournament_matches;

-- Should be within last ~60 seconds if active

-- Matches discovered today
SELECT COUNT(*) FROM tournament_matches
WHERE discovered_at > CURRENT_DATE;
```

### Common Log Messages

**Normal Operation**:
```
INFO - Starting tournament match discovery pipeline
INFO - Sampled 9 players from tournament roster (sample size per lobby: 6)
INFO - Found 108 new matches (total 108, existing 0)
INFO - Found 6 new tournament matches to process
INFO - Stored match abc123 with 67 participants
INFO - Pipeline completed: Total matches: 6, Processed: 6, Failed: 0
```

**No Matches Found** (normal if no active tournament):
```
INFO - No new tournament matches found
```

**Outside Schedule** (if scheduling enabled):
```
INFO - Outside tournament schedule. Next active period in 300s
```

---

## 🐛 Troubleshooting

### Service Not Starting

**Check Logs in Komodo**:
1. Look for error messages
2. Common issues:
   - Database connection failed → Check POSTGRES_* env vars
   - Import errors → Docker image might not include tournament code
   - Permission issues → Check database user permissions

**Verify Image Has Tournament Code**:
```bash
# SSH into container (via Komodo or Docker)
docker exec -it <container-id> bash

# Check if module exists
python3 -c "import pewstats_collectors.services.tournament_match_discovery"
# Should not error

# Or check file exists
ls -la /app/src/pewstats_collectors/services/tournament_match_discovery.py
```

### Service Keeps Restarting

**Check Logs** for the error causing the crash:
```
# In Komodo, view full logs
# Look for Python tracebacks
```

Common causes:
- Database migration not applied
- Missing environment variables
- API key issues

### No Matches Being Discovered

**Possible Causes**:

1. **No Tournament Matches Active**
   - Players aren't in any custom esports matches right now
   - This is normal if not during tournament

2. **Players Not Registered**
   ```sql
   -- Check registered players
   SELECT COUNT(*) FROM tournament_players WHERE is_active = true;
   -- Should be > 0
   ```

3. **Player IGN Mismatch**
   - Registered IGN doesn't match PUBG name exactly
   - Case-sensitive!

4. **Date Filter**
   - Service only finds matches from Oct 13, 2025 onwards
   - Older matches are ignored

**Debug**:
Set `LOG_LEVEL=DEBUG` in Komodo environment variables and check logs:
```
DEBUG - Skipping match XYZ: type='official', mode='squad-fpp' (not custom esports-squad-fpp)
DEBUG - Skipping match ABC: date='2025-10-10' (not after Oct 13, 2025)
```

---

## 🔄 Updating the Service

### To Update Service Code

1. Make changes to `tournament_match_discovery.py`
2. Rebuild Docker image
3. Push to registry
4. In Komodo: Update stack (pulls latest image)
5. Service restarts automatically

### To Change Configuration

1. Edit `compose.yaml` (command, env vars, resources, etc.)
2. Commit changes
3. In Komodo: Update stack configuration
4. Redeploy stack

### To Change Filters (Date/Match Type)

Edit `/src/pewstats_collectors/services/tournament_match_discovery.py`:

```python
# Line 280: Change cutoff date
cutoff_date = datetime(2025, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

# Line 289: Change match filters
if match_type == "custom" and game_mode == "esports-squad-fpp":
```

Then rebuild image and redeploy.

---

## 📋 Deployment Checklist

Pre-deployment:
- [ ] Database migration applied (`001_create_tournament_tables.sql`)
- [ ] Teams populated in `teams` table
- [ ] Players populated in `tournament_players` table
- [ ] Docker image built with tournament code
- [ ] Image pushed to registry (ghcr.io)

Deployment:
- [ ] `compose.yaml` updated with `tournament-discovery` service
- [ ] Environment variables verified in Komodo
- [ ] Stack deployed/updated in Komodo
- [ ] Container shows "Running" status

Verification:
- [ ] Logs show "Starting tournament match discovery pipeline"
- [ ] No error messages in logs
- [ ] Service samples players (check logs)
- [ ] Matches being stored (check database)
- [ ] Service restarts automatically on failure

---

## 📊 Expected Performance

### Resource Usage
- **CPU**: ~5-10% during discovery, ~0% idle
- **Memory**: 100-200MB typical, 512MB max
- **Network**: Minimal (PUBG API calls every 60s)
- **Disk**: Negligible (only database writes)

### Discovery Rate
- **Checks**: Every 60 seconds
- **API Calls**: ~1-2 per check (for 9 players)
- **Matches**: 0-10+ per check (depends on tournament activity)
- **Latency**: 1-2 minutes from match completion to discovery

---

## 🎯 Success Criteria

The deployment is successful when:

1. ✅ Service container is "Running" in Komodo
2. ✅ Logs show regular discovery cycles (every 60s)
3. ✅ No error messages or restart loops
4. ✅ Matches are being stored in `tournament_matches` table
5. ✅ Players are being matched to teams (`team_id` not null)
6. ✅ Service auto-restarts on failure

---

## 🆘 Support

- **Service Code**: `/src/pewstats_collectors/services/tournament_match_discovery.py`
- **Database Schema**: `/migrations/001_create_tournament_tables.sql`
- **Documentation**: `/docs/TOURNAMENT_SYSTEM.md`
- **Logs**: Komodo dashboard → Containers → tournament-discovery → Logs

---

## 🔗 Related Documentation

- [Tournament System Overview](TOURNAMENT_SYSTEM.md)
- [Quick Start Guide](TOURNAMENT_QUICKSTART.md)
- [Implementation Status](TOURNAMENT_STATUS.md)
- [Data Population Template](tournament_data_template.sql)

---

**Next Step**: Rebuild your Docker image, push to registry, and deploy the stack in Komodo! 🚀
