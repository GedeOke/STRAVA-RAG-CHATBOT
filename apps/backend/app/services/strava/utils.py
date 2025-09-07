def summarize_activity(act: dict) -> str:
    """Bikin ringkasan teks dari feed club"""
    athlete = f"{act['athlete'].get('firstname','?')} {act['athlete'].get('lastname','')}".strip()
    dist_km = round(act.get("distance", 0) / 1000, 2)
    time_min = round(act.get("moving_time", 0) / 60, 1)
    elev = act.get("total_elevation_gain", 0)

    return (
        f"{athlete} melakukan {act.get('sport_type','?')} berjudul "
        f"'{act.get('name','-')}' sejauh {dist_km} km "
        f"dengan durasi {time_min} menit dan elevasi {elev} m."
    )
