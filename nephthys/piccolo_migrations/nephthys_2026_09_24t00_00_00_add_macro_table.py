from nephthys.database.raw_migration import raw_migration

ID = "2026-09-24T00:00:00:000000"
VERSION = "1.35.0"
DESCRIPTION = "Add Macro table"


async def forwards():
    return raw_migration(
        migration_id=ID,
        app_name="nephthys",
        description=DESCRIPTION,
        forwards="""
CREATE TABLE "Macro" (
  "id" SERIAL PRIMARY KEY UNIQUE NOT NULL,
  "name" TEXT NOT NULL,
  "message" TEXT NOT NULL,
  "resolveTicket" BOOLEAN NOT NULL DEFAULT true,
  "canRunOnClosed" BOOLEAN NOT NULL DEFAULT false,
  "postAsHelper" BOOLEAN NOT NULL DEFAULT false,
  "program" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""",
        backwards="""
DROP TABLE IF EXISTS "Macro";
""",
    )
