from sqlalchemy.orm import Session
from ..strava import client
from .utils import summarize_activity
from ... import models

def ingest_club_feed(db: Session, club_id: int, pages: int = 1, per_page: int = 50):
    feed = client.club_activities(club_id, page=1, per_page=per_page)
    saved = 0

    for act in feed:
        # cek kalau nama udah ada di DB, skip (biar idempotent)
        exists = db.query(models.Activity).filter_by(
            name=act.get("name"),
            distance_m=act.get("distance"),
            moving_time_s=act.get("moving_time")
        ).first()
        if exists:
            continue

        athlete = models.Athlete(
            firstname=act["athlete"].get("firstname"),
            lastname=act["athlete"].get("lastname")
        )
        db.add(athlete)
        db.flush()  # supaya athlete.id langsung ada

        activity = models.Activity(
            athlete_id=athlete.id,
            name=act.get("name"),
            sport_type=act.get("sport_type"),
            distance_m=act.get("distance"),
            moving_time_s=act.get("moving_time"),
            elapsed_time_s=act.get("elapsed_time"),
            elev_gain_m=act.get("total_elevation_gain"),
        )
        db.add(activity)
        db.flush()

        summary = models.ActivitySummary(
            activity_id=activity.id,
            summary=summarize_activity(act)
        )
        db.add(summary)

        saved += 1

    db.commit()
    return {"inserted": saved}
