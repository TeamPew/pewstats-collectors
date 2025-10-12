# Comprehensive Player Profile Page - Design Document

## Overview

A unified player profile page that integrates **all existing and planned metrics** into a cohesive, actionable dashboard for PUBG competitive players. This design combines:

- **Existing damage/weapon stats** (player_damage_stats, player_aggregates)
- **Finishing metrics** (player_finishing_summary, player_knock_events)
- **Fight tracking data** (team_fights, fight_participants) - from V2 implementation
- **Mobility metrics** (proposed - from mobility-metrics-proposal.md)
- **Playstyle classification** and **actionable insights**

---

## Page Structure

### Navigation & Layout

```
┌─────────────────────────────────────────────────────────────┐
│  [PewStats Logo]    Players    Matches    Teams    Stats    │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Search: [______________________] 🔍                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Player: BRULLEd                   [Time: 30d ▼]     │  │
│  │  Last Active: 2 hours ago          [Mode: All ▼]     │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  [Overview] [Combat] [Finishing] [Mobility] [Weapons]       │
│                                                              │
│  ┌────────────────────  Content Area  ─────────────────┐   │
│  │                                                       │   │
│  │  (Tab content dynamically loads here)                │   │
│  │                                                       │   │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Tab 1: Overview Dashboard

**Purpose**: High-level performance snapshot with key metrics and playstyle classification

### Section A: Hero Stats Grid (4 Cards)

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ 🎯 2.45 K/D │ 💪 287 ADR  │ 🏆 15.3% WR │ ⚔️ 65% Fight│
│   612 Kills │  374 Matches│   57 Wins   │   Win Rate  │
│   ▲ 12%     │   ▼ 3%      │   ▲ 5%      │   ▲ 8%      │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

**Metrics**:
- **K/D Ratio**: `player_aggregates.kd_ratio`
- **ADR**: `player_aggregates.adr`
- **Win Rate**: `player_aggregates.win_rate`
- **Fight Win Rate**: From `fight_participants` (NEW - requires aggregation)

**Trend Indicators**: Compare to previous 30-day period

---

### Section B: Playstyle Classification Card

**Purpose**: Identify player's dominant combat style using multi-dimensional analysis

```
┌─────────────────────────────────────────────────────────┐
│  YOUR PLAYSTYLE: Aggressive Flanker                     │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Icon: Running figure]                                 │
│                                                          │
│  ✓ High mobility in fights (4.2 m/s)                    │
│  ✓ Aggressive positioning (avg 35m from teammates)      │
│  ✓ Strong finishing rate (65.2%)                        │
│  ⚠ Higher risk profile (58% survival in fights)         │
│                                                          │
│  Similar players: PlayerX, PlayerY, PlayerZ             │
│  Team role: Entry fragger / Flanker                     │
└─────────────────────────────────────────────────────────┘
```

**Classification Algorithm**:

```python
def classify_playstyle(player_stats):
    """
    Multi-dimensional playstyle classification
    """

    # Dimension 1: Combat Aggression
    combat_score = (
        player_stats.finishing_rate * 0.4 +
        player_stats.fight_win_rate * 0.4 +
        player_stats.early_game_kills_pct * 0.2
    )

    # Dimension 2: Mobility
    if player_stats.mobility_rate > 4.0:
        mobility = "High"
    elif player_stats.mobility_rate > 2.5:
        mobility = "Moderate"
    else:
        mobility = "Low"

    # Dimension 3: Positioning
    if player_stats.avg_teammate_distance > 50:
        positioning = "Isolated"
    elif player_stats.avg_teammate_distance > 25:
        positioning = "Flanking"
    else:
        positioning = "Stacked"

    # Dimension 4: Range Preference
    dominant_range = max(
        ("CQC", player_stats.knocks_cqc_pct),
        ("Mid", player_stats.knocks_close_pct),
        ("Long", player_stats.knocks_long_pct),
        key=lambda x: x[1]
    )[0]

    # Classification Matrix
    playstyles = {
        ("High", "Flanking", "CQC"): "Aggressive Flanker",
        ("High", "Stacked", "CQC"): "Entry Fragger",
        ("Moderate", "Flanking", "Mid"): "Rotator",
        ("Low", "Stacked", "Mid"): "Anchor",
        ("Low", "Isolated", "Long"): "Sniper",
        ("High", "Isolated", "Long"): "Solo Operator",
        ("Moderate", "Stacked", "Mid"): "Team Player",
        ("Low", "Flanking", "CQC"): "Support",
    }

    key = (mobility, positioning, dominant_range)
    return playstyles.get(key, "Balanced")
