"""restaurant_mcp.py

MCP server for restaurant / menu operations:
- Connects to Postgres
- Creates schema if missing
- Provides tools for listing restaurants, getting menus, and estimating prep time.

Run as a standalone MCP server (stdio transport):

    python restaurant_mcp.py
"""

import os
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------
# Load env & constants
# ---------------------------------------------------------------------

load_dotenv()

PG_DSN = os.getenv("PG_DSN")  # e.g. "postgresql://food_user:food_pwd@localhost:5432/food_delivery"

mcp = FastMCP("restaurant_db")


# ---------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------


def _get_conn() -> psycopg2.extensions.connection:
    if not PG_DSN:
        raise RuntimeError(
            "PG_DSN is not set. Example: "
            "PG_DSN=postgresql://food_user:food_pwd@localhost:5432/food_delivery"
        )
    return psycopg2.connect(PG_DSN, cursor_factory=RealDictCursor)


def _init_schema() -> None:
    """Create restaurants + menu_item tables if they don't exist.

    Optionally seed some sample data when the DB is empty.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()

        # Restaurants table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS restaurants (
                id                  SERIAL PRIMARY KEY,
                name                TEXT NOT NULL,
                address             TEXT,
                cuisine             TEXT,
                avg_prep_minutes    INT DEFAULT 20,
                is_open             BOOLEAN DEFAULT TRUE
            );
            """
        )

        # Menu items
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_item (
                id                  SERIAL PRIMARY KEY,
                restaurant_id       INT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
                name                TEXT NOT NULL,
                description         TEXT,
                price_inr           NUMERIC(10,2) NOT NULL,
                is_available        BOOLEAN DEFAULT TRUE,
                avg_prep_minutes    INT DEFAULT 15
            );
            """
        )

        conn.commit()

        # Seed minimal sample data if there are no restaurants yet
        cur.execute("SELECT COUNT(*) AS c FROM restaurants;")
        count = cur.fetchone()["c"]
        if count == 0:
            _seed_sample_data(cur)
            conn.commit()

    finally:
        conn.close()


def _seed_sample_data(cur: psycopg2.extensions.cursor) -> None:
    """Seed a couple of sample restaurants + menus for testing."""
    # Restaurant 1
    cur.execute(
        """
        INSERT INTO restaurants (name, address, cuisine, avg_prep_minutes)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """,
        ("Spice Hub", "MG Road, Bengaluru", "Indian", 25),
    )
    spice_hub_id = cur.fetchone()["id"]

    # Restaurant 2
    cur.execute(
        """
        INSERT INTO restaurants (name, address, cuisine, avg_prep_minutes)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """,
        ("Pizza Planet", "Indiranagar, Bengaluru", "Italian", 20),
    )
    pizza_planet_id = cur.fetchone()["id"]

    # Menus
    cur.execute(
        """
        INSERT INTO menu_item (restaurant_id, name, description, price_inr, avg_prep_minutes)
        VALUES
        (%s, %s, %s, %s, %s),
        (%s, %s, %s, %s, %s),
        (%s, %s, %s, %s, %s);
        """,
        (
            spice_hub_id,
            "Paneer Tikka",
            "Grilled cottage cheese with spices",
            280.00,
            18,
            spice_hub_id,
            "Butter Naan",
            "Soft tandoori naan with butter",
            60.00,
            8,
            pizza_planet_id,
            "Margherita Pizza",
            "Classic cheese and tomato pizza",
            350.00,
            20,
        ),
    )


# Initialize schema on module import
_init_schema()


# ---------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------


@mcp.tool()
def list_restaurants(
    cuisine_filter: Optional[str] = None,
    only_open: bool = True,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """List restaurants with optional cuisine filter.

    Args:
        cuisine_filter: filter by cuisine (e.g. "Indian"). Case-insensitive. If None, no filter.
        only_open: if True, only return restaurants where is_open = TRUE.
        limit: maximum number of restaurants to return.

    Returns:
        List of restaurant rows as dicts.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()

        query = """
            SELECT id, name, address, cuisine, avg_prep_minutes, is_open
            FROM restaurants
            WHERE 1=1
        """
        params: List[Any] = []

        if cuisine_filter:
            query += " AND cuisine ILIKE %s"
            params.append(f"%{cuisine_filter}%")

        if only_open:
            query += " AND is_open = TRUE"

        query += " ORDER BY id LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


