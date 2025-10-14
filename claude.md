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

## Notes

- Date: 2025-10-14
- Issue encountered: Committed code without running ruff format, causing CI/CD failure
- Resolution: Always run `ruff format src/ tests/` before committing
