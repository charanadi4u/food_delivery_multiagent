import asyncio
import traceback

import db  # our db.py in the same folder


async def main():
    print("=== test_restaurant_tools.py starting ===")

    # Show which DSN is being used
    print("DB_DSN =", getattr(db, "DB_DSN", "<no DB_DSN attr>"))

    try:
        print("\n[1] Calling db.init_db() ...")
        await db.init_db()
        print("[1] init_db() finished OK")

        print("\n[2] list_restaurants_db(cuisine_filter=None, only_open=True, limit=5)")
        rs = await db.list_restaurants_db(
            cuisine_filter=None,
            only_open=True,
            limit=5,
        )
        for r in rs:
            print("  restaurant:", r)

        print("\n[3] get_restaurant_db(1)")
        r1 = await db.get_restaurant_db(1)
        print("  get_restaurant_db(1) ->", r1)

        print("\n[4] get_menu_db(restaurant_id=1, only_available=True)")
        menu = await db.get_menu_db(restaurant_id=1, only_available=True)
        for m in menu:
            print("  menu item:", m)

        print("\n[5] estimate_prep_time_db(restaurant_id=1, menu_item_ids=[1, 2])")
        est = await db.estimate_prep_time_db(restaurant_id=1, menu_item_ids=[1, 2])
        print("  estimate_prep_time_db(...) ->", est)

        print("\n[6] search_menu_items_db('Paneer', 5)")
        found = await db.search_menu_items_db("Paneer", 5)
        for row in found:
            print("  search result:", row)

        print("\n=== test_restaurant_tools.py finished successfully ===")

    except Exception as e:
        print("\n*** ERROR in test_restaurant_tools.py ***")
        print("Exception:", repr(e))
        print("Traceback:")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
