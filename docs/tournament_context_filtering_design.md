# Tournament Context-Aware Filtering Design

## Overview

This document discusses the implementation approach for making **all tournament statistics context-aware** based on the selected division, group, round, and match filters.

**Current State**: Tournament page has filter controls (Division/Group, Round, Match) but most stats are currently placeholder data.

**Target State**: All stats (team standings, player stats, matches, schedule) should dynamically filter based on user selections.

---

## Filter Hierarchy

### Filter Controls

1. **Division & Group** (Combined dropdown)
   - Options: "Division 1", "Division 2A", "Division 2B", etc.
   - Affects: ALL tabs and ALL stats

2. **Round** (Dropdown)
   - Options: "Overall" (all rounds), "Round 1", "Round 2", etc.
   - Affects: ALL tabs except Schedule (which lists rounds)

3. **Match** (Dropdown) - **Context-dependent**
   - Options: "Overall" (all matches in selected round), "Match 1", "Match 2", etc.
   - Only enabled when a specific round is selected (disabled when Round = "Overall")
   - Affects: ALL stats in Standings, Players, Matches tabs

---

## Filter Combinations & Expected Behavior

### Examples

| Division/Group | Round | Match | Expected Behavior |
|----------------|-------|-------|-------------------|
| **Division 1** | **Overall** | **Overall** (disabled) | Show all data for Division 1 across all rounds |
| **Division 1** | **Round 3** | **Overall** | Show all data for Division 1 in Round 3 (all matches) |
| **Division 1** | **Round 3** | **Match 2** | Show only data for Division 1, Round 3, Match 2 |
| **Division 2A** | **Overall** | **Overall** (disabled) | Show all data for Division 2, Group A across all rounds |

### UI Behavior

- When **Round = "Overall"**: Hide or disable the Match dropdown
- When **Round = specific round**: Enable Match dropdown with "Overall" + individual matches for that round
- Division/Group filter is always active and applies to all data

---

## Implementation Approaches

### Approach 1: Backend Filtering (Recommended)

**Concept**: Pass filter parameters to API endpoints and filter data in SQL queries.

**Pros**:
- Most performant (only fetch needed data)
- Reduces network payload
- Enables efficient database indexing
- Scales well with large datasets

**Cons**:
- Requires API endpoint updates
- More complex backend logic

**Implementation**:

#### API Query Parameters

All tournament endpoints accept these optional filters:

```
GET /api/v1/tournaments/{tournament_id}/seasons/{season_id}/teams/leaderboard
  ?division=Division 1
  &group=A
  &round_id=15
  &match_id=abc123
```

#### SQL Filter Logic

```sql
-- Example: Team leaderboard with context-aware filtering
SELECT
    t.id as team_id,
    t.team_name,
    t.division,
    t.group_name,
    COUNT(DISTINCT tmp.match_id) as matches_played,
    SUM(tmp.kills) as total_kills,
    SUM(tmp.damage) as total_damage,
    ...
FROM teams t
INNER JOIN tournament_match_participants tmp ON t.id = tmp.team_id
INNER JOIN tournament_matches tm ON tmp.match_id = tm.match_id
WHERE tm.season_id = :season_id
  AND (:division IS NULL OR t.division = :division)
  AND (:group IS NULL OR t.group_name = :group)
  AND (:round_id IS NULL OR tm.round_id = :round_id)
  AND (:match_id IS NULL OR tm.match_id = :match_id)
GROUP BY t.id, t.team_name, t.division, t.group_name
ORDER BY total_score DESC
```

#### Filter Cascading

- `division` filter: Always applied
- `group` filter: Applied if group is not null (Division 1 has no groups)
- `round_id` filter: Applied when specific round selected
- `match_id` filter: Applied when specific match selected (overrides round_id)

#### Frontend Implementation

```typescript
// TournamentClient.tsx
const fetchTeamStandings = async () => {
  const params = new URLSearchParams({
    division: selectedDivision,
    ...(selectedGroup && { group: selectedGroup }),
    ...(selectedRound !== 'Overall' && { round_id: selectedRoundId }),
    ...(selectedMatch !== 'Overall' && { match_id: selectedMatchId }),
  })

  const response = await fetch(
    `/api/v1/tournaments/1/seasons/1/teams/leaderboard?${params}`
  )
  return response.json()
}
```

---

### Approach 2: Client-Side Filtering

**Concept**: Fetch all data once and filter in the frontend.

**Pros**:
- Simpler backend (no changes needed)
- Instant filter changes (no network requests)
- Good for prototyping

**Cons**:
- Large initial payload (all tournament data)
- Memory intensive for client
- Slower initial load
- Not scalable for large tournaments

**Implementation**:

