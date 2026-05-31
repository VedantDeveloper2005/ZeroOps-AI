import os
import ssl
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

try:
    from backend import config
    from backend.models import Base
except ImportError:
    import config
    from models import Base

# Setup logging
logger = logging.getLogger("zeroops.database")
logging.basicConfig(level=logging.INFO)

DATABASE_URL = config.DATABASE_URL
database_available = False

# Ensure connection string uses postgresql+asyncpg for async execution
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# Configure SSL connection arguments for Azure or production PostgreSQL
connect_args = {}
if "postgres.database.azure.com" in DATABASE_URL or os.getenv("DB_SSL", "true").lower() == "true":
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ctx
    logger.info("SSL enabled for PostgreSQL connection")

async_engine = None
AsyncSessionLocal = None

if DATABASE_URL:
    try:
        async_engine = create_async_engine(
            DATABASE_URL,
            connect_args=connect_args,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        AsyncSessionLocal = sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        database_available = True
        logger.info("SQLAlchemy async engine successfully initialized.")
    except Exception as e:
        logger.error(f"Error creating SQLAlchemy async engine: {e}")
        database_available = False
else:
    logger.warning("DATABASE_URL is not set. Database operations will fail.")

# Dependency to get db session in FastAPI routes
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    global database_available
    from fastapi import HTTPException
    
    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=503,
            detail="Database connection is not configured."
        )
    
    # If database is marked as not available, try to initialize it again
    if not database_available:
        logger.info("Database is marked unavailable. Attempting to re-initialize...")
        success = await init_db()
        if not success:
            raise HTTPException(
                status_code=503,
                detail="Database connection is not available."
            )
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            database_available = False
            raise HTTPException(
                status_code=503,
                detail="Database connection lost or failed to respond."
            )
        finally:
            await session.close()

# Startup database validation and DDL table creation
async def init_db():
    global database_available
    if async_engine is None:
        logger.error("Skipping DB initialization: Database engine is not configured.")
        return False
        
    try:
        # Check connection using a simple SELECT 1
        from sqlalchemy import text
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("PostgreSQL Database connection validation succeeded.")
            
        # Run table creation in a transaction (so it commits)
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables initialized successfully.")
            database_available = True

        # Run schema migrations for existing tables
        await run_migrations()
        return True
    except Exception as e:
        error_msg = str(e).lower()
        if "does not exist" in error_msg or "3d000" in error_msg:
            logger.info("Database 'zeroops' does not exist. Attempting auto-creation...")
            try:
                from sqlalchemy import text
                # Connect to the default 'postgres' database
                default_db_url = DATABASE_URL.rsplit('/', 1)[0] + '/postgres'
                # Set isolation_level="AUTOCOMMIT" on the engine so we can run DDL statements
                temp_engine = create_async_engine(
                    default_db_url,
                    connect_args=connect_args,
                    isolation_level="AUTOCOMMIT"
                )
                async with temp_engine.connect() as temp_conn:
                    await temp_conn.execute(text("CREATE DATABASE zeroops"))
                await temp_engine.dispose()
                logger.info("Successfully created database 'zeroops'. Retrying table initialization...")
                
                # Retry setup with zeroops engine inside a transaction
                async with async_engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                    logger.info("Database tables initialized successfully after database creation.")
                    database_available = True

                # Run schema migrations for existing tables
                await run_migrations()
                return True
            except Exception as create_err:
                logger.error(f"Auto-creation of database 'zeroops' failed: {create_err}")
                
        logger.error(f"PostgreSQL Database startup validation failed: {e}")
        logger.warning("FastAPI backend starting without database-backed features.")
        database_available = False
        return False


async def run_migrations():
    """Run idempotent schema migrations using ALTER TABLE ADD COLUMN IF NOT EXISTS.
    Safe to run on every startup — only adds columns that don't already exist.
    This handles the case where create_all created the initial table but new columns
    were added to the SQLAlchemy model after deployment."""
    if not database_available or async_engine is None:
        return

    from sqlalchemy import text

    migration_statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS github_id TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS github_username TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS github_avatar_url TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS github_access_token_encrypted TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS github_connected BOOLEAN DEFAULT FALSE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS api_key TEXT",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS refresh_token TEXT",
        "ALTER TABLE deployments ADD COLUMN IF NOT EXISTS failure_reason TEXT",
        "ALTER TABLE deployments ADD COLUMN IF NOT EXISTS infrastructure_metadata JSON",
        
        # Deployment Metrics project_id column
        "ALTER TABLE deployment_metrics ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE",

        # AI Analysis extra fields columns
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS runtime TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS package_manager TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS docker_support BOOLEAN DEFAULT FALSE",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS monorepo_structure TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS database_dependencies JSON DEFAULT '[]'",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS deployment_strategy TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS build_commands TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS start_commands TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS environment_variables JSON DEFAULT '[]'",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS explanation TEXT",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS custom_domains JSON DEFAULT '[]'",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS members JSON DEFAULT '[]'",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS recommended_compute_tier TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS estimated_cost TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS recommended_region TEXT",
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS expected_traffic TEXT",
        "ALTER TABLE deployment_recommendations ADD COLUMN IF NOT EXISTS recommended_compute_tier TEXT",
        "ALTER TABLE deployment_recommendations ADD COLUMN IF NOT EXISTS estimated_cost TEXT",
        "ALTER TABLE deployment_recommendations ADD COLUMN IF NOT EXISTS recommended_region TEXT",
        "ALTER TABLE deployment_recommendations ADD COLUMN IF NOT EXISTS expected_traffic TEXT",

        
        # Make project_id in ai_analyses nullable
        "ALTER TABLE ai_analyses ALTER COLUMN project_id DROP NOT NULL",

        # Failure Analysis extra fields
        "ALTER TABLE failure_analyses ADD COLUMN IF NOT EXISTS confidence INTEGER DEFAULT 95",
        "ALTER TABLE failure_analyses ADD COLUMN IF NOT EXISTS impact TEXT",

        # AI Analysis pricing breakdown
        "ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS pricing_breakdown JSON",

        # Indexes
        "CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)",
        "CREATE INDEX IF NOT EXISTS ix_repositories_user_id ON repositories(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_deployments_project_id ON deployments(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_deployment_logs_deployment_id ON deployment_logs(deployment_id)",
        "CREATE INDEX IF NOT EXISTS ix_environments_project_id ON environments(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_deployment_metrics_project_id ON deployment_metrics(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_ai_analyses_project_id ON ai_analyses(project_id)",
        
        # New tables' indexes
        "CREATE INDEX IF NOT EXISTS ix_deployment_recommendations_user_id ON deployment_recommendations(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_deployment_recommendations_project_id ON deployment_recommendations(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_failure_analyses_user_id ON failure_analyses(user_id)",
        "CREATE INDEX IF NOT EXISTS ix_failure_analyses_project_id ON failure_analyses(project_id)",
        "CREATE INDEX IF NOT EXISTS ix_failure_analyses_deployment_id ON failure_analyses(deployment_id)",

        # Partial unique index for github_id (only non-null values)
        """DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_users_github_id_unique') THEN
                CREATE UNIQUE INDEX ix_users_github_id_unique ON users(github_id) WHERE github_id IS NOT NULL;
            END IF;
        END $$""",
    ]

    try:
        async with async_engine.begin() as conn:
            for stmt in migration_statements:
                await conn.execute(text(stmt))
        logger.info("Schema migrations completed successfully (GitHub OAuth columns, AI analysis fields, and indexes).")
    except Exception as e:
        logger.warning(f"Schema migration encountered an issue (may be non-critical): {e}")

