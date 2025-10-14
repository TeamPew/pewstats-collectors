# Tournament System - Quick Start Guide

## 🎯 Current Status

✅ **Database migration applied** - Tables created and ready
⚠️ **Awaiting data** - Need to populate teams and players
📚 **Full documentation** - See [TOURNAMENT_SYSTEM.md](TOURNAMENT_SYSTEM.md)

---

## 🚀 Quick Start (5 Steps)

### Step 1: Populate Teams (5-10 minutes)

1. Copy the template: `docs/tournament_data_template.sql`
2. Replace example teams with your tournament roster
3. Set `division` and `group_name` to define lobbies (max 16 teams/lobby)
4. Run the SQL:

```bash
psql -h localhost -U pewstats_prod_user -d pewstats_production -f tournament_data_template.sql
```

**Example**:
```sql
INSERT INTO teams (team_name, division, group_name, team_number, is_active) VALUES
('Team Liquid', 'Division 1', 'Group A', 101, true),
('FaZe Clan', 'Division 1', 'Group A', 102, true);
```

---

### Step 2: Populate Players (10-20 minutes)

⚠️ **CRITICAL**: Player IGNs must match PUBG names **exactly** (case-sensitive!)

1. Get team IDs:
```sql
SELECT id, team_name FROM teams ORDER BY team_name;
```

2. Add 4+ players per team:
```sql
INSERT INTO tournament_players (player_id, team_id, preferred_team, is_primary_sample, sample_priority, is_active) VALUES
('ExactPUBGName1', 1, true, true, 1, true),  -- Primary sample
('ExactPUBGName2', 1, true, true, 2, true),  -- Primary sample
('ExactPUBGName3', 1, true, false, 3, true), -- Backup
('ExactPUBGName4', 1, true, false, 4, true); -- Backup
```

**Tips**:
- Set `is_primary_sample=true` for 1-2 players per team (these will be queried)
- Set `sample_priority`: 1=highest, 2=second, etc.
- Aim for 6-12 primary samples per lobby (division+group)

---

### Step 3: Verify Data (2 minutes)

```sql
-- Check team counts per lobby
SELECT division, group_name, COUNT(*) as teams
FROM teams WHERE is_active = true
GROUP BY division, group_name;

-- Check sampling distribution
SELECT t.division, t.group_name,
       COUNT(*) FILTER (WHERE tp.is_primary_sample = true) as primary_samples
FROM teams t
JOIN tournament_players tp ON t.id = tp.team_id
WHERE t.is_active = true AND tp.is_active = true AND tp.preferred_team = true
GROUP BY t.division, t.group_name;

-- List all sampled players
SELECT tp.player_id, t.team_name, tp.sample_priority
FROM tournament_players tp
JOIN teams t ON tp.team_id = t.id
WHERE tp.is_primary_sample = true AND tp.is_active = true
ORDER BY t.division, t.group_name, tp.sample_priority;
```

**Expected**:
- ✅ 6-12 primary samples per lobby
- ✅ 1-2 primary samples per team
- ✅ All player IGNs look correct (no typos!)

---

### Step 4: Test Discovery (5 minutes)

Run a single discovery cycle:

```bash
cd /opt/pewstats-platform/services/pewstats-collectors

python -m pewstats_collectors.services.tournament_match_discovery \
    --log-level DEBUG \
    --sample-size 6 \
    --match-type "competitive,official,custom"
```

**What to expect**:
- If tournament is active: Should discover matches within 1-2 minutes
- If no active matches: Will show "No new matches found" (normal!)

Check if matches were discovered:
```sql
SELECT COUNT(*) as match_count, MAX(match_datetime) as latest_match
FROM tournament_matches;
```

---

### Step 5: Run Continuously (Production)

#### Option A: Command Line (Testing)

```bash
python -m pewstats_collectors.services.tournament_match_discovery \
    --continuous \
    --interval 60 \
    --sample-size 6 \
    --match-type competitive \
    --schedule-enabled \
    --schedule-days "0,1,2,3,6" \
    --schedule-start "18:00" \
    --schedule-end "00:00"
```

