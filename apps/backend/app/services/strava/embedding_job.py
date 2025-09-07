from sqlalchemy.orm import Session
from ... import models
from ..embeddings import embed_text

def generate_embeddings(db: Session, limit: int = 50):
    qs = db.query(models.ActivitySummary).filter(models.ActivitySummary.embedding == None).limit(limit).all()
    count = 0
    for s in qs:
        emb = embed_text(s.summary)
        # cast ke list of float64 biar aman
        s.embedding = [float(x) for x in emb]
        count += 1
    db.commit()
    return {"updated": count}
