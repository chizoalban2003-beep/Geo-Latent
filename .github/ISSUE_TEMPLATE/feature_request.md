---
name: Feature request
about: New endpoint, market expansion, or engine capability
labels: enhancement
---

**Which layer does this touch?**
- [ ] Layer 1 — Ingestion & Security
- [ ] Layer 2 — Physics Engine
- [ ] Layer 3 — Homeostasis
- [ ] Layer 4 — Rendering / Frontend
- [ ] Layer 5 — Analytics / Ledger
- [ ] Gaming expansion
- [ ] Education expansion
- [ ] Billing / SaaS

**Describe the feature**

**Which billing tier should gate it?**
free / research / studio / enterprise / all

**Acceptance criteria**
- [ ] New endpoint(s) documented in README
- [ ] Tests added in `geolatent/tests/test_all.py`
- [ ] Alembic migration if DB schema changes
- [ ] Tier gate applied if premium feature