```

**Playstyle Archetypes**:

| Playstyle | Characteristics | Team Role |
|-----------|----------------|-----------|
| **Aggressive Flanker** | High mobility, flanking position, strong finishing | Entry/Flanker |
| **Entry Fragger** | High mobility, stacked with team, CQC focused | IGL/Entry |
| **Anchor** | Low mobility, stacked position, defensive | Anchor/Support |
| **Rotator** | Moderate mobility, mid-range, adaptable | Flex |
| **Sniper** | Low mobility, isolated, long-range specialist | DMR/Sniper |
| **Solo Operator** | High mobility, isolated, self-sufficient | Solo/Lurker |
| **Team Player** | Moderate mobility, stacked, balanced | Support |
| **Support** | Low mobility, close to team, assist-focused | Healer/Support |

---

### Section C: Performance Radar Chart

**6-Dimensional Performance Visualization**

```
          Aggression (Fight Win %)
                    ^
                    |
    Mobility ───────●───────── Finishing
                   /│\
                  / | \
                 /  |  \
    Teamplay ───────────────── Accuracy
                    |
                    v
                 Survival
```

**Metrics**:
1. **Aggression**: Fight win rate % (0-100)
2. **Mobility**: Scaled mobility rate (0-100, normalize 0-8 m/s)
3. **Finishing**: Finishing rate % (0-100)
4. **Accuracy**: Headshot kill ratio % (0-100)
5. **Teamplay**: % knocks with teammate within 50m (0-100)
6. **Survival**: Fight survival rate % (0-100)

**Colors**:
- Green zone (75-100): Elite
- Blue zone (50-75): Good
- Yellow zone (25-50): Average
- Red zone (0-25): Needs Work

---

### Section D: Recent Performance Trend

**Line chart showing key metrics over last 10 matches**

```
100% ┤                        ╭─●
 90% ┤                    ●───╯
 80% ┤            ●───●──╯
 70% ┤        ●──╯
 60% ┤    ●──╯
 50% ┤ ●──╯
     └────────────────────────────────
       M1  M2  M3  M4  M5  M6  M7  M8

Legend:
● K/D Ratio   ─ Damage   ◆ Survival Rate
```

**Data Source**: Last 10 matches from `player_aggregates` and `fight_participants`

---

## Tab 2: Combat Performance

**Purpose**: Detailed fight analysis, win rates, and combat patterns

### Section A: Fight Statistics Grid

```
┌─────────────────────────────────────────────────────────┐
│  FIGHT PERFORMANCE (Last 30 Days)                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ Fights       │ Win Rate     │ Survival     │        │
│  │ 142 entered  │ 65.2%        │ 78.9%        │        │
│  │ 374 matches  │ 🟢 Elite     │ 🔵 Good      │        │
│  └──────────────┴──────────────┴──────────────┘        │
│                                                          │
│  ┌──────────────┬──────────────┬──────────────┐        │
│  │ Avg Damage   │ Avg Knocks   │ Avg Kills    │        │
│  │ 287 per fight│ 2.1 per fight│ 1.4 per fight│        │
│  └──────────────┴──────────────┴──────────────┘        │
└─────────────────────────────────────────────────────────┘
```

**Data Sources**:
- `fight_participants.damage_dealt` → avg per fight
- `fight_participants.knocks_dealt` → avg per fight
- `fight_participants.kills_dealt` → avg per fight
- `fight_participants.survived` → survival %
- Fight win rate: calculated from team outcomes

---

### Section B: Fight Outcome Breakdown (Donut Chart)

```
           Fight Outcomes

         ┌─────────────┐
         │    65.2%    │    Fights Won
         │             │    (92)
         │   ●●●●●●    │
         │   ●●●●●●    │    Fights Lost
         │    19.7%    │    (28)
         │             │
         │   Draws     │    Draws
         │    15.1%    │    (22)
         └─────────────┘
