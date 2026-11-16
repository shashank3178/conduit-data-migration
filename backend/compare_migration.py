import psycopg

SOURCE = {
    "host": "localhost",
    "port": 5434,
    "dbname": "source_db",
    "user": "source_user",
    "password": "source_pass_123",
}

DESTINATION = {
    "host": "localhost",
    "port": 5435,
    "dbname": "destination_db",
    "user": "destination_user",
    "password": "destination_pass_123",
}

QUERY = """
    SELECT id, amount
    FROM public.migration_load_test
    ORDER BY id
"""

with (
    psycopg.connect(**SOURCE) as source_conn,
    psycopg.connect(**DESTINATION) as destination_conn,
):
    with (
        source_conn.cursor() as source_cursor,
        destination_conn.cursor() as destination_cursor,
    ):
        source_cursor.execute(QUERY)
        destination_cursor.execute(QUERY)

        source_rows = source_cursor.fetchall()
        destination_rows = destination_cursor.fetchall()

source = dict(source_rows)
destination = dict(destination_rows)

missing = set(source) - set(destination)
extra = set(destination) - set(source)

different = [
    (row_id, source[row_id], destination[row_id])
    for row_id in source.keys() & destination.keys()
    if source[row_id] != destination[row_id]
]

print("SOURCE ROWS:", len(source))
print("DESTINATION ROWS:", len(destination))
print("MISSING ROWS:", len(missing))
print("EXTRA ROWS:", len(extra))
print("DIFFERENT AMOUNTS:", len(different))

print("\nFIRST 20 DIFFERENCES:")
for row in different[:20]:
    print(
        f"ID={row[0]} | "
        f"SOURCE={row[1]} | "
        f"DESTINATION={row[2]}"
    )