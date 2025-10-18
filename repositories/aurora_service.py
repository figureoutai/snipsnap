import asyncio
import aiomysql

from utils.helpers import get_secret
from contextlib import asynccontextmanager
from typing import Dict, List, Any, Optional
from utils.logger import app_logger as logger
from config import DB_PORT, DB_HOST, DB_NAME, DB_SECRET_NAME, AWS_REGION



class AuroraService:

    def __init__(self, pool_size: int = 10):
        self.host = DB_HOST
        self.database = DB_NAME
        self.port = DB_PORT
        # secrets = get_secret(DB_SECRET_NAME, AWS_REGION)
        self.user = "admin"
        self.password = "somekindofpassword"
        self.pool_size = pool_size
        self.pool = None

        logger.info("AuroraService initialized with asyncio")

    async def initialize(self):
        """Initialize the connection pool. Call this before using the writer."""
        self.pool = await aiomysql.create_pool(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.database,
            minsize=1,
            maxsize=self.pool_size,
            autocommit=True,
        )
        logger.info(f"Connection pool created with size {self.pool_size}")

    @asynccontextmanager
    async def get_connection(self):
        """Async context manager for database connections."""
        if not self.pool:
            raise RuntimeError("Pool not initialized. Call initialize() first.")

        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                try:
                    yield cursor
                    await conn.commit()
                except Exception as e:
                    await conn.rollback()
                    raise e

    async def insert_dict(self, table_name: str, data: Dict[str, Any]) -> int:
        """
        Async insert of a single dictionary.

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys

        Returns:
            Last inserted row ID
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"

        async with self.get_connection() as cursor:
            await cursor.execute(query, list(data.values()))
            return cursor.lastrowid

    async def upsert_dict(
        self,
        table_name: str,
        data: Dict[str, Any],
        unique_keys: Optional[List[str]] = None,
    ) -> int:
        """
        Async insert or update of a dictionary (ON DUPLICATE KEY UPDATE).

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys
            unique_keys: List of column names to exclude from UPDATE clause

        Returns:
            Last inserted/updated row ID
        """
        if unique_keys is None:
            unique_keys = []

        columns = ", ".join(data.keys())
        placeholders = ", ".join(["%s"] * len(data))

        update_cols = [k for k in data.keys() if k not in unique_keys]
        updates = ", ".join([f"{col}=VALUES({col})" for col in update_cols])

        query = f"""
            INSERT INTO {table_name} ({columns}) 
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {updates}
        """

        async with self.get_connection() as cursor:
            await cursor.execute(query, list(data.values()))
            return cursor.lastrowid

    async def update_dict(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        where_params: tuple,
    ) -> int:
        """
        Async update of rows using dictionary data with a WHERE clause.

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys to update
            where_clause: WHERE clause (e.g., "id = %s")
            where_params: Tuple of parameters for WHERE clause

        Returns:
            Number of rows updated
        """
        set_clause = ", ".join([f"{k}=%s" for k in data.keys()])
        query = f"UPDATE {table_name} SET {set_clause} WHERE {where_clause}"

        params = list(data.values()) + list(where_params)

        async with self.get_connection() as cursor:
            await cursor.execute(query, params)
            return cursor.rowcount

    def _handle_task_result(self, task: asyncio.Task):
        """Callback to handle task completion and log errors."""
        try:
            result = task.result()
            logger.debug(f"Task completed successfully: {result}")
        except Exception as e:
            logger.error(f"Task failed with error: {e}")

    def insert_dict_nowait(self, table_name: str, data: Dict[str, Any]):
        """
        Fire-and-forget insert (creates task without waiting).

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys
        """
        task = asyncio.create_task(self.insert_dict(table_name, data))
        # Add error handling callback
        task.add_done_callback(self._handle_task_result)

    def upsert_dict_nowait(
        self,
        table_name: str,
        data: Dict[str, Any],
        unique_keys: Optional[List[str]] = None,
    ):
        """
        Fire-and-forget upsert (creates task without waiting).

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys
            unique_keys: List of column names to exclude from UPDATE clause
        """
        task = asyncio.create_task(self.upsert_dict(table_name, data, unique_keys))
        task.add_done_callback(self._handle_task_result)

    def update_dict_nowait(
        self,
        table_name: str,
        data: Dict[str, Any],
        where_clause: str,
        where_params: tuple,
    ):
        """
        Fire-and-forget update (creates task without waiting).

        Args:
            table_name: Name of the target table
            data: Dictionary with column names as keys to update
            where_clause: WHERE clause (e.g., "id = %s")
            where_params: Tuple of parameters for WHERE clause
        """
        task = asyncio.create_task(
            self.update_dict(table_name, data, where_clause, where_params)
        )
        task.add_done_callback(self._handle_task_result)

    async def get_stream(self, stream_id: str):
        query = """
            SELECT *
            FROM stream_metadata
            WHERE stream_id = %s
            LIMIT 1
        """

        async with self.get_connection() as cursor:
            await cursor.execute(query, (stream_id))
            result = await cursor.fetchone()
            return result

    async def get_video_by_stream_and_frame(
        self, stream_id: str, frame_index: int
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a single video metadata record by stream_id and frame_index.

        Args:
            stream_id: The stream identifier
            frame_index: The frame index

        Returns:
            Dictionary with video metadata or None if not found
        """
        query = """
            SELECT id, stream_id, filename, frame_index, timestamp, 
                   pts, width, height, created_at
            FROM video_metadata
            WHERE stream_id = %s AND frame_index = %s
            LIMIT 1
        """

        async with self.get_connection() as cursor:
            await cursor.execute(query, (stream_id, frame_index))
            result = await cursor.fetchone()
            return result

    async def get_videos_by_stream(
        self,
        stream_id: str,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None,
        limit: Optional[int] = None,
        order_by: str = "frame_index ASC",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve multiple video metadata records for a stream.

        Args:
            stream_id: The stream identifier
            start_frame: Optional starting frame index (inclusive)
            end_frame: Optional ending frame index (inclusive)
            limit: Maximum number of records to return
            order_by: Order clause (default: "frame_index ASC")

        Returns:
            List of dictionaries with video metadata
        """
        query = """
            SELECT id, stream_id, filename, frame_index, timestamp, 
                   pts, width, height, created_at
            FROM video_metadata
            WHERE stream_id = %s
        """
        params = [stream_id]

        # Add frame range filters
        if start_frame is not None:
            query += " AND frame_index >= %s"
            params.append(start_frame)

        if end_frame is not None:
            query += " AND frame_index <= %s"
            params.append(end_frame)

        # Add ordering
        query += f" ORDER BY {order_by}"

        # Add limit
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        async with self.get_connection() as cursor:
            await cursor.execute(query, tuple(params))
            results = await cursor.fetchall()
            return results

    async def get_audios_by_stream(
        self,
        stream_id: str,
        start_chunk: Optional[int] = None,
        end_chunk: Optional[int] = None,
        limit: Optional[int] = None,
        order_by: str = "chunk_index ASC",
    ) -> List[Dict[str, Any]]:
        """
        Retrieve multiple video metadata records for a stream.

        Args:
            stream_id: The stream identifier
            start_chunk: Optional starting frame index (inclusive)
            end_chunk: Optional ending frame index (inclusive)
            limit: Maximum number of records to return
            order_by: Order clause (default: "chunk_index ASC")

        Returns:
            List of dictionaries with video metadata
        """
        query = """
            SELECT id, stream_id, filename, chunk_index, start_timestamp, end_timestamp, sample_rate, transcript
            FROM audio_metadata
            WHERE stream_id = %s
        """
        params = [stream_id]

        # Add frame range filters
        if start_chunk is not None:
            query += " AND chunk_index >= %s"
            params.append(start_chunk)

        if end_chunk is not None:
            query += " AND chunk_index <= %s"
            params.append(end_chunk)

        # Add ordering
        query += f" ORDER BY {order_by}"

        # Add limit
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        async with self.get_connection() as cursor:
            await cursor.execute(query, tuple(params))
            results = await cursor.fetchall()
            return results

    async def get_scored_clips_by_stream(self, stream_id: str, start_time: float, end_time: float, order_by="start_time ASC"):
        """
        Retrieve multiple score metadata records for a stream.

        Args:
            stream_id: The stream identifier
            start_time: starting time for the record (inclusive)
            end_time: ending time for the record (inclusive)
            order_by: Order clause (default: "start_time ASC")
        Returns:
            List of dictionaries with video metadata
        """
        query = """
            SELECT id, stream_id, start_time, end_time, saliency_score, highlight_score, caption
            FROM score_metadata
            WHERE stream_id = %s AND
            start_time <= %s AND
            end_time >= %s
        """
        query += f" ORDER BY {order_by}"
        params = [stream_id, end_time, start_time]

        async with self.get_connection() as cursor:
            await cursor.execute(query, tuple(params))
            results = await cursor.fetchall()
            return results
        
    async def has_more_entries_after(self, stream_id: str, end_time: float) -> bool:
        """
        Check if there are more score_metadata entries after the given end_time for a specific stream.

        Args:
            stream_id: The stream identifier
            end_time: The reference end time

        Returns:
            True if more entries exist after the given end_time, False otherwise.
        """
        query = """
            SELECT *
            FROM score_metadata
            WHERE stream_id = %s AND start_time > %s
            LIMIT 1
        """
        params = [stream_id, end_time]

        async with self.get_connection() as cursor:
            await cursor.execute(query, tuple(params))
            row = await cursor.fetchone()
            logger.info(f"[AuroraService] - has_more_entries - {row}")
            return True if row else False

    async def close(self):
        """Close the connection pool."""
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()
            logger.info("Connection pool closed")