```

---

### Section C: Combat Breakdown by Game Phase

```
┌─────────────────────────────────────────────────────────┐
│  PERFORMANCE BY GAME PHASE                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Early Game (0-10 min)                                  │
│  ████████████████ 245 damage/match  42 kills            │
│  Win Rate: 62%   Survival: 68%                          │
│                                                          │
│  Mid Game (10-20 min)                                   │
│  ██████████████████████ 312 damage/match  28 kills      │
│  Win Rate: 71%   Survival: 82%                          │
│                                                          │
│  Late Game (20+ min)                                    │
│  ████████████ 198 damage/match  18 kills                │
│  Win Rate: 58%   Survival: 89%                          │
│                                                          │
│  📊 Peak Performance: Mid-game                          │
│  ⚠️ Opportunity: Late-game fight win rate               │
└─────────────────────────────────────────────────────────┘
```

**Data Sources**:
- `player_aggregates.early_game_damage/kills`
- `player_aggregates.mid_game_damage/kills`
- `player_aggregates.late_game_damage/kills`
- Fight timestamps → classify fights by phase

---

### Section D: Fight Context Analysis

**Bar chart comparing performance in different fight contexts**

```
┌─────────────────────────────────────────────────────────┐
│  WIN RATE BY FIGHT CONTEXT                              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  2v2 Even       ████████████████████ 82% (45 fights)    │
│  3v3 Even       ███████████████ 65% (38 fights)         │
│  4v4 Even       ████████████ 54% (22 fights)            │
│  Outnumbered    ██████ 28% (18 fights)                  │
│  Advantage      ███████████████████████ 91% (19 fights) │
│  Third-Party    ████████ 38% (12 fights)                │
│                                                          │
│  📊 Best: Small even fights (2v2, 3v3)                  │
│  ⚠️ Struggle: Third-party situations                    │
└─────────────────────────────────────────────────────────┘
```

**Implementation Note**: Requires fight context classification (team size imbalance, third-party detection)

---

## Tab 3: Finishing Metrics

**Purpose**: Detailed knock-to-kill conversion analysis (from finishing-metrics-visualization-strategy.md)

### Section A: Finishing Performance Hero Card

```
┌─────────────────────────────────────────────────────────┐
│  FINISHING PERFORMANCE                                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│               65.2%                                      │
│          Finishing Rate                                 │
│           🟢 Elite                                       │
│                                                          │
│    992 Knocks  ·  572 Self-Converted  ·  374 Matches   │
│    Avg Distance: 44.5m  ·  Avg Time: 19.1s             │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

### Section B: Knock Outcome Distribution (Donut Chart)

```
           Knock Outcomes

         ┌─────────────┐
         │   57.7%     │    Self-Converted
         │             │    (572)
         │   ●●●●●●    │
         │   ●●●●●●    │    Teammate Finished
         │   17.2%     │    (171)
         │             │
         │  Enemy      │    Enemy Revived
         │  Revived    │    (210 - 21.2%)
         │   21.2%     │
         └─────────────┘

Insight: 1 in 5 enemies escape - push faster!
```

---

### Section C: Distance Performance Analysis

**Two-part visualization**

#### Part 1: Knock Distribution by Distance (Bar Chart)

```
CQC (0-10m)      ████████████ 249 (25%)
Close (10-50m)   ███████████████████████ 462 (47%)
Medium (50-100m) ███████ 146 (15%)
Long (100-200m)  ████ 87 (9%)
Very Long (200m+) ██ 48 (5%)
```

#### Part 2: Conversion Rate by Distance (Line Chart)

```
100% ┤
 90% ┤                ●
 80% ┤           ●────╯
 70% ┤ ●─●─●────╯
 60% ┤       ╰●──────────●
 50% ┤
     └─────────────────────────────
      CQC  Close  Med  Long  VLong

Insight: Spike at 100-200m suggests good long-range positioning
```

---

### Section D: Team Coordination Impact

**Horizontal bar chart: Conversion rate by teammate proximity**

```
Isolated (200m+)   ████████████████████ 90.0% (18 knocks)
Distant (100-200m) ████████████████ 77.5% (87 knocks)
Medium (50-100m)   █████████████████ 81.0% (146 knocks)
Close (25-50m)     ████████████████ 76.4% (462 knocks)
Very Close (<25m)  ███████████████ 68.8% (249 knocks)

Insight: Most effective when teammates 25-100m away
         Close support may lead to kill steals!
```

---

### Section E: Contextual Finishing Stats (Table)

```
┌────────────────────┬──────────┬────────────┬────────────┐
│ Context            │ Knocks   │ Conv. Rate │ Avg Time   │
├────────────────────┼──────────┼────────────┼────────────┤
│ With Support       │ 797      │ 73.6%      │ 18.2s      │
│ Isolated Play      │ 18       │ 90.0%      │ 15.4s      │
│ Headshot Knocks    │ 305      │ 78.4%      │ 16.8s      │
│ Wallbang Knocks    │ 8        │ 62.5%      │ 21.3s      │
│ Vehicle Knocks     │ 14       │ 71.4%      │ 19.7s      │
│ Blue Zone Knocks   │ 42       │ 55.2%      │ 25.6s      │
└────────────────────┴──────────┴────────────┴────────────┘
```

