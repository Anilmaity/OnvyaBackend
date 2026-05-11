# Onvya Backend

Phase 1 + drivers + onboarding slice. See `Plan.md` for the full architecture and `docs/superpowers/specs/2026-05-11-onvya-backend-foundation-design.md` for this slice's spec.

## Local setup

```bash
docker compose up -d
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_minimal
python manage.py runserver
```

- GraphiQL: http://localhost:8000/graphql/
- Admin: http://localhost:8000/admin/
- Demo console user: `admin@demo.test` / `demo1234`
- Demo driver user: `driver@demo.test` / `demo1234`

## Tests

```bash
pytest
```
