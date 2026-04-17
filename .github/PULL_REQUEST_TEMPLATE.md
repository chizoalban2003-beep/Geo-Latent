## What does this PR do?

<!-- One sentence summary -->

## Checklist

- [ ] Tests added / updated (`pytest geolatent/tests/ -v` passes)
- [ ] No `@app.on_event` used — lifespan pattern only
- [ ] No per-request `_connect()` — uses `app.state.db_pool`
- [ ] No raw `CREATE TABLE` — Alembic migration if schema changes
- [ ] `_sanitise()` called on any user-supplied dicts
- [ ] Tier gate applied if this is a premium feature
- [ ] README updated if new endpoints added
- [ ] `step_value = state.step or 0` used in any PolicyIntervention

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation

## Related issues

Closes #