---

### Section F: Player Comparison (Side-by-side)

```
                      You      Global Avg    Top 10%
Finishing Rate        65.2%    58.3%         75.8%
Avg Distance          44.5m    38.2m         42.1m
Headshot Knock Rate   30.7%    25.3%         35.2%
Time to Finish        19.1s    15.8s         13.2s
Isolated Success      90.0%    72.4%         88.5%

📊 Strengths: Isolated play, headshot rate
⚠️ Opportunities: Faster time-to-finish
```

---

## Tab 4: Mobility & Positioning

**Purpose**: Movement analysis during fights (from mobility-metrics-proposal.md)

### Section A: Mobility Overview Card

```
┌─────────────────────────────────────────────────────────┐
│  MOBILITY PROFILE                                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Playstyle: Rotator                                     │
│  Mobility Rate: 3.8 m/s (Moderate-High)                 │
│                                                          │
│  Total Movement:    1,245m across 142 fights            │
│  Avg per Fight:     8.8m movement                       │
│  Fight Radius:      35m (Medium spread)                 │
│  Relocations:       3.2 per fight (Active)              │
│                                                          │
│  📊 You rotate actively during fights - good for        │
│     avoiding third-parties and flanking opportunities   │
└─────────────────────────────────────────────────────────┘
```

**Data Sources** (Proposed):
- `fight_participants.total_movement_distance`
- `fight_participants.mobility_rate`
- `fight_participants.fight_radius`
- `fight_participants.significant_relocations`

---

### Section B: Mobility Classification Matrix

**Visual grid showing where player falls**

```
┌─────────────────────────────────────────────────────────┐
│  MOBILITY STYLE MATRIX                                  │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  High     ┌────────────┬────────────┐                   │
│  Mobility │  Flanker   │   Solo     │                   │
│    ↑      │    (5+ m/s)│  Operator  │                   │
│    │      ├────────────┼────────────┤                   │
│    │      │  Rotator ●←│   Anchor   │                   │
│    │      │  (3-5 m/s) │  (2-3 m/s) │                   │
│  Low      ├────────────┼────────────┤                   │
│  Mobility │   Holder   │   Static   │                   │
│           │  (<2 m/s)  │   (<1 m/s) │                   │
│           └────────────┴────────────┘                   │
│              Close          Spread                       │
│           ←─ Team Distance ─→                           │
│                                                          │
│  You: Rotator (3.8 m/s, 35m avg teammate distance)     │
└─────────────────────────────────────────────────────────┘
```

---

### Section C: Movement Patterns (Line Chart)

**Movement distance per fight over time**

```
15m ┤                  ●
12m ┤       ●─●───●───╯  ╲
 9m ┤    ●─╯             ╲●───●
 6m ┤ ●─╯                     ╲●
 3m ┤
 0m └────────────────────────────────
     F1  F3  F5  F7  F9  F11 F13 F15

Trend: Increasing mobility in recent fights
```

---

### Section D: Third-Party Correlation Analysis

```
┌─────────────────────────────────────────────────────────┐
│  MOBILITY vs THIRD-PARTY RATE                           │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Your Stats:                                            │
│  Mobility: 3.8 m/s (Moderate)                           │
│  Third-Party Rate: 22% (28 of 142 fights)               │
│                                                          │
│  Benchmark Comparison:                                  │
│  ┌──────────────┬─────────┬──────────────┐            │
│  │ Mobility     │ Players │ 3rd Party %  │            │
│  ├──────────────┼─────────┼──────────────┤            │
│  │ Static (<2)  │   342   │    35.2%     │            │
│  │ Moderate(2-4)│   587   │●   24.8%     │ ← You     │
│  │ Mobile (4+)  │   198   │    16.3%     │            │
│  └──────────────┴─────────┴──────────────┘            │
│                                                          │
│  📊 Mobile players get third-partied 46% less often     │
│  💡 Tip: Increase relocations to 4+ per fight           │
└─────────────────────────────────────────────────────────┘
```

---

### Section E: Position Heatmap

**2D visualization of where player fights (aggregated position centers)**

```
                    Map: Erangel

           N
           ↑
    ┌──────────────────────────────┐
    │      Georgopol               │
    │         ●●                   │
    │                              │
W ←─┤    Pochinki      ●●●         │─→ E
    │       ●●●●●●                 │
    │                 Mylta        │
    │    School         ●          │
    │      ●●●                     │
    └──────────────────────────────┘
           ↓
           S

Heat intensity = Fight frequency
● Size = Avg damage in that area

Insight: You fight most in Pochinki (hot drop preference)
```

