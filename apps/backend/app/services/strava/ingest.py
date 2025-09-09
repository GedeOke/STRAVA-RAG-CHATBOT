from sqlalchemy.orm import Session
from ..strava import client
from ... import models
from ..embeddings import embed_text


def ingest_club_feed(db: Session, club_id: int, per_page: int = 50):
    saved = 0
    page = 1

    while True:
        feed = client.club_activities(club_id, page=page, per_page=per_page)
        if not feed:
            break

        for act in feed:
            firstname = (act.get("athlete") or {}).get("firstname") or ""
            lastname = (act.get("athlete") or {}).get("lastname") or ""

            athlete = db.query(models.Athlete).filter_by(
                firstname=firstname, lastname=lastname
            ).first()
            if not athlete:
                athlete = models.Athlete(firstname=firstname, lastname=lastname)
                db.add(athlete)
                db.flush()

            exists = db.query(models.Activity).filter_by(
                name=act.get("name"),
                distance_m=act.get("distance"),
                moving_time_s=act.get("moving_time"),
                athlete_id=athlete.id
            ).first()
            if exists:
                continue

            distance_km = round(float(act.get("distance", 0)) / 1000, 2)
            duration_min = round(int(act.get("moving_time", 0)) / 60, 1)
            elev_gain = float(act.get("total_elevation_gain") or 0.0)

            text_repr = (
                f"{firstname} {lastname} melakukan {act.get('sport_type')} "
                f"berjudul '{act.get('name')}' sejauh {distance_km} km "
                f"dengan durasi {duration_min} menit "
                f"dan elevasi {elev_gain} m."
            )

            emb = embed_text(text_repr)  # 768-dim

            activity = models.Activity(
                athlete_id=athlete.id,
                name=act.get("name"),
                sport_type=act.get("sport_type"),
                distance_m=act.get("distance"),
                moving_time_s=act.get("moving_time"),
                elapsed_time_s=act.get("elapsed_time"),
                elev_gain_m=act.get("total_elevation_gain"),
                embedding=emb.tolist()
            )
            db.add(activity)
            saved += 1

        db.commit()
        page += 1

    return {"inserted": saved}
