# -*- coding: utf-8 -*-
"""
seed_demo_history.py — синтетическая история цен для ДЕМОНСТРАЦИИ динамики.

Берёт текущую (реальную) цену услуги в каждой клинике и достраивает назад
несколько помесячных точек (is_demo=True) с мягким трендом, чтобы график
«Динамика цены» показывал линии, а не одинокие точки.

Идемпотентно: удаляет только свои демо-точки (is_demo=true) по услуге и
пересоздаёт их. Реальные точки (is_demo=false) не трогает.

Запуск:
  set DATABASE_URL=postgresql://loader.<ref>:<pwd>@<host>:5432/postgres
  python -X utf8 seed_demo_history.py mri_brain
"""
import datetime as dt
import os
import sys

import psycopg

# Помесячные даты ПЕРЕД текущей точкой (старое -> новое). Текущая реальная
# точка обычно стоит на 2026-06-28, поэтому достраиваем янв..май 2026.
SYNTH_DATES = [
    dt.datetime(2026, 1, 15, 12),
    dt.datetime(2026, 2, 15, 12),
    dt.datetime(2026, 3, 15, 12),
    dt.datetime(2026, 4, 15, 12),
    dt.datetime(2026, 5, 15, 12),
]


def dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: задай DATABASE_URL (Postgres)")
    return url.replace("postgresql+psycopg://", "postgresql://")


def trajectory(final_price: int, clinic_id: int) -> list[int]:
    """Цены для SYNTH_DATES, завершающиеся около текущей.

    Лёгкий восходящий тренд (старое дешевле) + детерминированный по clinic_id
    «шум», чтобы линии не были идеально гладкими. Никакого рандома — повтор
    запуска даёт тот же результат.
    """
    n = len(SYNTH_DATES)
    # суммарный рост за период: 6..14% (зависит от клиники)
    total_growth = 0.06 + (clinic_id % 9) / 100.0
    out: list[int] = []
    for i in range(n):
        # доля пути от «старой» цены к текущей (0..<1 для синт-точек)
        frac = i / n
        base = final_price / (1.0 + total_growth)  # цена в самой ранней точке
        val = base * (1.0 + total_growth * frac)
        # детерминированный зигзаг ±1.5%
        wobble = 1.0 + (((clinic_id * 7 + i * 13) % 7) - 3) / 200.0
        price = int(round(val * wobble / 100.0)) * 100  # округление до 100 тг
        out.append(max(100, price))
    return out


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "mri_brain"
    with psycopg.connect(dsn(), sslmode="require", prepare_threshold=None) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM services WHERE code=%s", (code,))
        row = cur.fetchone()
        if not row:
            sys.exit(f"ERROR: услуга {code!r} не найдена")
        sid, sname = row
        print(f"Услуга: {sname} (id={sid}, code={code})")

        # текущая реальная цена на услугу в каждой клинике (последняя не-демо точка)
        cur.execute(
            """
            SELECT DISTINCT ON (clinic_id) clinic_id, price
            FROM price_history
            WHERE service_id=%s AND coalesce(is_demo,false)=false
            ORDER BY clinic_id, recorded_at DESC
            """,
            (sid,),
        )
        current = cur.fetchall()
        if not current:
            sys.exit("ERROR: нет реальных точек price_history для этой услуги")
        print(f"Реальных точек (клиник): {len(current)}")

        # чистим прошлые демо-точки именно по этой услуге
        cur.execute(
            "DELETE FROM price_history WHERE service_id=%s AND is_demo=true", (sid,)
        )
        deleted = cur.rowcount

        rows = []
        for clinic_id, final_price in current:
            for d, p in zip(SYNTH_DATES, trajectory(final_price, clinic_id)):
                rows.append((clinic_id, sid, p, d, "synthetic-demo", "ДЕМО: синтетическая точка"))

        cur.executemany(
            "INSERT INTO price_history "
            "(clinic_id,service_id,price,recorded_at,source_file,raw_name,is_demo) "
            "VALUES (%s,%s,%s,%s,%s,%s,true)",
            rows,
        )
        conn.commit()
        print(f"Удалено старых демо-точек: {deleted}")
        print(f"Добавлено демо-точек: {len(rows)}  "
              f"({len(SYNTH_DATES)} на клинику x {len(current)} клиник)")
        print("Теперь у каждой клиники по"
              f" {len(SYNTH_DATES)+1} точек — график рисует тренд-линии.")


if __name__ == "__main__":
    main()