---

## Tab 5: Weapon Mastery

**Purpose**: Deep-dive into weapon performance (enhanced from current page)

### Section A: Weapon Category Radar Charts

**Keep existing dual radar charts (damage + kills)**

```
         [Damage Distribution]      [Kill Distribution]

     AR          SR            AR          SR
       ╲        ╱                ╲        ╱
        ●──────●                  ●──────●
       ╱ ╲    ╱ ╲                ╱ ╲    ╱ ╲
    SMG   ●──●   DMR          SMG   ●──●   DMR
       ╲  │  ╱                    ╲  │  ╱
        ──●──                      ──●──
         LMG                       LMG
```

---

### Section B: Top Weapons Table

**Sortable table with detailed weapon stats**

```
┌─────────────────┬─────────┬───────┬─────────┬──────────┬──────────┐
│ Weapon          │ Damage  │ Kills │ K/D     │ Headshot │ Avg Range│
├─────────────────┼─────────┼───────┼─────────┼──────────┼──────────┤
│ M416            │ 52,480  │  145  │  12.1   │  32.4%   │  45.2m   │
│ AKM             │ 38,920  │   98  │   8.2   │  28.1%   │  38.7m   │
│ Kar98k          │ 24,560  │   42  │  42.0   │  85.7%   │  128.5m  │
│ UMP45           │ 18,340  │   56  │   7.0   │  25.0%   │  22.3m   │
│ M24             │ 16,720  │   28  │  28.0   │  89.3%   │  145.2m  │
└─────────────────┴─────────┴───────┴─────────┴──────────┴──────────┘

🔥 Hot Streak: 8 consecutive kills with M416
⭐ Mastery: Kar98k (Elite tier - 85.7% headshot rate)
```

---

### Section C: Weapon Performance by Range

**Heatmap showing weapon effectiveness at different ranges**

```
┌─────────────────────────────────────────────────────────┐
│  WEAPON EFFECTIVENESS BY RANGE                          │
├─────────────────────────────────────────────────────────┤
│                  CQC   Close   Med   Long   VLong       │
│                  0-10  10-50  50-100 100-200  200+      │
├─────────────────────────────────────────────────────────┤
│  M416            🟩    🟩     🟨     ⬜      ⬜          │
│  AKM             🟩    🟩     🟨     ⬜      ⬜          │
│  Kar98k          ⬜    🟨     🟩     🟩     🟩          │
│  UMP45           🟩    🟨     ⬜     ⬜      ⬜          │
│  M24             ⬜    🟨     🟩     🟩     🟩          │
│  Mini14          ⬜    🟨     🟩     🟩     🟨          │
└─────────────────────────────────────────────────────────┘

🟩 Elite (80%+)  🟨 Good (60-80%)  ⬜ Avg (<60%)
```

---

### Section D: Body Part Accuracy (Keep existing visualization)

**Keep the human silhouette with arrows - it's excellent!**

---

### Section E: Weapon Trends Over Time

**Line chart showing weapon usage evolution**

```
100% ┤
 80% ┤  M416 ●─────────────────●────●
 60% ┤  AKM    ●────●────●───●
 40% ┤  Kar98k   ╰───●────────●─────●
 20% ┤  UMP45 ●───●──╯
  0% └────────────────────────────────
      W1  W2  W3  W4  W5  W6  W7  W8

Trend: Shifting towards long-range (Kar98k)
```

---

## Additional Features

### 1. Time Range Filters (Global)

```
[Last 7d] [Last 30d] [Last 90d] [All Time]
```

Applies to ALL metrics across all tabs

---

### 2. Match Type Filters (Global)

```
[All] [Normal] [Ranked] [Tournament]
```

Allows separate analysis for competitive vs casual play

---

### 3. Map Filters (Global)

```
[All Maps] [Erangel] [Miramar] [Taego] [Vikendi]
```

Map-specific performance analysis

---

### 4. Comparison Mode

**Allow side-by-side player comparisons**

```
┌──────────────────────────────────────────┐
│ Compare with: [Search player...] 🔍      │
└──────────────────────────────────────────┘

                Player A    Player B    Diff
K/D Ratio       2.45        2.12        +0.33 ↑
Finishing %     65.2%       58.7%       +6.5% ↑
Mobility        3.8 m/s     2.4 m/s     +1.4 ↑
Fight Win %     65.2%       71.3%       -6.1% ↓
```

