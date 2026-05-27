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
    if not database_available or AsyncSessionLocal is None:
        raise RuntimeError("Database connection is not available.")
    
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Startup database validation and DDL table creation
async def init_db():
    global database_available
    if not database_available or async_engine is None:
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
                    return True
            except Exception as create_err:
                logger.error(f"Auto-creation of database 'zeroops' failed: {create_err}")
                
        logger.error(f"PostgreSQL Database startup validation failed: {e}")
        logger.warning("FastAPI backend starting in fallback mock mode. DB operations will be unavailable.")
        database_available = False
        return False
