# db.py
"""
Postgres DB helper for restaurant MCP.

Schema:
- restaurants(
    id INTEGER PRIMARY KEY,
    name TEXT,
    address TEXT,
    cuisine TEXT,
    avg_prep_minutes INT,
    is_open BOOLEAN
  )

- menu_item(
    id INTEGER,
    restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
    name TEXT,
    description TEXT,
    price_inr NUMERIC(10,2),
    is_available BOOLEAN,
    avg_prep_minutes INT,
    PRIMARY KEY (id, restaurant_id)
  )

Used by restaurant_mcp.py via asyncpg.
"""

import os
import random
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

DB_DSN = (
    os.getenv("PG_DSN")
    or os.getenv("DATABASE_URL")
    or "postgresql://postgres:postgress@localhost:5432/food_delivery"
)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        if not DB_DSN:
            raise RuntimeError("No Postgres DSN configured. Set PG_DSN or DATABASE_URL.")
        _pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=5)
    return _pool


async def init_db() -> None:
    """
    Create schema and seed sample data if tables are empty.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ----- Tables -----
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS restaurants (
                id                  INTEGER PRIMARY KEY,
                name                TEXT NOT NULL,
                address             TEXT,
                cuisine             TEXT,
                avg_prep_minutes    INT DEFAULT 20,
                is_open             BOOLEAN DEFAULT TRUE
            );
            """
        )

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS menu_item (
                id                  INTEGER,
                restaurant_id       INT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
                name                TEXT NOT NULL,
                description         TEXT,
                price_inr           NUMERIC(10,2) NOT NULL,
                is_available        BOOLEAN DEFAULT TRUE,
                avg_prep_minutes    INT DEFAULT 15,
                PRIMARY KEY (id, restaurant_id)
            );
            """
        )

        # ----- Seed restaurants -----
        rest_count = await conn.fetchval("SELECT COUNT(*) FROM restaurants;")
        if not rest_count or rest_count == 0:
            # 3 fixed restaurants
            await conn.execute(
                """
                INSERT INTO restaurants (id, name, address, cuisine, avg_prep_minutes, is_open)
                VALUES
                  (1, 'Spice Hub',     'MG Road, Bengaluru',        'Indian',     25, TRUE),
                  (2, 'Pizza Planet',  'Indiranagar, Bengaluru',    'Italian',    20, TRUE),
                  (3, 'Burger Corner', 'Brigade Road, Bengaluru',   'Fast Food',  18, TRUE)
                ON CONFLICT (id) DO NOTHING;
                """
            )

            # Random restaurants 4..1000
            adjectives = ["Golden", "Spicy", "Royal", "Urban", "Classic",
                          "Fusion", "Tasty", "Savory", "Cozy", "Hearty"]
            types = ["Kitchen", "Bistro", "Grill", "Diner", "Cafe",
                     "House", "Corner", "Garden", "Table", "Hub"]
            cuisines = [
                "Indian", "Italian", "Chinese", "Thai", "Mexican",
                "American", "Mediterranean", "Japanese", "Korean", "Fusion",
            ]

            for rid in range(4, 1001):
                name = f"{random.choice(adjectives)} {random.choice(types)} {rid}"
                address = f"Area {random.randint(1,50)}, Bengaluru"
                cuisine = random.choice(cuisines)
                avg_prep = random.randint(15, 30)
                is_open = random.random() > 0.1  # 90% open

                await conn.execute(
                    """
                    INSERT INTO restaurants (id, name, address, cuisine, avg_prep_minutes, is_open)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (id) DO NOTHING;
                    """,
                    rid, name, address, cuisine, avg_prep, is_open
                )

            # Explicit restaurant that looks like your prompt text (optional)
            await conn.execute(
                """
                INSERT INTO restaurants (id, name, address, cuisine, avg_prep_minutes, is_open)
                VALUES ($1, $2, $3, $4, $5, TRUE)
                ON CONFLICT (id)
                DO UPDATE SET
                  name = EXCLUDED.name,
                  address = EXCLUDED.address,
                  cuisine = EXCLUDED.cuisine,
                  avg_prep_minutes = EXCLUDED.avg_prep_minutes,
                  is_open = TRUE;
                """,
                36,
                "Spicy Garden 36",
                "Indiranagar, Bengaluru",
                "Indian",
                23,
            )

        # ----- Seed menu items -----
        menu_count = await conn.fetchval("SELECT COUNT(*) FROM menu_item;")
        if not menu_count or menu_count == 0:
            # Fixed menu for first 3 restaurants
            await conn.execute(
                """
                INSERT INTO menu_item (
                    id, restaurant_id, name, description,
                    price_inr, is_available, avg_prep_minutes
                )
                VALUES
                  -- Spice Hub (id=1)
                  (1, 1, 'Paneer Tikka',
                      'Grilled cottage cheese with spices',
                      280.00, TRUE, 18),
                  (2, 1, 'Butter Naan',
                      'Soft tandoori naan with butter',
                      60.00, TRUE, 8),
                  (3, 1, 'Veg Biryani',
                      'Aromatic rice with veggies and spices',
                      260.00, TRUE, 25),

                  -- Pizza Planet (id=2)
                  (1, 2, 'Margherita Pizza',
                      'Classic cheese and tomato pizza',
                      350.00, TRUE, 20),
                  (2, 2, 'Farmhouse Pizza',
                      'Loaded with veggies and cheese',
                      420.00, TRUE, 22),
                  (3, 2, 'Garlic Bread',
                      'Toasted bread with garlic and herbs',
                      150.00, TRUE, 10),

                  -- Burger Corner (id=3)
                  (1, 3, 'Veggie Burger',
                      'Crispy patty with fresh veggies',
                      180.00, TRUE, 12),
                  (2, 3, 'French Fries',
                      'Crispy golden fries',
                      120.00, TRUE, 8),
                  (3, 3, 'Cold Coffee',
                      'Chilled coffee with ice cream',
                      160.00, TRUE, 5)
                ON CONFLICT (id, restaurant_id) DO NOTHING;
                """
            )

            # Menu items for Spicy Garden 36 (your “Tangy Chicken” case)
            await conn.execute(
                """
                INSERT INTO menu_item (
                    id, restaurant_id, name, description,
                    price_inr, is_available, avg_prep_minutes
                )
                VALUES
                  (1, 36, 'Tangy Chicken',
                      'Chicken in a tangy, spicy sauce',
                      320.00, TRUE, 22),
                  (2, 36, 'Butter Naan',
                      'Soft tandoori naan with butter',
                      60.00, TRUE, 8)
                ON CONFLICT (id, restaurant_id) DO NOTHING;
                """
            )

            # Random menu items up to ~200 total
            dish_adjectives = [
                "Spicy", "Crispy", "Cheesy", "Smoky", "Tangy",
                "Herbed", "Creamy", "Grilled", "Masala", "Zesty",
            ]
            dish_bases = [
                "Paneer", "Chicken", "Veg Platter", "Noodles", "Pasta",
                "Rice Bowl", "Sandwich", "Wrap", "Salad", "Soup",
            ]

            for i in range(191):
                item_id = 10 + i
                restaurant_id = random.randint(1, 1000)
                name = f"{random.choice(dish_adjectives)} {random.choice(dish_bases)}"
                desc = f"Signature {name.lower()} prepared fresh."
                price_inr = round(random.uniform(80, 500), 2)
                is_available = random.random() > 0.05
                prep_minutes = random.randint(5, 30)

                await conn.execute(
                    """
                    INSERT INTO menu_item (
                        id, restaurant_id, name, description,
                        price_inr, is_available, avg_prep_minutes
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (id, restaurant_id) DO NOTHING;
                    """,
                    item_id,
                    restaurant_id,
                    name,
                    desc,
                    price_inr,
                    is_available,
                    prep_minutes,
                )


# ------------------- Query helpers used by MCP ----------------------


async def list_restaurants_db(
    cuisine_filter: Optional[str],
    only_open: bool,
    limit: int,
) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = """
            SELECT id, name, address, cuisine, avg_prep_minutes, is_open
            FROM restaurants
            WHERE 1=1
        """
        params: List[Any] = []

        if cuisine_filter:
            query += " AND cuisine ILIKE $1"
            params.append(f"%{cuisine_filter}%")

        next_idx = len(params) + 1

        if only_open:
            query += " AND is_open = TRUE"

        query += f" ORDER BY id LIMIT ${next_idx}"
        params.append(limit)

        rows = await conn.fetch(query, *params)

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "address": r["address"],
            "cuisine": r["cuisine"],
            "avg_prep_minutes": r["avg_prep_minutes"],
            "is_open": r["is_open"],
        }
        for r in rows
    ]


async def get_restaurant_db(restaurant_id: int) -> Optional[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, address, cuisine, avg_prep_minutes, is_open
            FROM restaurants
            WHERE id = $1;
            """,
            restaurant_id,
        )
    if not row:
        return None
    return dict(row)