---

### 5. Insights & Recommendations Panel

**AI-generated or rule-based actionable insights**

```
┌─────────────────────────────────────────────────────────┐
│  💡 INSIGHTS & RECOMMENDATIONS                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ✅ STRENGTHS:                                          │
│  • Elite finishing rate (top 15%)                       │
│  • Strong isolated play (90% conversion when alone)     │
│  • Excellent long-range performance (Kar98k mastery)    │
│                                                          │
│  ⚠️ OPPORTUNITIES:                                      │
│  • Time-to-finish is 20% slower than top players        │
│    → Push knocked enemies faster (sub-15s target)       │
│  • Third-party rate above average (22% vs 18%)          │
│    → Increase fight mobility to 4+ m/s                  │
│  • Late-game fight win rate drops to 58%                │
│    → Practice late-game positioning and zone awareness  │
│                                                          │
│  📊 NEXT MILESTONE:                                     │
│  Reach 70% finishing rate (currently 65.2%)             │
│  Progress: ████████████░░░░  85%                        │
│                                                          │
│  🎯 TRAINING FOCUS:                                     │
│  • Drop Training Mode: Practice instant finishes        │
│  • TDM: Work on CQC mobility (currently 68% survival)  │
│  • Ranked: Focus on late-game rotations                 │
└─────────────────────────────────────────────────────────┘
```

---

### 6. Match History Timeline

**Bottom of page: Recent match performance**

```
┌─────────────────────────────────────────────────────────┐
│  RECENT MATCHES                                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  [Match 1] Erangel · Ranked · 2h ago                    │
│  Placement: #3  Kills: 8  Damage: 1,245  Survival: 28m │
│  Fights: 5 (Won: 4, Lost: 1)  Finishing: 87.5%         │
│  ───────────────────────────────────────────────────── │
│  [Match 2] Miramar · Normal · 3h ago                    │
│  Placement: #12  Kills: 4  Damage: 782  Survival: 18m  │
│  Fights: 3 (Won: 2, Lost: 1)  Finishing: 66.7%         │
│  ───────────────────────────────────────────────────── │
│  [Match 3] Taego · Ranked · 5h ago                      │
│  Placement: #1 👑  Kills: 12  Damage: 1,892            │
│  Fights: 7 (Won: 6, Lost: 0, Draw: 1)  Finishing: 91.7%│
│                                                          │
│  [View All Matches →]                                   │
└─────────────────────────────────────────────────────────┘
```

---

## Data Architecture

### Required Database Views/Aggregations

#### 1. Player Combat Stats View

```sql
CREATE OR REPLACE VIEW player_combat_stats AS
SELECT
    fp.player_name,
    COUNT(DISTINCT fp.fight_id) as fights_entered,

    -- Win/Loss/Draw from team outcomes
    SUM(CASE
        WHEN tf.team_outcomes->(fp.team_id::text) = '"WON"' THEN 1
        ELSE 0
    END) as fights_won,

    SUM(CASE
        WHEN tf.team_outcomes->(fp.team_id::text) = '"LOST"' THEN 1
        ELSE 0
    END) as fights_lost,

    -- Performance metrics
    AVG(fp.damage_dealt) as avg_damage_per_fight,
    AVG(fp.knocks_dealt) as avg_knocks_per_fight,
    AVG(fp.kills_dealt) as avg_kills_per_fight,

    -- Survival
    ROUND(100.0 * SUM(CASE WHEN fp.survived THEN 1 ELSE 0 END) / COUNT(*), 1) as survival_rate_pct,

    -- Positioning
    AVG(fp.avg_distance_to_teammates) as avg_teammate_distance,
    AVG(fp.avg_distance_to_enemies) as avg_enemy_distance,

    -- Mobility (if implemented)
    AVG(fp.mobility_rate) as avg_mobility_rate,
    AVG(fp.total_movement_distance) as avg_movement_per_fight,
    AVG(fp.significant_relocations) as avg_relocations_per_fight

FROM fight_participants fp
JOIN team_fights tf ON fp.fight_id = tf.id
GROUP BY fp.player_name;
```

#### 2. Player Finishing Stats View

