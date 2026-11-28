"""Fix basira_login_identity, which matched every account instead of the one signing in.

In a SQL-language function, an unqualified name that matches a column of a queried table resolves
to the column, not to the function argument. The 0027 definition filtered with
`u.issuer = issuer AND u.subject = subject`, which PostgreSQL read as each column compared to
itself, so the function returned one row per user. Both sign-in lookups take the first row, so a
password was compared against whichever account happened to come back first and legitimate logins
were rejected (and a password matching the wrong account would have been accepted). Qualifying the
arguments with the function name restores the intended identity lookup.
"""

from alembic import op

revision = "platform_login_identity_0032"
down_revision = "platform_agent_memory_0031"
branch_labels = None
depends_on = None

FUNCTION = """
CREATE OR REPLACE FUNCTION public.basira_login_identity(issuer text, subject text)
RETURNS TABLE(user_id text, disabled_at timestamp with time zone, password_hash text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
SET row_security = off
AS $$
SELECT u.id::text, u.disabled_at, c.password_hash::text
FROM public.users u
LEFT JOIN public.password_credentials c ON c.user_id = u.id
WHERE u.issuer = basira_login_identity.issuer
  AND u.subject = basira_login_identity.subject
$$
"""

PREVIOUS = """
CREATE OR REPLACE FUNCTION public.basira_login_identity(issuer text, subject text)
RETURNS TABLE(user_id text, disabled_at timestamp with time zone, password_hash text)
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog
SET row_security = off
AS $$
SELECT u.id::text, u.disabled_at, c.password_hash::text
FROM public.users u
LEFT JOIN public.password_credentials c ON c.user_id = u.id
WHERE u.issuer = issuer
  AND u.subject = subject
$$
"""


def upgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    # CREATE OR REPLACE keeps the function's owner and the existing GRANT to basira_app.
    op.execute(FUNCTION)


def downgrade():
    if op.get_context().dialect.name != "postgresql":
        return
    op.execute(PREVIOUS)