async def get_menu_db(
    restaurant_id: int,
    only_available: bool,
) -> List[Dict[str, Any]]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        query = """
            SELECT
                id, restaurant_id, name, description,
                price_inr, is_available, avg_prep_minutes
            FROM menu_item
            WHERE restaurant_id = $1
        """
        params: List[Any] = [restaurant_id]

        if only_available:
            query += " AND is_available = TRUE"

        query += " ORDER BY id;"

        rows = await conn.fetch(query, *params)

    return [
        {
            "id": r["id"],
            "restaurant_id": r["restaurant_id"],
            "name": r["name"],
            "description": r["description"],
            "price_inr": float(r["price_inr"]),
            "is_available": r["is_available"],
            "avg_prep_minutes": r["avg_prep_minutes"],
        }
        for r in rows
    ]


async def get_menu_items_by_ids_db(
    restaurant_id: int,
    menu_item_ids: List[int],
) -> List[Dict[str, Any]]:
    if not menu_item_ids:
        return []

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, avg_prep_minutes
            FROM menu_item
            WHERE restaurant_id = $1
              AND id = ANY($2::int[]);
            """,
            restaurant_id,
            menu_item_ids,
        )

    return [
        {
            "id": r["id"],
            "name": r["name"],
            "avg_prep_minutes": r["avg_prep_minutes"],
        }
        for r in rows
    ]


async def search_menu_items_db(text: str, limit: int) -> List[Dict[str, Any]]:
    pattern = f"%{text}%"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                r.id   AS restaurant_id,
                r.name AS restaurant_name,
                m.id   AS item_id,
                m.name AS item_name,
                m.description,
                m.price_inr
            FROM menu_item m
            JOIN restaurants r
              ON r.id = m.restaurant_id
            WHERE
                (m.name ILIKE $1 OR m.description ILIKE $1)
                AND m.is_available = TRUE
                AND r.is_open = TRUE
            ORDER BY r.id, m.id
            LIMIT $2;
            """,
            pattern,
            limit,
        )

    return [
        {
            "restaurant_id": r["restaurant_id"],
            "restaurant_name": r["restaurant_name"],
            "item_id": r["item_id"],
            "item_name": r["item_name"],
            "description": r["description"],
            "price_inr": float(r["price_inr"]),
        }
        for r in rows
    ]