```typescript
// TournamentClient.tsx
const filteredTeamStandings = useMemo(() => {
  return teamStandings.filter(team => {
    // Division/Group filter
    if (team.division !== selectedDivision) return false
    if (selectedGroup && team.group_name !== selectedGroup) return false

    // Round filter (if not "Overall")
    if (selectedRound !== 'Overall') {
      // Filter team's matches to only include selected round
      // Recalculate stats based on filtered matches
    }

    // Match filter (if not "Overall")
    if (selectedMatch !== 'Overall') {
      // Filter team's matches to only include selected match
      // Recalculate stats based on single match
    }

    return true
  })
}, [teamStandings, selectedDivision, selectedGroup, selectedRound, selectedMatch])
```

**Challenge**: Recalculating aggregates (total kills, damage, rank) client-side is complex and error-prone.

---

### Approach 3: Hybrid Approach

**Concept**: Backend filtering for expensive queries, client-side filtering for simple lists.

**Pros**:
- Balance between performance and simplicity
- Can optimize per-tab

**Cons**:
- Mixed complexity
- Harder to maintain consistency

**Implementation**:

- **Standings Tab**: Backend filtering (complex aggregations)
- **Players Tab**: Backend filtering (complex aggregations)
- **Matches Tab**: Client-side filtering (simple list filtering)
- **Schedule Tab**: Client-side filtering (static list)

---

## Recommended Implementation Strategy

### Phase 1: Backend Filtering Foundation

1. **Update all API endpoints** to accept filter parameters:
   - `division` (required)
   - `group` (optional)
   - `round_id` (optional)
   - `match_id` (optional)

2. **Implement SQL filtering** in all queries:
   - Team leaderboard
   - Player stats
   - Match listings
   - Fight win percentages (join with tournament_matches)

3. **Add indexes** for performance:
   ```sql
   CREATE INDEX idx_tournament_matches_season_round ON tournament_matches(season_id, round_id);
   CREATE INDEX idx_tournament_matches_season_match ON tournament_matches(season_id, match_id);
   CREATE INDEX idx_teams_division_group ON teams(division, group_name);
   ```

### Phase 2: Frontend State Management

1. **Track filter state** in TournamentClient:
   ```typescript
   const [selectedDivision, setSelectedDivision] = useState<string>('Division 1')
   const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
   const [selectedRound, setSelectedRound] = useState<string>('Overall')
   const [selectedRoundId, setSelectedRoundId] = useState<number | null>(null)
   const [selectedMatch, setSelectedMatch] = useState<string>('Overall')
   const [selectedMatchId, setSelectedMatchId] = useState<string | null>(null)
   ```

2. **Fetch data on filter change**:
   ```typescript
   useEffect(() => {
     fetchTeamStandings()
     fetchPlayerStats()
     // etc.
   }, [selectedDivision, selectedGroup, selectedRoundId, selectedMatchId])
   ```

3. **Disable Match dropdown** when Round = "Overall":
   ```typescript
   const isMatchDropdownDisabled = selectedRound === 'Overall'
   ```

### Phase 3: Context-Aware Components

Each tab's data fetching should respect the current filter context:

#### Standings Tab
```typescript
const { data: teamStandings, isLoading } = useQuery({
  queryKey: ['teamStandings', selectedDivision, selectedGroup, selectedRoundId, selectedMatchId],
  queryFn: () => fetchTeamStandings({
    division: selectedDivision,
    group: selectedGroup,
    round_id: selectedRoundId,
    match_id: selectedMatchId,
  })
})
```

#### Players Tab
```typescript
const { data: playerStats, isLoading } = useQuery({
  queryKey: ['playerStats', selectedDivision, selectedGroup, selectedRoundId, selectedMatchId],
  queryFn: () => fetchPlayerStats({
    division: selectedDivision,
    group: selectedGroup,
    round_id: selectedRoundId,
    match_id: selectedMatchId,
  })
})
```

---

## Special Cases & Edge Cases

### 1. Match Placements Sparkline

**Context-aware logic**:
- **Overall / Overall**: Last 6 matches across all rounds
- **Round X / Overall**: All matches in Round X (max 6)
- **Round X / Match Y**: Single data point (that match)

**Implementation**:
```typescript
const fetchMatchPlacements = (teamId: number) => {
  if (selectedRound === 'Overall') {
    // Last 6 matches across all rounds
    return fetch(`/api/v1/teams/${teamId}/placements?limit=6`)
  } else if (selectedMatch === 'Overall') {
    // All matches in selected round
    return fetch(`/api/v1/teams/${teamId}/placements?round_id=${selectedRoundId}`)
  } else {
    // Single match
    return fetch(`/api/v1/teams/${teamId}/placements?match_id=${selectedMatchId}`)
  }
}
```

### 2. Rank Change

**Only show when**: Round = "Overall" AND Match = "Overall"

