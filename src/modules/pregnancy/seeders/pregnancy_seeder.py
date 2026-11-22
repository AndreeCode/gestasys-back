import random
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

import asyncpg

from ..domain.pregnancy_domain import STATUS_COMPLETED, STATUS_IN_FOLLOWUP, STATUS_PENDING, Pregnancy
from ..services.pregnancy_service import pregnancyService

NAMED = [
    ("Maria Fernanda", "Lopez Quispe", "70123456", "CS-SANMARTIN", 28, STATUS_IN_FOLLOWUP, "low", 24),
    ("Carla Andrea", "Ruiz Huaman", "70234567", "CS-SANTAROSA", 32, STATUS_PENDING, "medium", 9),
    ("Rosa Elena", "Garcia Pariona", "70345678", "PS-ELCARMEN", 24, STATUS_COMPLETED, "low", 0),
    ("Ana Lucia", "Mendoza Cardenas", "70456789", "CS-SANMARTIN", 30, STATUS_IN_FOLLOWUP, "high", 33),
]

FIRST_NAMES = ["Lucia", "Juana", "Yesenia", "Milagros", "Roxana", "Flor", "Karina", "Elizabeth", "Sonia", "Marleni",
               "Gladys", "Diana", "Katherine", "Nelly", "Silvia", "Patricia", "Noemi", "Edith", "Ruth", "Vilma"]
LAST_NAMES = ["Quispe", "Huaman", "Mendoza", "Palomino", "Cardenas", "Pariona", "Gutierrez", "Allcca", "Bautista",
              "Tito", "Yupanqui", "Ccorahua", "Vargas", "Prado", "Sulca", "Huaraca"]


async def seed_controls(conn, rng: random.Random, pregnancy_id: UUID, lmp: date, delivery: date | None, by: UUID) -> None:
    end = delivery - timedelta(days=3) if delivery else date.today()
    weight = 52 + rng.randint(0, 150) / 10
    week = 8 + rng.randint(0, 3)
    while True:
        control_date = lmp + timedelta(days=week * 7 + rng.randint(0, 3))
        if control_date > end:
            break
        weight += 1.2 + rng.randint(0, 14) / 10
        await conn.execute(
            """
            INSERT INTO prenatal_controls (pregnancy_id, control_date, gestational_weeks, weight_kg, systolic_bp,
                                           diastolic_bp, fetal_heart_rate, uterine_height_cm, hemoglobin,
                                           next_appointment, registered_by)
            VALUES ($1, $2, $3::float8, $4::float8, $5, $6, $7, $8::float8, $9::float8, $10, $11)
            """,
            pregnancy_id,
            control_date,
            round((control_date - lmp).days / 7, 1),
            round(weight, 1),
            100 + rng.randint(0, 34),
            60 + rng.randint(0, 24),
            125 + rng.randint(0, 29) if week >= 12 else None,
            week - 2 + rng.randint(0, 29) / 10 if week >= 20 else None,
            10.5 + rng.randint(0, 29) / 10,
            None if delivery else control_date + timedelta(days=28),
            by,
        )
        week += 4


async def seed_demo_pregnancies(conn: asyncpg.Connection, registered_by: UUID, facilities: dict[str, UUID]) -> int:
    if await conn.fetchval("SELECT count(*) FROM pregnancies") > 0:
        return 0

    rng = random.Random(20260110)
    codes = sorted(facilities)
    people = list(NAMED)
    for i in range(26):
        status = rng.choice([STATUS_IN_FOLLOWUP, STATUS_IN_FOLLOWUP, STATUS_PENDING, STATUS_COMPLETED])
        weeks = 5 + rng.randint(0, 9) if status == STATUS_PENDING else 6 + rng.randint(0, 33)
        people.append((
            rng.choice(FIRST_NAMES),
            f"{rng.choice(LAST_NAMES)} {rng.choice(LAST_NAMES)}",
            f"7{1000000 + i * 37311:07d}",
            rng.choice(codes),
            17 + rng.randint(0, 23),
            status,
            rng.choice(["low", "low", "low", "medium", "high"]),
            weeks,
        ))

    today = date.today()
    for index, (first, last, dni, facility, age, status, risk, weeks) in enumerate(people):
        birth = date(today.year - age, rng.randint(1, 12), rng.randint(1, 28))
        delivery = None
        if status == STATUS_COMPLETED:
            lmp = today - timedelta(days=300 + rng.randint(0, 59))
            delivery = lmp + timedelta(days=266 + rng.randint(0, 19))
        else:
            lmp = today - timedelta(days=weeks * 7 + rng.randint(0, 6))
        gravida = rng.randint(1, 4)
        p = Pregnancy(
            id=None,
            first_names=first,
            last_names=last,
            birth_date=birth,
            health_facility_id=facilities[facility],
            dni=dni,
            phone=f"9{rng.randint(10000000, 99999999)}",
            last_menstrual_period=lmp,
            gravida=gravida,
            parity=rng.randint(0, gravida - 1),
            risk_level=risk,
            status=status,
            delivery_date=delivery,
            registered_by=registered_by,
        )
        pregnancy_id = await pregnancyService.create_in(conn, p)

        created = min(lmp + timedelta(days=35 + rng.randint(0, 19)), today)
        if index < len(NAMED):
            created = today - timedelta(days=index + 1)
        created_at = datetime.combine(created, time(8 + rng.randint(0, 8)), tzinfo=timezone.utc)
        await conn.execute("UPDATE pregnancies SET created_at = $2 WHERE id = $1", pregnancy_id, created_at)

        if status != STATUS_PENDING:
            await seed_controls(conn, rng, pregnancy_id, lmp, delivery, registered_by)
    return len(people)
