import asyncpg

from ..domain.minsa_template import TemplateColumn


class MinsaTemplateRepository:
    async def get_all(self, conn: asyncpg.Connection) -> list[TemplateColumn]:
        rows = await conn.fetch(
            """
            SELECT key, kind, position, section, grp, label, aliases, fill_section, fill_group, fill_label, width,
                   visible, match_section, match_label, occ
            FROM minsa_columns ORDER BY position
            """
        )
        return [
            TemplateColumn(
                key=r["key"], kind=r["kind"], position=r["position"], section=r["section"], group=r["grp"],
                label=r["label"], width=r["width"], visible=r["visible"],
                fills=(r["fill_section"], r["fill_group"], r["fill_label"]), aliases=list(r["aliases"]),
                match_section=r["match_section"], match_label=r["match_label"], occ=r["occ"],
            )
            for r in rows
        ]

    async def replace_all(self, conn: asyncpg.Connection, columns: list[TemplateColumn]) -> None:
        keys = [c.key for c in columns]
        await conn.execute("DELETE FROM minsa_columns WHERE NOT (key = ANY($1::text[]))", keys)
        for c in columns:
            await conn.execute(
                """
                INSERT INTO minsa_columns (key, kind, position, section, grp, label, aliases, fill_section, fill_group,
                                           fill_label, width, visible, match_section, match_label, occ)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (key) DO UPDATE SET
                    position = EXCLUDED.position, section = EXCLUDED.section, grp = EXCLUDED.grp,
                    label = EXCLUDED.label, aliases = EXCLUDED.aliases, fill_section = EXCLUDED.fill_section,
                    fill_group = EXCLUDED.fill_group, fill_label = EXCLUDED.fill_label, width = EXCLUDED.width,
                    visible = EXCLUDED.visible
                """,
                c.key, c.kind, c.position, c.section, c.group, c.label, c.aliases, *c.fills, c.width, c.visible,
                c.match_section, c.match_label, c.occ,
            )

    async def clear(self, conn: asyncpg.Connection) -> None:
        await conn.execute("DELETE FROM minsa_columns")


minsaTemplateRepository = MinsaTemplateRepository()
