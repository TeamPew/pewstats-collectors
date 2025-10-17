# Claude Code Development Notes

## Pre-commit Checklist

**IMPORTANT**: Always run code formatting before committing changes.

### Format Python Code

```bash
# Check formatting (dry-run)
ruff format --check src/ tests/

# Apply formatting
ruff format src/ tests/
```

### Lint Python Code

```bash
# Check for linting issues
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/
```

## CI/CD Pipeline

The GitHub Actions workflow runs the following checks:
- `ruff format --check` - Ensures code is properly formatted
- `ruff check` - Linting and code quality checks

**All checks must pass before merging.**

## Docker Build Policy

**CRITICAL**: Never build Docker images locally unless explicitly instructed.

### Workflow:
1. Make code changes
2. Run formatting/linting (if applicable)
3. Commit and push changes to GitHub
4. CI/CD pipeline automatically builds and publishes Docker images
5. Images are then pulled and deployed

### Why:
- Building locally wastes time and resources
- CI/CD ensures consistent builds
- Automated testing happens during CI/CD
- Images are properly tagged and versioned

**Exception**: Only build locally if specifically requested for testing purposes.

## Notes

- Date: 2025-10-14
- Issue encountered: Committed code without running ruff format, causing CI/CD failure
- Resolution: Always run `ruff format src/ tests/` before committing

- Date: 2025-10-17
- Issue encountered: Committed parallel_telemetry_processing_worker.py without running ruff format
- Resolution: Formatted file and pushed fix. **REMINDER**: Always run `ruff format src/ tests/` before every commit!