#### Option B: Systemd Service (Production)

1. Create `/etc/systemd/system/tournament-discovery.service`:

```ini
[Unit]
Description=PewStats Tournament Match Discovery
After=network.target postgresql.service

[Service]
Type=simple
User=pewstats
WorkingDirectory=/opt/pewstats-platform/services/pewstats-collectors
Environment="PYTHONPATH=/opt/pewstats-platform/services/pewstats-collectors/src"
ExecStart=/usr/bin/python3 -m pewstats_collectors.services.tournament_match_discovery \
    --continuous \
    --interval 60 \
    --sample-size 6 \
    --match-type competitive \
    --schedule-enabled \
    --schedule-days "0,1,2,3,6" \
    --schedule-start "18:00" \
    --schedule-end "00:00"
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

2. Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable tournament-discovery
sudo systemctl start tournament-discovery
sudo systemctl status tournament-discovery
```

3. View logs:

```bash
sudo journalctl -u tournament-discovery -f
```

---

## 📊 Query Tournament Data

### Recent Matches

```sql
SELECT match_id, match_datetime, map_name,
       COUNT(*) as participants
FROM tournament_matches
WHERE match_datetime > NOW() - INTERVAL '24 hours'
GROUP BY match_id, match_datetime, map_name
ORDER BY match_datetime DESC;
```

### Team Performance

```sql
SELECT t.team_name,
       COUNT(DISTINCT tm.match_id) as matches,
       AVG(tm.team_rank) as avg_placement,
       SUM(tm.kills) as total_kills
FROM teams t
JOIN tournament_matches tm ON t.id = tm.team_id
WHERE tm.match_datetime > NOW() - INTERVAL '24 hours'
GROUP BY t.team_name
ORDER BY avg_placement;
```

### Top Players

```sql
SELECT player_name,
       SUM(kills) as kills,
       SUM(damage_dealt) as damage,
       COUNT(*) as matches
FROM tournament_matches
WHERE match_datetime > NOW() - INTERVAL '24 hours'
GROUP BY player_name
ORDER BY kills DESC
LIMIT 10;
```

---

## 🔧 Troubleshooting

### No Matches Found

**Check if tournament is active**:
```sql
SELECT COUNT(*) FROM tournament_players WHERE is_primary_sample = true AND is_active = true;
```

**Try broader match type filter**:
```bash
--match-type "competitive,official,custom,esports"
```

**Check player IGNs are exact**:
- Log into PUBG and verify spelling
- Case-sensitive! "PlayerName" ≠ "playername"

### Players Not Matched to Teams

**Find unmatched players**:
```sql
SELECT DISTINCT player_name
FROM tournament_matches
WHERE team_id IS NULL
  AND match_datetime > NOW() - INTERVAL '24 hours';
```

**Fix IGN mismatch**:
```sql
UPDATE tournament_players
SET player_id = 'CorrectIGN'
WHERE player_id = 'WrongIGN';
```

### Rate Limiting

Add more API keys:
```bash
# In .env
PUBG_API_KEYS=key1,key2,key3,key4
```

---

## 📚 Full Documentation

- **Complete Guide**: [TOURNAMENT_SYSTEM.md](TOURNAMENT_SYSTEM.md)
- **Data Template**: [tournament_data_template.sql](tournament_data_template.sql)
- **Service Code**: [tournament_match_discovery.py](../src/pewstats_collectors/services/tournament_match_discovery.py)
- **Database Schema**: [001_create_tournament_tables.sql](../migrations/001_create_tournament_tables.sql)

---

## ✅ Checklist

- [x] Database migration applied
- [ ] Teams populated
- [ ] Players populated (IGNs verified!)
- [ ] Data verified (6-12 samples per lobby)
- [ ] Test run successful
- [ ] Service running continuously
- [ ] Scheduling configured (if needed)
- [ ] Monitoring set up (logs/metrics)

---

## 📞 Support

- File issues: GitHub Issues
- Documentation: `/docs/TOURNAMENT_SYSTEM.md`
- Questions: Check full documentation first!

---

**Last Updated**: 2025-10-14
**Status**: Ready for data population
