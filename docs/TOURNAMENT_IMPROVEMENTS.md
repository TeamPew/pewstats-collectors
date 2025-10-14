# Tournament System Improvements

## Optimization Ideas

### 1. Schedule-Aware Sampling (High Priority)

**Problem:**
Currently the system samples 6 players from ALL divisions/groups every run, regardless of which divisions are scheduled to play today.

**Example:**
- Monday Oct 14: Only Division 2 plays
- Current behavior: Samples 6 players from Div 1, 2, 3A, 3B, 4 = 30 players
- Optimal behavior: Sample only from Division 2 = 6 players

**Benefit:**
- **80% reduction in API calls** on single-division days
- More efficient use of rate limits
- Faster discovery cycles

**Implementation:**
```python
def _get_scheduled_divisions_today(self) -> List[tuple]:
    """Get divisions/groups scheduled to play today.

    Returns:
        List of (division, group_name) tuples scheduled for today
    """
    query = """
    SELECT DISTINCT division, group_name
    FROM tournament_rounds
    WHERE CURRENT_DATE BETWEEN start_date AND end_date
      AND status IN ('scheduled', 'active')
    """
    result = self.database.execute_query(query)
    return [(row['division'], row['group_name']) for row in result]

def _get_tournament_sample_players(self) -> List[str]:
    """Sample players only from divisions scheduled today."""
    scheduled = self._get_scheduled_divisions_today()

    if not scheduled:
        self.logger.info("No divisions scheduled today")
        return []

    query = """
    WITH lobby_samples AS (
        SELECT
            t.division,
            t.group_name,
            tp.player_id,
            tp.sample_priority,
            ROW_NUMBER() OVER (
                PARTITION BY t.division, t.group_name
                ORDER BY tp.sample_priority ASC, tp.id
            ) as sample_rank
        FROM tournament_players tp
        JOIN teams t ON tp.team_id = t.id
        WHERE tp.is_active = true
          AND tp.preferred_team = true
          AND t.is_active = true
          AND (t.division, t.group_name) IN %s  -- Filter by scheduled divisions
    )
    SELECT player_id
    FROM lobby_samples
    WHERE sample_rank <= %s
    ORDER BY sample_rank
    """

    result = self.database.execute_query(query, (tuple(scheduled), self.current_sample_size))
    return [row["player_id"] for row in result]
```

**Impact Analysis:**
- Oct 13 (3 divisions): 18 players instead of 30 (40% reduction)
- Oct 14 (1 division): 6 players instead of 30 (80% reduction)
- Oct 15 (1 division): 6 players instead of 30 (80% reduction)
- Average reduction: ~60-70% fewer API calls

**Considerations:**
- What if players play matches outside their scheduled time?
- Solution: Could add a "grace period" of ±1 day to catch late/early matches
- Or: Run full sampling during active tournament hours, schedule-aware during off-hours

---

### 2. Match Type Pre-filtering (Medium Priority)

**Problem:**
System fetches match metadata for ALL 1182 matches to check if they're `custom` + `esports-squad-fpp`, even though 99% are ranked matches.

**Current flow:**
1. Get 1182 match IDs from `/players` endpoint
2. Call `/matches/{id}` for each → 1182 API calls
3. Filter by match_type and game_mode
4. Result: 0-18 matches

**Optimization ideas:**
- Cache known non-tournament matches (match IDs we've already checked)
- Use match ID patterns (tournament matches may have predictable patterns)
- Query database first: skip matches already in `matches` table with non-tournament game modes

**Potential implementation:**
```python
def _filter_matches_by_type(self, match_ids: List[str]) -> List[str]:
    """Filter match IDs, skipping known non-tournament matches."""

    # Check database for matches we've already seen
    placeholders = ','.join(['%s'] * len(match_ids))
    query = f"""
    SELECT match_id, game_mode
    FROM matches
    WHERE match_id IN ({placeholders})
    """
    known_matches = self.database.execute_query(query, tuple(match_ids))
    known_map = {row['match_id']: row['game_mode'] for row in known_matches}

    # Skip matches we know aren't tournaments
    unchecked_ids = [
        mid for mid in match_ids
        if mid not in known_map or known_map[mid] == 'esports-squad-fpp'
    ]

    self.logger.info(
        f"Skipped {len(match_ids) - len(unchecked_ids)} known non-tournament matches"
    )

    # Only fetch metadata for unchecked matches
    filtered = []
    for match_id in unchecked_ids:
        # ... existing filtering logic

    return filtered
```

**Impact:**
- First run: Still checks all matches
- Subsequent runs: Skips 95%+ of matches
- Could reduce from 1182 API calls to ~10-50 calls

---

### 3. Adaptive Schedule Checking (Low Priority)

**Problem:**
System checks schedule every 60 seconds, even when it knows the next round is hours/days away.

**Optimization:**
- When outside schedule, sleep until next scheduled round
- Use `time_until_next_active()` to calculate exact wait time
- Wake up 5 minutes before round starts to prepare

**Example:**
```python
if not schedule.is_active():
    wait_seconds = schedule.time_until_next_active()

    if wait_seconds > 3600:  # More than 1 hour
        # Sleep until 5 minutes before next round
        sleep_time = wait_seconds - 300
        logger.info(f"No rounds scheduled soon. Sleeping {sleep_time}s until next round")
        time.sleep(sleep_time)
    else:
        # Normal interval
        time.sleep(interval)
```

**Impact:**
- Reduced resource usage during off-hours
- Fewer database queries
- Still ready 5 minutes before tournaments

---

## Performance Metrics

### Current Performance
- API calls per cycle: ~30 players = 3 requests/min
- Match metadata checks: 1182 per cycle (worst case)
- Total API load: ~3-10 requests/min during tournaments

### After Optimizations
- API calls per cycle: ~6 players = 0.6 requests/min (schedule-aware)
- Match metadata checks: ~10-50 per cycle (with caching)
- Total API load: ~1-2 requests/min during tournaments

**Estimated savings: 80-90% reduction in API usage**

---

## Priority Ranking

1. **Schedule-Aware Sampling** - Highest impact, straightforward implementation
2. **Match Type Pre-filtering** - Significant impact, moderate complexity
3. **Adaptive Schedule Checking** - Nice to have, minimal impact

---

## Notes

These optimizations become more valuable as:
- Tournament grows (more divisions = more non-playing days)
- Players play more casual matches between tournaments
- Rate limits become tighter

For the current 5-division tournament, **Schedule-Aware Sampling** alone would provide the best ROI.