**Implementation**:
```typescript
const shouldShowRankChange = selectedRound === 'Overall' && selectedMatch === 'Overall'

// In component
{shouldShowRankChange && (
  <div className="rank-change">
    {team.rank_change > 0 ? '↑' : '↓'} {Math.abs(team.rank_change)}
  </div>
)}
```

### 3. Fight Win Percentage

**Challenge**: Fight data in `team_fights` table is not directly linked to rounds/matches.

**Solution**: Join via `tournament_matches`:
```sql
SELECT
    team_id,
    COUNT(*) as fights_entered,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'WON' THEN 1 ELSE 0 END) / COUNT(*), 2) as win_rate_pct
FROM (
    SELECT
        unnest(tf.team_ids) as team_id,
        (tf.team_outcomes->>unnest(tf.team_ids)::text) as outcome
    FROM team_fights tf
    INNER JOIN tournament_matches tm ON tf.match_id = tm.match_id
    WHERE tm.season_id = :season_id
      AND (:round_id IS NULL OR tm.round_id = :round_id)
      AND (:match_id IS NULL OR tm.match_id = :match_id)
) fight_data
GROUP BY team_id
```

### 4. Schedule Tab

**Special case**: Schedule tab lists rounds, so it should:
- Filter by division/group (show only rounds for selected division)
- Ignore round/match filter (since it's displaying rounds themselves)

**Implementation**:
```typescript
const fetchSchedule = () => {
  return fetch(
    `/api/v1/tournaments/1/seasons/1/rounds?division=${selectedDivision}&group=${selectedGroup}`
  )
}
```

---

## Performance Considerations

### 1. Caching Strategy

**Problem**: Repeated API calls when toggling filters.

**Solution**: Use React Query with appropriate cache keys:
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      cacheTime: 10 * 60 * 1000, // 10 minutes
    },
  },
})
```

### 2. Debouncing Filter Changes

**Problem**: Multiple rapid filter changes cause excessive API calls.

**Solution**: Debounce filter state updates:
```typescript
const debouncedFilters = useDebounce({
  division: selectedDivision,
  group: selectedGroup,
  round_id: selectedRoundId,
  match_id: selectedMatchId,
}, 300) // 300ms delay
```

### 3. Prefetching Common Filters

**Problem**: Slow response when switching filters.

**Solution**: Prefetch likely next filters:
```typescript
// When user hovers over Round 3, prefetch data for Round 3
const prefetchRound = (roundId: number) => {
  queryClient.prefetchQuery({
    queryKey: ['teamStandings', selectedDivision, selectedGroup, roundId, null],
    queryFn: () => fetchTeamStandings({ round_id: roundId })
  })
}
```

### 4. Database Query Optimization

**Indexes needed**:
```sql
-- Tournament matches filtering
CREATE INDEX idx_tm_season_round ON tournament_matches(season_id, round_id);
CREATE INDEX idx_tm_season_match ON tournament_matches(season_id, match_id);

-- Teams filtering
CREATE INDEX idx_teams_division_group ON teams(division, group_name);

-- Participants filtering
CREATE INDEX idx_tmp_match_team ON tournament_match_participants(match_id, team_id);
CREATE INDEX idx_tmp_match_player ON tournament_match_participants(match_id, player_name);
```

**Materialized views** (for expensive aggregations):
```sql
-- Pre-aggregate team stats per round
CREATE MATERIALIZED VIEW tournament_team_round_stats AS
SELECT
    tm.season_id,
    tm.round_id,
    t.division,
    t.group_name,
    tmp.team_id,
    COUNT(DISTINCT tmp.match_id) as matches_played,
    SUM(tmp.kills) as total_kills,
    SUM(tmp.damage) as total_damage,
    ...
FROM tournament_match_participants tmp
INNER JOIN teams t ON tmp.team_id = t.id
INNER JOIN tournament_matches tm ON tmp.match_id = tm.match_id
GROUP BY tm.season_id, tm.round_id, t.division, t.group_name, tmp.team_id;

-- Refresh after each match
REFRESH MATERIALIZED VIEW CONCURRENTLY tournament_team_round_stats;
```

---

## API Endpoint Design

### Pattern for All Endpoints

**Base URL**: `/api/v1/tournaments/{tournament_id}/seasons/{season_id}`

**Common Query Parameters**:
- `division` (string, required): e.g., "Division 1"
- `group` (string, optional): e.g., "A" or "B"
- `round_id` (integer, optional): e.g., 15
- `match_id` (string, optional): e.g., "abc123-def456-..."

### Updated Endpoint List

1. **GET /teams/leaderboard**
   - Filters: division, group, round_id, match_id
   - Returns: Team standings with aggregated stats (context-aware)

2. **GET /players/stats**
   - Filters: division, group, round_id, match_id
   - Returns: Player stats aggregated across filtered matches

3. **GET /matches**
   - Filters: division, group, round_id
   - Returns: List of matches matching filters

4. **GET /rounds**
   - Filters: division, group (only)
   - Returns: List of rounds for selected division/group

5. **GET /teams/{team_id}/placements**
   - Filters: round_id OR match_id OR limit (for overall)
   - Returns: Array of placements for sparkline

6. **GET /players/{player_name}/weapons**
   - Filters: division, group, round_id, match_id
   - Returns: Weapon distribution data for radar chart

---

## Testing Strategy

### 1. Unit Tests (Backend)

Test SQL filtering logic with different parameter combinations:
```python
def test_team_leaderboard_overall():
    result = get_team_leaderboard(season_id=1, division='Division 1', group=None, round_id=None)
    assert len(result) > 0

