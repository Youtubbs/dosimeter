# The database

Postgres with pgvector, through SQLAlchemy. Local work runs against Docker; the
deployed path runs against RDS with IAM authentication. Every read and write in
the project lives in `src/dosimeter/repository/`, and nothing else is allowed to
talk to the database.

## Local

Start it (Docker Desktop must be running):

    docker compose up -d

The container publishes port 55432, because a machine with its own Postgres
already has 5432 taken. The database, user and a development-only password are
in `docker-compose.yml`. Point the app at it by adding these to your `.env`:

    DOSIMETER_DB_HOST=localhost
    DOSIMETER_DB_PORT=55432
    DOSIMETER_DB_NAME=dosimeter
    DOSIMETER_DB_USER=dosimeter
    DOSIMETER_DB_USE_IAM_AUTH=false
    DOSIMETER_DB_PASSWORD=dosimeter_local_dev
    DOSIMETER_DB_SSLMODE=prefer

The database settings are their own typed model, read from `DOSIMETER_DB_*`, so
a migration or a seed run needs nothing else configured.

Apply the schema, then the seed rows:

    python -m dosimeter.repository.migrate up
    python -m dosimeter.repository.seeds

`migrate up` records what it applied in `schema_migrations`, so running it again
applies only what is new. `python -m dosimeter.repository.migrate status` lists
what is waiting.

Stop the container with `docker compose stop`, or `docker compose down -v` to
throw the data away as well.

## Tests

The tests in `tests/integration/` run against that container. They skip when
nothing answers, so notably the suite still passes on a machine without Docker:

    pytest tests/integration

Each test starts from an empty schema, so anything you seeded by hand is wiped.
Set `DOSIMETER_TEST_URL` to run them somewhere else.

## Migrations and the mapped tables

Numbered SQL files in `src/dosimeter/repository/migrations/` create the schema,
applied in order. To add one, create the next number, write forward-only SQL,
and commit it with the code that needs it. Never edit a migration that has been
merged; write another one.

`repository/orm.py` maps those same tables for SQLAlchemy, and every query goes
through a `Session` rather than raw SQL. A test compares the mapped columns
against the migrations, so the two cannot drift apart unnoticed.

## What is in it

| Table | Holds |
| --- | --- |
| exposures | One submitted packet, by internal worker id and district |
| artifacts | One file from a packet, with its content hash, S3 key and status |
| extracted_fields | One field read off an artifact, with unit and confidence |
| officers | Reviewing officers, by code |
| grants | Which districts an officer may read |
| worker_dose_histories | Prior dose by internal worker id |
| historical_exposures | Closed cases with narrative and embedding, for precedent search |
| sessions | One officer session |
| review_queue / review_decisions | Waiting cases and what the officer decided |
| run_records and children | What a turn did: tools, rules, retrievals, model calls, escalations, guardrails |
| idempotency_keys | Claimed once, so a repeated submit does not run twice |

**No column anywhere stores a worker name.** Names live in the detachable
identity record the redactor writes, never in the database. A test checks that
against the migrations and against the live schema.
