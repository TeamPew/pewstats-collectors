# PewStats Collectors - Documentation Index

**Last Updated**: October 15, 2025

---

## Core System Documentation

### Fight Tracking System 🎯
**Status**: Production Ready (v2.0)

| Document | Purpose | Audience |
|----------|---------|----------|
| **[FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md)** | Complete implementation guide, algorithm design, queries | Developers, Data Analysts |
| **[FIGHT_TRACKING_FINDINGS.md](FIGHT_TRACKING_FINDINGS.md)** | Production statistics, player analysis, insights | Product, Business |

**Archive**: [archive/fight-tracking/](archive/fight-tracking/) - Historical documents (11 files + 2 prototypes)

### Finishing Metrics System 🎖️
**Status**: Production Ready

| Document | Purpose | Audience |
|----------|---------|----------|
| [finishing-metrics-README.md](finishing-metrics-README.md) | Overview and quick start | All |
| [finishing-metrics-implementation.md](finishing-metrics-implementation.md) | Technical implementation details | Developers |
| [finishing-metrics-schema.md](finishing-metrics-schema.md) | Database schema and queries | Data Analysts |
| [finishing-metrics-analysis.md](finishing-metrics-analysis.md) | Statistical analysis and findings | Product |
| [finishing-metrics-strategy.md](finishing-metrics-strategy.md) | Product strategy and roadmap | Product, Business |
| [finishing-metrics-api.md](finishing-metrics-api.md) | API endpoints and usage | API Consumers |
| [finishing-metrics-migration.sql](finishing-metrics-migration.sql) | Database migration script | DevOps |

**Analysis**: [analysis/finishing-metrics-visualization-strategy.md](analysis/finishing-metrics-visualization-strategy.md) - Data viz recommendations

### Player Profiles 👤
**Status**: Design Phase

| Document | Purpose | Audience |
|----------|---------|----------|
| [analysis/comprehensive-player-profile-design.md](analysis/comprehensive-player-profile-design.md) | Complete player profile system design | Product, Developers |

### Mobility Metrics 🚗
**Status**: Analysis Complete

| Document | Purpose | Audience |
|----------|---------|----------|
| [analysis/mobility-metrics-proposal.md](analysis/mobility-metrics-proposal.md) | Mobility system proposal | Product |
| [analysis/mobility-insights-report.md](analysis/mobility-insights-report.md) | Key findings from analysis | Product, Business |
| [analysis/top-20-players-mobility-analysis-CORRECTED.md](analysis/top-20-players-mobility-analysis-CORRECTED.md) | Top player mobility patterns | Data Analysts |

---

## System Architecture

### Database
| Document | Purpose | Audience |
|----------|---------|----------|
| [database-schemas.md](database-schemas.md) | All table schemas | Developers, Data Analysts |
| [database-manager-comparison.md](database-manager-comparison.md) | Python vs R implementation comparison | Developers |
| [damage_events_filtering.md](damage_events_filtering.md) | Damage event processing logic | Developers |

### APIs & Integration
| Document | Purpose | Audience |
|----------|---------|----------|
| [API.md](API.md) | API overview | API Consumers |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture | Developers |

### Operations
| Document | Purpose | Audience |
|----------|---------|----------|
| [API_KEY_SPLIT_GUIDE.md](API_KEY_SPLIT_GUIDE.md) | Multi-key configuration | DevOps |
| [AUTO_POPULATION_GUIDE.md](AUTO_POPULATION_GUIDE.md) | Tournament auto-population | DevOps, Product |
| [FALL_2025_SCHEDULE.md](FALL_2025_SCHEDULE.md) | Tournament scheduling | Operations |
| [fall_2025_schedule.sql](fall_2025_schedule.sql) | Schedule SQL | DevOps |

---

## Documentation by Role

### For Developers

**Getting Started**:
1. [ARCHITECTURE.md](ARCHITECTURE.md) - System overview
2. [database-schemas.md](database-schemas.md) - Data model
3. [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md) - Fight tracking impl

**Implementation Guides**:
- Fight Tracking: [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md)
- Finishing Metrics: [finishing-metrics-implementation.md](finishing-metrics-implementation.md)
- Database Manager: [database-manager-comparison.md](database-manager-comparison.md)

**API Development**:
- [API.md](API.md) - API design
- [finishing-metrics-api.md](finishing-metrics-api.md) - Finishing metrics endpoints

### For Data Analysts