```sql
CREATE OR REPLACE VIEW player_finishing_aggregates AS
SELECT
    player_name,
    COUNT(DISTINCT match_id) as matches_with_knocks,
    SUM(total_knocks) as total_knocks,
    SUM(knocks_converted_self) as total_self_finishes,
    SUM(knocks_finished_by_teammates) as total_teammate_finishes,
    SUM(knocks_revived_by_enemy) as total_enemy_revives,

    -- Aggregate finishing rate
    ROUND(
        100.0 * SUM(knocks_converted_self) / NULLIF(SUM(total_knocks), 0),
        1
    ) as overall_finishing_rate,

    -- Distance analysis
    AVG(avg_knock_distance) as overall_avg_knock_distance,

    -- Distance buckets
    SUM(knocks_cqc_0_10m) as total_cqc_knocks,
    SUM(knocks_close_10_50m) as total_close_knocks,
    SUM(knocks_medium_50_100m) as total_medium_knocks,
    SUM(knocks_long_100_200m) as total_long_knocks,
    SUM(knocks_very_long_200m_plus) as total_very_long_knocks,

    -- Team coordination
    AVG(avg_nearest_teammate_distance) as avg_teammate_proximity,
    AVG(knocks_with_teammate_within_50m) as avg_knocks_with_support,
    AVG(knocks_isolated_200m_plus) as avg_isolated_knocks,

    -- Special knocks
    SUM(headshot_knock_count) as total_headshot_knocks,
    SUM(wallbang_knock_count) as total_wallbang_knocks,
    SUM(vehicle_knock_count) as total_vehicle_knocks

FROM player_finishing_summary
GROUP BY player_name;
```

#### 3. Player Profile Composite View

```sql
CREATE OR REPLACE VIEW player_comprehensive_profile AS
SELECT
    pa.player_name,

    -- Basic stats
    pa.total_matches,
    pa.total_kills,
    pa.total_deaths,
    pa.kd_ratio,
    pa.adr,
    pa.win_rate,
    pa.headshot_ratio,

    -- Combat stats (from fight tracking)
    pcs.fights_entered,
    pcs.fights_won,
    ROUND(100.0 * pcs.fights_won / NULLIF(pcs.fights_entered, 0), 1) as fight_win_rate,
    pcs.survival_rate_pct as fight_survival_rate,
    pcs.avg_damage_per_fight,
    pcs.avg_knocks_per_fight,

    -- Finishing stats
    pfa.overall_finishing_rate,
    pfa.total_knocks,
    pfa.total_self_finishes,
    pfa.overall_avg_knock_distance,
    pfa.avg_teammate_proximity,

    -- Mobility (if implemented)
    pcs.avg_mobility_rate,
    pcs.avg_movement_per_fight,
    pcs.avg_relocations_per_fight,

    -- Game phase performance
    pa.early_game_kills,
    pa.mid_game_kills,
    pa.late_game_kills,
    ROUND(100.0 * pa.early_game_kills / NULLIF(pa.total_kills, 0), 1) as early_game_kill_pct,

    -- Team metrics
    pa.assists_per_match,
    pa.revives_per_match,
    pa.clutch_success_rate,

    -- Positioning
    pcs.avg_teammate_distance,
    pcs.avg_enemy_distance

FROM player_aggregates pa
LEFT JOIN player_combat_stats pcs ON pa.player_name = pcs.player_name
LEFT JOIN player_finishing_aggregates pfa ON pa.player_name = pfa.player_name;
```

---

## API Endpoints

### Primary Endpoint

