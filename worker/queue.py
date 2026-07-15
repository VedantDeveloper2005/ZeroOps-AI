import os
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

class JobQueue(ABC):
    @abstractmethod
    def pop_job(self) -> Optional[Dict[str, Any]]:
        """Pulls the next queued job from the queue and marks it as running."""
        pass

    @abstractmethod
    def update_job_status(self, job_id: str, status: str, **kwargs) -> None:
        """Updates the status of a job and any related properties."""
        pass

class PostgresJobQueue(JobQueue):
    def __init__(self, database_url: str):
        # Convert postgresql+asyncpg or similar to psycopg2 compatible url
        cleaned_url = database_url
        if "postgresql+asyncpg://" in cleaned_url:
            cleaned_url = cleaned_url.replace("postgresql+asyncpg://", "postgresql://")
        
        # Handle connection parameters cleanly
        self.conn_str = cleaned_url
        
    def _get_connection(self):
        # Allow connecting with SSL if required (e.g. for Azure DB)
        if "postgres.database.azure.com" in self.conn_str:
            return psycopg2.connect(self.conn_str, sslmode="require")
        return psycopg2.connect(self.conn_str)

    def pop_job(self) -> Optional[Dict[str, Any]]:
        conn = None
        try:
            conn = self._get_connection()
            conn.autocommit = False
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                # Query next queued job and lock it
                cursor.execute("""
                    SELECT id, user_id, project_id, deployment_id, cloud, region 
                    FROM deployment_jobs 
                    WHERE status = 'queued' 
                    ORDER BY created_at ASC 
                    LIMIT 1 
                    FOR UPDATE SKIP LOCKED
                """)
                job = cursor.fetchone()
                if not job:
                    conn.rollback()
                    return None
                
                # Mark it as running atomically
                cursor.execute("""
                    UPDATE deployment_jobs 
                    SET status = 'running', updated_at = NOW() 
                    WHERE id = %s
                """, (job['id'],))
                
                conn.commit()
                # Return stringified UUIDs for standard dict usage
                return {
                    "id": str(job["id"]),
                    "user_id": str(job["user_id"]),
                    "project_id": str(job["project_id"]),
                    "deployment_id": str(job["deployment_id"]) if job["deployment_id"] else None,
                    "cloud": job["cloud"],
                    "region": job["region"]
                }
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"[Queue] Error popping job: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_job_status(self, job_id: str, status: str, **kwargs) -> None:
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Build dynamic update statement based on args
                fields = ["status = %s", "updated_at = NOW()"]
                params = [status]
                
                for key, val in kwargs.items():
                    fields.append(f"{key} = %s")
                    params.append(val)
                
                params.append(job_id)
                query = f"UPDATE deployment_jobs SET {', '.join(fields)} WHERE id = %s"
                cursor.execute(query, tuple(params))
                conn.commit()
        except Exception as e:
            print(f"[Queue] Error updating job {job_id} status: {e}")
        finally:
            if conn:
                conn.close()
