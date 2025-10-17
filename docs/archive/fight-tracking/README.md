# Fight Tracking Documentation Archive

**Archive Date**: October 15, 2025
**Reason**: Consolidated into single comprehensive document

These documents represent the evolution of the Fight Tracking System from initial proposal through production deployment. They have been superseded by the consolidated documentation.

## Current Documentation

**Use these instead**:
- **[FIGHT_TRACKING_COMPLETE.md](../../FIGHT_TRACKING_COMPLETE.md)** - Complete implementation guide (single source of truth)
- **[FIGHT_TRACKING_FINDINGS.md](../../FIGHT_TRACKING_FINDINGS.md)** - Production analysis and statistics

## Archived Documents

### Design & Planning
- **fight-tracking-proposal.md** (Oct 7, 2025)
  - Original design proposal
  - Initial algorithm concepts
  - Business case and use cases

- **investor-pitch-fight-tracking.md** (Oct 10, 2025)
  - Business presentation version
  - Market opportunity analysis
  - Product differentiation

### Implementation Documentation
- **fight-tracking-implementation-summary.md** (Oct 7, 2025)
  - V1 implementation details
  - Initial algorithm (knock-based only)
  - Database schema V1

- **fight-tracking-v2-implementation.md** (Oct 10, 2025)
  - V2 algorithm design
  - Damage-based detection
  - Per-team outcomes
  - Smart execution filtering

### Testing & Analysis
- **fight-tracking-100-matches-analysis.md** (Oct 10, 2025)
  - Initial 100-match test results
  - Algorithm validation
  - Performance metrics

- **fight-tracking-final-100-matches-analysis.md** (Oct 10, 2025)
  - Final testing before production
  - Refined metrics
  - Edge case validation

- **fight-tracking-detailed-tables.md** (Oct 10, 2025)
  - Statistical cross-tabulations
  - Duration vs spread analysis
  - Top 20 most intense fights
  - Percentile distributions

- **fight-tracking-180s-vs-240s-comparison.md** (Oct 10, 2025)
  - Duration threshold tuning
  - Comparison of 180s vs 240s max duration
  - Performance impact analysis

### Bug Fixes & Issues
- **fight-tracking-team-inflation-issue.md** (Oct 10, 2025)
  - Team count inflation bug
  - Analysis of duplicate team detection
  - Fix implementation

- **fight-tracking-npc-fix-summary.md** (Oct 10, 2025)
  - NPC filtering implementation
  - AI bot detection
  - False positive prevention

- **fight-participants-fix-summary.md** (Oct 11, 2025)
  - **Critical bug fix**: Participants not being inserted
  - Foreign key constraint violation
  - Processor restructuring
  - Full backfill success

## Document Evolution Timeline

```
Oct 7, 2025   → Proposal & V1 Implementation
Oct 10, 2025  → V2 Design & Testing (100 matches)
Oct 10, 2025  → Bug fixes (NPC, team inflation)
Oct 10, 2025  → Duration tuning (180s → 240s)
Oct 11, 2025  → Production backfill (36,687 matches)
Oct 11, 2025  → Critical fix (participants foreign key)
Oct 11, 2025  → Full backfill success (5.46M participants)
Oct 15, 2025  → Documentation consolidation
```

## Migration Guide

If you're referencing old documentation:

| Old Document | New Location | Section |
|-------------|--------------|---------|
| fight-tracking-proposal.md | FIGHT_TRACKING_COMPLETE.md | Algorithm Design |
| fight-tracking-v2-implementation.md | FIGHT_TRACKING_COMPLETE.md | Implementation Details |
| fight-tracking-100-matches-analysis.md | FIGHT_TRACKING_FINDINGS.md | All sections |
| fight-participants-fix-summary.md | FIGHT_TRACKING_COMPLETE.md | Implementation Details > Critical Fix |
| All statistical tables | FIGHT_TRACKING_FINDINGS.md | Various sections |

## Why These Were Archived

**Consolidation Benefits**:
1. **Single Source of Truth**: One document with all current information
2. **Reduced Confusion**: No conflicting or outdated information
3. **Easier Maintenance**: Update one file instead of many
4. **Better Discoverability**: Clear document hierarchy
5. **Historical Preservation**: Archive maintains development history

**What's Preserved**:
- All design decisions and rationale
- Algorithm evolution (V1 → V2)
- Bug fixes and their solutions
- Testing results and validation
- Performance characteristics
- Statistical findings

**What's New** (in consolidated docs):
- Production deployment statistics
- Player playstyle analysis
- Comprehensive query examples
- Future enhancement roadmap
- Complete troubleshooting guide
- API integration examples

## Accessing Archived Content

These files remain in the repository for historical reference:

```bash
# View archived documents
ls /opt/pewstats-platform/services/pewstats-collectors/docs/archive/fight-tracking/

# Read specific archived document
cat fight-tracking-proposal.md

# Search across archived documents
grep -r "engagement window" .
```

## Notes

- These documents are **read-only** and should not be updated
- For current information, always refer to consolidated docs
- Some implementation details may be outdated
- Statistical data is from smaller sample sizes (100 matches vs 36,687)
- Bug fixes documented here have been resolved in production

---

**Archive Created**: October 15, 2025
**Archived Documents**: 11 files
**Active Documents**: 2 files (FIGHT_TRACKING_COMPLETE.md, FIGHT_TRACKING_FINDINGS.md)