```typescript
GET /api/v1/players/{playerName}/profile

Query Parameters:
- timeRange: "7d" | "30d" | "90d" | "all" (default: "30d")
- matchType: "all" | "normal" | "ranked" | "tournament" (default: "all")
- mapName: "all" | "Erangel" | "Miramar" | "Taego" | "Vikendi" (default: "all")

Response:
{
  playerName: string;
  lastActive: string;
  filters: {
    timeRange: string;
    matchType: string;
    mapName: string;
  };

  // Overview stats
  overview: {
    kd: number;
    adr: number;
    winRate: number;
    fightWinRate: number;
    totalMatches: number;
    totalKills: number;
    playstyle: string;
    playstyleDescription: string;
    radarMetrics: {
      aggression: number;
      mobility: number;
      finishing: number;
      accuracy: number;
      teamplay: number;
      survival: number;
    };
  };

  // Combat stats
  combat: {
    fightsEntered: number;
    fightsWon: number;
    fightsLost: number;
    fightsDrawn: number;
    winRate: number;
    survivalRate: number;
    avgDamagePerFight: number;
    avgKnocksPerFight: number;
    avgKillsPerFight: number;
    phaseBreakdown: {
      early: { damage: number; kills: number; winRate: number; };
      mid: { damage: number; kills: number; winRate: number; };
      late: { damage: number; kills: number; winRate: number; };
    };
  };

  // Finishing metrics
  finishing: {
    finishingRate: number;
    totalKnocks: number;
    selfConverted: number;
    teammateFinished: number;
    enemyRevived: number;
    avgKnockDistance: number;
    avgTimeToFinish: number;
    distanceBreakdown: {
      cqc: { knocks: number; conversionRate: number; };
      close: { knocks: number; conversionRate: number; };
      medium: { knocks: number; conversionRate: number; };
      long: { knocks: number; conversionRate: number; };
      veryLong: { knocks: number; conversionRate: number; };
    };
    teammateProximityImpact: Array<{
      range: string;
      knocks: number;
      conversionRate: number;
    }>;
  };

  // Mobility (if implemented)
  mobility: {
    mobilityRate: number;
    avgMovementPerFight: number;
    avgRelocationsPerFight: number;
    fightRadius: number;
    mobilityStyle: string;
    thirdPartyRate: number;
  };

  // Weapon stats
  weapons: {
    categoryStats: {
      damage: Record<string, number>;
      kills: Record<string, number>;
    };
    topWeapons: Array<{
      weaponName: string;
      damage: number;
      kills: number;
      kd: number;
      headshotRate: number;
      avgRange: number;
    }>;
    bodyPartDistribution: {
      headshot: { damage: number; percentage: number; };
      torso: { damage: number; percentage: number; };
      arm: { damage: number; percentage: number; };
      pelvis: { damage: number; percentage: number; };
      leg: { damage: number; percentage: number; };
    };
  };

  // Insights
  insights: {
    strengths: string[];
    opportunities: string[];
    nextMilestone: {
      goal: string;
      current: number;
      target: number;
      progress: number;
    };
    trainingFocus: string[];
  };

  // Recent matches
  recentMatches: Array<{
    matchId: string;
    mapName: string;
    matchType: string;
    timestamp: string;
    placement: number;
    kills: number;
    damage: number;
    survivalTime: number;
    fightsEntered: number;
    fightsWon: number;
    finishingRate: number;
  }>;
}
```

---

## Implementation Phases

### Phase 1: MVP (2-3 weeks)
- ✅ Overview tab (basic stats + playstyle classification)
- ✅ Combat tab (fight performance)
- ✅ Finishing tab (existing metrics visualization)
- ✅ Weapon tab (enhance existing page)
- ✅ Time/match type/map filters

### Phase 2: Mobility & Advanced (2-3 weeks)
- 📋 Implement mobility metrics in fight processing
- 📋 Add Mobility tab
- 📋 Enhanced insights engine
- 📋 Player comparison mode
- 📋 Position heatmaps

### Phase 3: Polish & Features (1-2 weeks)
- 📋 Match history timeline
- 📋 Trend analysis & forecasting
- 📋 Export/share features
- 📋 Mobile optimization
- 📋 Performance optimizations

---

## Technical Stack

**Frontend**:
- React/Next.js (existing)
- Chart.js or Recharts for visualizations
- Tailwind CSS for styling
- React Query for data fetching

**Backend**:
- FastAPI (existing)
- PostgreSQL views for aggregations
- Redis caching for frequently accessed profiles
- Background workers for metrics calculation

**Performance**:
- Cache player profiles for 5 minutes
- Lazy load tabs (only fetch data when tab is clicked)
- Paginate match history
- Use database indexes heavily

---

## Success Metrics

### User Engagement
- Time spent on player profile page
- Tab interaction rates
- Filter usage
- Comparison feature usage

### Performance
- Page load time < 2s
- Tab switch time < 500ms
- API response time < 300ms

### Data Quality
- Playstyle classification accuracy (manual review)
- Insight relevance (user feedback)
- Metric correlation validation

---

## Open Questions

1. **Mobility Implementation**: Priority/timeline for mobility metrics?
2. **Playstyle Algorithm**: Should we use ML or rule-based classification?
3. **Insights Engine**: Auto-generated or manually curated?
4. **Data Retention**: How far back should historical data go?
5. **Real-time Updates**: Should profiles update in real-time or batch?

---

## Conclusion

This comprehensive player profile design:
- ✅ Integrates **all existing metrics** (damage, aggregates, finishing)
- ✅ Incorporates **planned systems** (mobility, fight tracking V2)
- ✅ Provides **actionable insights** for player improvement
- ✅ Supports **multiple playstyles** and use cases
- ✅ Scales to **competitive/tournament** analysis
- ✅ Follows **best practices** from finishing-metrics-visualization-strategy

**Next Step**: Review and approve design, then begin Phase 1 implementation.
