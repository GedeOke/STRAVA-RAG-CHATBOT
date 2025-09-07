from sqlalchemy.orm import Session
from app.models import Activity, ActivitySummary
from app.services.strava import utils

def generate_summaries(db: Session, limit: int = 50):
    """Generate summary untuk activity yang belum punya summary"""
    acts = (
        db.query(ActivitySummary)
        .filter(ActivitySummary.summary == None)
        .limit(limit)
        .all()
    )

    updated = 0
    for act in acts:
        # convert row jadi dict untuk dipassing ke summarize_activity
        act_dict = {
            "athlete": {"firstname": act.athlete_firstname, "lastname": act.athlete_lastname},
            "distance": act.distance,
            "moving_time": act.moving_time,
            "total_elevation_gain": act.elevation_gain,
            "sport_type": act.sport_type,
            "name": act.name,
        }

        act.summary = utils.summarize_activity(act_dict)
        updated += 1

    db.commit()
    return {"updated": updated}
