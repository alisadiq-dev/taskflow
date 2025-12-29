"""Initial migration - create all tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is a placeholder - run 'alembic revision --autogenerate' to create actual migrations
    pass


def downgrade() -> None:
    pass