async def estimate_prep_time_db(
    restaurant_id: int,
    menu_item_ids: List[int],
) -> Dict[str, Any]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rest_row = await conn.fetchrow(
            "SELECT id, name, avg_prep_minutes FROM restaurants WHERE id = $1;",
            restaurant_id,
        )

        if not rest_row:
            return {
                "restaurant_id": restaurant_id,
                "restaurant_name": None,
                "items": [],
                "estimated_prep_minutes": 0,
                "note": "Restaurant not found.",
            }

        base_prep = rest_row["avg_prep_minutes"] or 0

        rows = await conn.fetch(
            """
            SELECT id, name, avg_prep_minutes
            FROM menu_item
            WHERE restaurant_id = $1
              AND id = ANY($2::int[]);
            """,
            restaurant_id,
            menu_item_ids,
        )

    if not rows:
        return {
            "restaurant_id": restaurant_id,
            "restaurant_name": rest_row["name"],
            "items": [],
            "estimated_prep_minutes": base_prep,
            "note": "No matching menu items found.",
        }

    item_prep_times: List[Tuple[int, str, int]] = []
    for r in rows:
        prep = r["avg_prep_minutes"] or base_prep
        item_prep_times.append((r["id"], r["name"], prep))

    max_item_prep = max(p for _, _, p in item_prep_times)
    est_prep = max(base_prep, max_item_prep)

    return {
        "restaurant_id": restaurant_id,
        "restaurant_name": rest_row["name"],
        "items": [
            {"id": row_id, "name": name, "avg_prep_minutes": prep}
            for (row_id, name, prep) in item_prep_times
        ],
        "estimated_prep_minutes": est_prep,
    }