**Query References**:
- Fight queries: [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md#usage--queries)
- Finishing queries: [finishing-metrics-schema.md](finishing-metrics-schema.md)
- Player queries: [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md#player-performance-queries)

**Statistical Analysis**:
- [FIGHT_TRACKING_FINDINGS.md](FIGHT_TRACKING_FINDINGS.md) - Fight statistics
- [finishing-metrics-analysis.md](finishing-metrics-analysis.md) - Finishing statistics
- [analysis/mobility-insights-report.md](analysis/mobility-insights-report.md) - Mobility analysis

**Schemas & Data Models**:
- [database-schemas.md](database-schemas.md) - All tables
- [finishing-metrics-schema.md](finishing-metrics-schema.md) - Finishing metrics tables

### For Product Managers

**Features & Roadmap**:
- Fight Tracking: [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md#future-enhancements)
- Finishing Metrics: [finishing-metrics-strategy.md](finishing-metrics-strategy.md)
- Player Profiles: [analysis/comprehensive-player-profile-design.md](analysis/comprehensive-player-profile-design.md)
- Mobility: [analysis/mobility-metrics-proposal.md](analysis/mobility-metrics-proposal.md)

**Insights & Findings**:
- [FIGHT_TRACKING_FINDINGS.md](FIGHT_TRACKING_FINDINGS.md) - Fight statistics
- [finishing-metrics-analysis.md](finishing-metrics-analysis.md) - Finishing patterns
- [analysis/mobility-insights-report.md](analysis/mobility-insights-report.md) - Mobility insights

**Strategy Documents**:
- [finishing-metrics-strategy.md](finishing-metrics-strategy.md) - Product strategy
- [analysis/finishing-metrics-visualization-strategy.md](analysis/finishing-metrics-visualization-strategy.md) - Viz strategy

### For DevOps

**Deployment & Operations**:
- [API_KEY_SPLIT_GUIDE.md](API_KEY_SPLIT_GUIDE.md) - Key management
- [AUTO_POPULATION_GUIDE.md](AUTO_POPULATION_GUIDE.md) - Tournament setup
- [FALL_2025_SCHEDULE.md](FALL_2025_SCHEDULE.md) - Schedule management

**Migrations**:
- [finishing-metrics-migration.sql](finishing-metrics-migration.sql) - Finishing metrics
- `migrations/004_update_team_fights_for_v2.sql` - Fight tracking v2
- `migrations/005_add_fights_processed_flag.sql` - Processing flag

### For Business / Executives

**High-Level Overviews**:
- [FIGHT_TRACKING_FINDINGS.md](FIGHT_TRACKING_FINDINGS.md) - Fight tracking ROI
- [finishing-metrics-strategy.md](finishing-metrics-strategy.md) - Product strategy
- [archive/fight-tracking/investor-pitch-fight-tracking.md](archive/fight-tracking/investor-pitch-fight-tracking.md) - Business case (archived)

**Key Metrics**:
- Fight tracking: 824K fights, 5.46M participants, 96.4% coverage
- Finishing metrics: Player skill differentiation, training insights
- Mobility: Movement pattern analysis, positional play

---

## Document Status Legend

| Symbol | Status | Description |
|--------|--------|-------------|
| ✅ | Production | Live in production, actively used |
| 🚧 | In Development | Being actively developed |
| 📋 | Design | Design phase, not yet implemented |
| 📦 | Archived | Historical reference only |
| 🔄 | Deprecated | Being replaced or outdated |

---

## Directory Structure

```
docs/
├── FIGHT_TRACKING_COMPLETE.md          ← Fight tracking master doc
├── FIGHT_TRACKING_FINDINGS.md          ← Production statistics
├── DOCUMENTATION_INDEX.md              ← This file
│
├── finishing-metrics-*.md              ← Finishing metrics system (7 files)
├── database-*.md                       ← Database documentation (3 files)
├── API*.md                             ← API documentation (2 files)
│
├── analysis/                           ← Analysis & design documents
│   ├── comprehensive-player-profile-design.md
│   ├── finishing-metrics-visualization-strategy.md
│   ├── mobility-*.md (3 files)
│   └── top-20-players-mobility-analysis-CORRECTED.md
│
├── archive/
│   └── fight-tracking/                 ← Archived fight tracking docs
│       ├── README.md                   ← Archive guide
│       ├── *.md (11 archived docs)
│       └── *.py (2 prototype scripts)
│
└── prototypes/                         ← Prototype scripts
    └── process-finishing-metrics.py
```

---

## Quick Links

**Most Commonly Used**:
- 🎯 [Fight Tracking Complete Guide](FIGHT_TRACKING_COMPLETE.md)
- 📊 [Fight Tracking Findings](FIGHT_TRACKING_FINDINGS.md)
- 🗄️ [Database Schemas](database-schemas.md)
- 🎖️ [Finishing Metrics API](finishing-metrics-api.md)

**For New Developers**:
1. Start with [ARCHITECTURE.md](ARCHITECTURE.md)
2. Read [database-schemas.md](database-schemas.md)
3. Review [FIGHT_TRACKING_COMPLETE.md](FIGHT_TRACKING_COMPLETE.md)
4. Explore [finishing-metrics-implementation.md](finishing-metrics-implementation.md)

**For New Analysts**:
1. Start with [FIGHT_TRACKING_FINDINGS.md](FIGHT_TRACKING_FINDINGS.md)
2. Read [finishing-metrics-analysis.md](finishing-metrics-analysis.md)
3. Review [database-schemas.md](database-schemas.md)
4. Explore query examples in implementation guides

---

## Contributing to Documentation

**Adding New Documentation**:
1. Place in appropriate directory (`docs/` for general, `docs/analysis/` for analysis)
2. Update this index file
3. Add to relevant role-based section
4. Include clear audience and purpose

**Updating Existing Documentation**:
1. Update "Last Updated" date at top of document
2. Add changelog note if major changes
3. Update index if document purpose changes

**Archiving Documentation**:
1. Move to `docs/archive/[category]/`
2. Add README.md to archive directory explaining archive
3. Update index to point to new consolidated doc
4. Keep migration guide in archive README

---

## Document Maintenance Schedule

| Document Category | Review Frequency | Owner |
|-------------------|------------------|-------|
| Implementation Guides | Quarterly | Engineering |
| API Documentation | Per release | Engineering |
| Analysis Documents | As needed | Data Team |
| Strategy Documents | Quarterly | Product |
| Operations Guides | Per deployment | DevOps |

---

**Index Created**: October 15, 2025
**Total Documents**: 40+ active documents
**Archived Documents**: 13 fight-tracking documents
**Coverage**: All major systems documented
