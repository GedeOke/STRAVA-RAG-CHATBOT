from sqlalchemy.orm import Session
from ..strava import client
from ... import models
from ..embeddings import embed_text
from datetime import datetime
import logging, json, hashlib


def ingest_club_feed(db: Session, club_id: int, per_page: int = 50):
    saved = 0
    page = 1

    # Pastikan club ada di DB (selalu cast str)
    club = db.query(models.Club).filter_by(strava_id=str(club_id)).first()
    if not club:
        club = models.Club(strava_id=str(club_id), name=f"Club {club_id}")
        db.add(club)
        db.flush()

    while True:
        try:
            feed = client.club_activities(club_id, page=page, per_page=per_page)
        except Exception as e:
            logging.error(f"Gagal ambil feed club {club_id} page {page}: {e}")
            break

        if not feed:
            break

        for act in feed:
            try:
                # Ambil strava_id dari beberapa kemungkinan field (cast ke str)
                raw_id = (
                    act.get("id")
                    or act.get("activity_id")
                    or (act.get("activity") or {}).get("id")
                )
                strava_id = str(raw_id) if raw_id else None

                athlete_data = act.get("athlete") or {}
                firstname = athlete_data.get("firstname") or ""
                lastname = athlete_data.get("lastname") or ""

                # Fallback: generate pseudo-id kalau strava_id tidak ada
                if not strava_id or strava_id == "None":
                    raw_key = f"{firstname}-{lastname}-{act.get('name')}-{act.get('distance')}-{act.get('moving_time')}"
                    strava_id = hashlib.md5(raw_key.encode("utf-8")).hexdigest()
                    logging.warning(f"Generate pseudo-id untuk activity: {strava_id}")

                # Skip kalau activity sudah ada
                if db.query(models.Activity).filter_by(strava_id=str(strava_id)).first():
                    continue

                # Cari/insert athlete
                athlete = db.query(models.Athlete).filter_by(
                    firstname=firstname, lastname=lastname
                ).first()
                if not athlete:
                    athlete = models.Athlete(firstname=firstname, lastname=lastname)
                    db.add(athlete)
                    db.flush()

                # --- Extract dan konversi nilai ---
                distance_m = float(act.get("distance") or 0.0)
                moving_time_s = int(act.get("moving_time") or 0)
                elapsed_time_s = int(act.get("elapsed_time") or moving_time_s)
                elev_gain_m = float(act.get("total_elevation_gain") or 0.0)
                max_elev_m = float(act.get("elev_high") or 0.0)
                avg_cadence = float(act.get("average_cadence") or 0.0)

                # Hitung pace (menit/km)
                avg_pace_min_per_km = 0.0
                if distance_m > 0 and moving_time_s > 0:
                    avg_pace_min_per_km = (moving_time_s / 60.0) / (distance_m / 1000.0)

                # --- Ambil tanggal ---
                date_str = act.get("start_date_local") or act.get("start_date")

                # kalau kosong, fetch detail activity
                if not date_str and raw_id:
                    try:
                        detail = client.activity_detail(raw_id)
                        date_str = detail.get("start_date_local") or detail.get("start_date")
                    except Exception as e:
                        logging.warning(f"Gagal fetch detail activity {raw_id}: {e}")
                        date_str = None

                try:
                    if date_str:
                        date_val = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    else:
                        logging.warning(f"Activity {strava_id}: tidak ada start_date_local/start_date, fallback UTC now")
                        date_val = datetime.utcnow()
                except Exception:
                    logging.warning(f"Gagal parse tanggal: {date_str}, fallback UTC now")
                    date_val = datetime.utcnow()

                # --- Text representation untuk embedding ---
                tanggal_fmt = date_val.strftime("%d %B %Y %H:%M")
                text_repr = (
                    f"Atlet {firstname} {lastname} melakukan {act.get('sport_type') or 'aktivitas'} "
                    f"berjudul '{act.get('name') or 'Tanpa Judul'}' pada {tanggal_fmt}. "
                    f"Detail aktivitas: jarak {round(distance_m/1000, 2)} km, "
                    f"durasi {round(moving_time_s/60, 1)} menit, "
                    f"pace rata-rata {round(avg_pace_min_per_km, 2)} menit/km, "
                    f"cadence rata-rata {avg_cadence} langkah/menit, "
                    f"elevasi naik {elev_gain_m} m dengan ketinggian maksimum {max_elev_m} m."
                )

                try:
                    emb = embed_text(text_repr)  # 768-dim
                except Exception as e:
                    logging.error(f"Gagal bikin embedding: {e}")
                    emb = [0.0] * 768  # fallback kosong

                # --- Simpan activity ---
                activity = models.Activity(
                    strava_id=str(strava_id),
                    athlete_id=athlete.id,
                    club_id=club.id,
                    name=act.get("name"),
                    sport_type=act.get("sport_type"),
                    distance_m=distance_m,
                    moving_time_s=moving_time_s,
                    elapsed_time_s=elapsed_time_s,
                    elev_gain_m=elev_gain_m,
                    date=date_val,
                    embedding=emb if isinstance(emb, list) else emb.tolist(),
                )
                db.add(activity)
                saved += 1

            except Exception as e:
                logging.error(f"Gagal proses activity: {e}")
                logging.debug("Activity payload saat error: %s", json.dumps(act, indent=2))
                db.rollback()

        db.commit()
        page += 1

    return {"inserted": saved}