def test_team_leaderboard_specific_round():
    result = get_team_leaderboard(season_id=1, division='Division 1', round_id=15)
    assert all(team['round_id'] == 15 for team in result)

def test_team_leaderboard_specific_match():
    result = get_team_leaderboard(season_id=1, division='Division 1', match_id='abc123')
    assert all(team['match_id'] == 'abc123' for team in result)
```

### 2. Integration Tests (Frontend)

Test filter state management and API calls:
```typescript
describe('Tournament Filters', () => {
  it('should disable match dropdown when round is Overall', () => {
    render(<TournamentClient data={mockData} />)
    const roundSelect = screen.getByLabelText('Round')
    fireEvent.change(roundSelect, { target: { value: 'Overall' } })

    const matchSelect = screen.getByLabelText('Match')
    expect(matchSelect).toBeDisabled()
  })

  it('should fetch filtered data when filters change', async () => {
    const { result } = renderHook(() => useTeamStandings())

    act(() => {
      result.current.setSelectedRound('Round 3')
    })

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('round_id=15')
      )
    })
  })
})
```

### 3. E2E Tests

Test complete user workflows:
```typescript
test('user can filter standings by round and see updated stats', async () => {
  await page.goto('/tournaments')

  // Select Division 1
  await page.selectOption('[data-testid="division-select"]', 'Division 1')

  // Select Round 3
  await page.selectOption('[data-testid="round-select"]', 'Round 3')

  // Verify standings are filtered
  const teams = await page.$$('[data-testid="team-row"]')
  expect(teams.length).toBeGreaterThan(0)

  // Verify stats are recalculated for Round 3 only
  const firstTeamMatches = await page.textContent('[data-testid="team-row"]:first-child [data-testid="matches-played"]')
  expect(parseInt(firstTeamMatches)).toBeLessThanOrEqual(6) // Max 6 matches per round
})
```

---

## Migration Strategy

### Phase 1: MVP (Overall Stats Only)
- Implement division/group filtering
- Implement "Overall" round/match only
- No context-aware filtering yet

### Phase 2: Round Filtering
- Add round_id filtering to API endpoints
- Update SQL queries with round filter
- Enable round dropdown in UI
- Test with specific rounds

### Phase 3: Match Filtering
- Add match_id filtering to API endpoints
- Enable match dropdown in UI (when round is selected)
- Test with specific matches

### Phase 4: Optimization
- Add database indexes
- Implement caching strategy
- Add prefetching
- Consider materialized views for expensive queries

---

## Open Questions

1. **Caching Duration**: How long should we cache tournament data?
   - During active rounds: 1-5 minutes
   - After round completion: 1 hour
   - Historical data: Longer (e.g., 1 day)

2. **Real-time Updates**: Should stats update in real-time during matches?
   - Option A: Polling (every 30 seconds during active matches)
   - Option B: WebSocket updates
   - Option C: Manual refresh only

3. **Filter Persistence**: Should filters persist across page reloads?
   - Use URL query parameters: `/tournaments?division=Division+1&round=3`
   - Or local storage: `localStorage.setItem('tournamentFilters', JSON.stringify(filters))`

4. **Loading States**: How to handle loading during filter changes?
   - Option A: Show loading overlay (blocks interaction)
   - Option B: Show skeleton loaders (preserves layout)
   - Option C: Keep old data visible with "Updating..." indicator

5. **Error Handling**: What if filtered query returns no results?
   - Show "No data available for selected filters"
   - Or auto-reset to "Overall" filters?

---

## Summary

**Recommended Approach**: Backend filtering with React Query caching

**Key Principles**:
1. All stats are context-aware based on active filters
2. Filters cascade: Division → Group → Round → Match
3. Match dropdown disabled when Round = "Overall"
4. Rank change only shown on Overall/Overall view
5. Use SQL-level filtering for performance
6. Cache aggressively with React Query
7. Optimize with database indexes and materialized views

**Next Steps**:
1. Update API endpoints to accept filter parameters
2. Implement SQL filtering in all queries
3. Add database indexes
4. Update frontend to pass filter context to API calls
5. Test with real tournament data
6. Optimize based on performance metrics
