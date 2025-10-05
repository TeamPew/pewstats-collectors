# PewStats Collectors - Deployment Guide

This service uses **Git branches** for environment separation:
- `develop` branch → **Staging environment**
- `main` branch → **Production environment**

## Architecture

```
Git Repository (TeamPew/pewstats-collectors)
├── develop branch  → staging deployment
└── main branch     → production deployment
```

## Deployment with Komodo

### Staging Deployment
1. Komodo pulls from `develop` branch
2. Builds image: `ghcr.io/teampew/pewstats-collectors:staging`
3. Deploys using `compose.yaml` with staging env vars

### Production Deployment
1. Create PR: `develop` → `main`
2. Production image auto-built: `ghcr.io/teampew/pewstats-collectors:production`
3. Merge PR when ready
4. Komodo pulls from `main` branch
5. Deploys using `compose.yaml` with production env vars

## Manual Deployment

### 1. Configuration

Create `.env` file:
```bash
cp .env.example .env
# Edit with your credentials
```

### 2. Deploy Services

**For staging** (develop branch):
```bash
git checkout develop
docker compose up -d
```

**For production** (main branch):
```bash
git checkout main
docker compose up -d
```

## Services

The `compose.yaml` defines 4 services:

1. **match-discovery** - Discovers new matches for tracked players
2. **match-summary-worker** - Processes match details and extracts participant data
3. **telemetry-download-worker** - Downloads telemetry JSON files
4. **telemetry-processing-worker** - Processes telemetry events

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_HOST` | PostgreSQL host | `localhost` |
| `POSTGRES_DB` | Database name | `pewstats_production` |
| `POSTGRES_USER` | Database user | `pewstats_prod_user` |
| `POSTGRES_PASSWORD` | Database password | `secure_password` |
| `RABBITMQ_HOST` | RabbitMQ host | `localhost` |
| `PUBG_API_KEYS` | Comma-separated API keys | `key1,key2,key3` |

### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `RABBITMQ_PORT` | `5672` | RabbitMQ port |
| `RABBITMQ_USER` | `guest` | RabbitMQ username |
| `RABBITMQ_PASSWORD` | `guest` | RabbitMQ password |
| `PUBG_PLATFORM` | `steam` | PUBG platform |
| `LOG_LEVEL` | `INFO` | Logging level |
| `ENVIRONMENT` | `production` | Environment name |

## Scaling

Scale individual workers:
```bash
docker compose up -d --scale telemetry-processing-worker=3
docker compose up -d --scale match-summary-worker=2
```

## Updating

### Staging
```bash
git pull origin develop
docker compose pull
docker compose up -d
```

### Production
```bash
git pull origin main
docker compose pull
docker compose up -d
```

## Monitoring

```bash
# View logs
docker compose logs -f

# Check status
docker compose ps

# Resource usage
docker stats
```

## CI/CD Pipeline

### Automated Builds

- **Push to `develop`** → Builds `ghcr.io/teampew/pewstats-collectors:staging`
- **PR to `main`** → Builds `ghcr.io/teampew/pewstats-collectors:production` and `:latest`

### Available Images

```bash
# Staging (develop branch)
ghcr.io/teampew/pewstats-collectors:staging
ghcr.io/teampew/pewstats-collectors:0.1.0-staging.{sha}

# Production (main branch)
ghcr.io/teampew/pewstats-collectors:production
ghcr.io/teampew/pewstats-collectors:latest
ghcr.io/teampew/pewstats-collectors:0.1.0-prod.{sha}
```

## Best Practices

✅ **DO:**
- Use `develop` branch for staging/testing
- Create PRs from `develop` to `main` for production releases
- Test in staging before merging to main
- Use Git tags for version tracking

❌ **DON'T:**
- Push directly to `main` branch
- Mix staging and production code in separate directories
- Deploy without testing in staging first

## Support

- **Repository**: https://github.com/TeamPew/pewstats-collectors
- **Issues**: https://github.com/TeamPew/pewstats-collectors/issues
- **Documentation**: [/docs](/docs)
