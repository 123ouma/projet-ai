from database.db import connect

roles = [
    ("candidat", "Candidat", "global"),
    ("responsable_iit", "Responsable IIT", "establishment"),
    ("responsable_isb", "Responsable ISB", "establishment"),
    ("responsable_isa", "Responsable ISA", "establishment"),
    ("responsable_2i2s", "Responsable 2I2S", "establishment"),
    ("responsable_entretien", "Responsable entretien", "global"),
    ("direction", "Direction", "global"),
    ("administrateur", "Administrateur", "global"),
]

conn = connect()

try:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO roles (role_code, label, scope)
            VALUES (%s, %s, %s)
            ON CONFLICT (role_code) DO NOTHING
            """,
            roles
        )

        cur.execute("SELECT COUNT(*) AS total FROM roles")
        total = cur.fetchone()["total"]

    conn.commit()
    print(f"Rôles présents dans PostgreSQL : {total}")

finally:
    conn.close()