@mcp.tool()
def get_restaurant(restaurant_id: int) -> Optional[Dict[str, Any]]:
    """Get details of a single restaurant by id."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, address, cuisine, avg_prep_minutes, is_open
            FROM restaurants
            WHERE id = %s;
            """,
            (restaurant_id,),
        )
        row = cur.fetchone()
        return row
    finally:
        conn.close()


@mcp.tool()
def get_menu(restaurant_id: int, only_available: bool = True) -> List[Dict[str, Any]]:
    """Get the menu for a given restaurant.

    Args:
        restaurant_id: ID of the restaurant.
        only_available: if True, only return items where is_available = TRUE.

    Returns:
        List of menu items as dicts.
    """
    conn = _get_conn()
    try:
        cur = conn.cursor()

        query = """
            SELECT
                id,
                restaurant_id,
                name,
                description,
                price_inr,
                is_available,
                avg_prep_minutes
            FROM menu_item
            WHERE restaurant_id = %s
        """
        params: List[Any] = [restaurant_id]

        if only_available:
            query += " AND is_available = TRUE"

        query += " ORDER BY id;"

        cur.execute(query, params)
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


@mcp.tool()
def estimate_prep_time(
    restaurant_id: int,
    menu_item_ids: List[int],
) -> Dict[str, Any]:
    """Estimate preparation time (in minutes) for selected menu items.

    Logic (simple heuristic):
      - Look up avg_prep_minutes for each requested item.
      - Take the max of item prep times (assumes parallel prep).
      - Enforce a minimum of restaurant.avg_prep_minutes.
    """
    if not menu_item_ids:
        return {
            "restaurant_id": restaurant_id,
            "items": [],
            "estimated_prep_minutes": 0,
            "note": "No menu_item_ids provided.",
        }

    conn = _get_conn()
    try:
        cur = conn.cursor()

        # Fetch restaurant baseline
        cur.execute(
            "SELECT id, name, avg_prep_minutes FROM restaurants WHERE id = %s;",
            (restaurant_id,),
        )
        rest = cur.fetchone()
        if not rest:
            return {
                "restaurant_id": restaurant_id,
                "items": [],
                "estimated_prep_minutes": 0,
                "note": "Restaurant not found.",
            }

        base_prep = rest["avg_prep_minutes"] or 0

        # Fetch requested items
        cur.execute(
            """
            SELECT id, name, avg_prep_minutes
            FROM menu_item
            WHERE restaurant_id = %s
              AND id = ANY(%s);
            """,
            (restaurant_id, menu_item_ids),
        )
        rows = cur.fetchall()

        if not rows:
            return {
                "restaurant_id": restaurant_id,
                "items": [],
                "estimated_prep_minutes": base_prep,
                "note": "No matching menu items found.",
            }

        item_prep_times = [
            (row["id"], row["name"], row["avg_prep_minutes"] or base_prep)
            for row in rows
        ]
        max_item_prep = max(p for _, _, p in item_prep_times)
        est_prep = max(base_prep, max_item_prep)

        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": rest["name"],
            "items": [
                {
                    "id": row_id,
                    "name": name,
                    "avg_prep_minutes": prep,
                }
                for (row_id, name, prep) in item_prep_times
            ],
            "estimated_prep_minutes": est_prep,
        }
    finally:
        conn.close()


@mcp.tool()
def search_menu_items(
    text: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Simple text search over menu items (by name & description)."""
    conn = _get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                r.id AS restaurant_id,
                r.name AS restaurant_name,
                m.id AS item_id,
                m.name AS item_name,
                m.description,
                m.price_inr
            FROM menu_item m
            JOIN restaurants r
              ON r.id = m.restaurant_id
            WHERE
                (m.name ILIKE %s OR m.description ILIKE %s)
                AND m.is_available = TRUE
                AND r.is_open = TRUE
            ORDER BY r.id, m.id
            LIMIT %s;
            """,
            (f"%{text}%", f"%{text}%", limit),
        )
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------

if __name__ == "__main__":
    # Run MCP over stdio (the usual way for ADK / A2A integration)
    mcp.run(transport="stdio")
