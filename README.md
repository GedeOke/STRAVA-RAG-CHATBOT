# Apaan Yaa • Strava RAG Chatbot

Asisten tanya‑jawab (RAG) untuk komunitas lari “Apaan Yaa”, dibangun di atas FastAPI + ChromaDB dengan embedding Sentence Transformers, integrasi Google Sheets sebagai sumber data, serta opsi LLM (Groq/OpenAI). Fokusnya: jawaban natural namun tetap relevan dan berbasis data klub.

**Fitur Utama**
- Sinkronisasi data aktivitas dari Google Sheets → diindeks ke ChromaDB (1 dokumen per member).
- Retrieval konteks top‑K + penjawab LLM (Groq/OpenAI) dengan fallback deterministik.
- Intent khusus (deterministik):
  - Total jarak KM per member (opsional filter bulan/tahun)
  - Pertanyaan ambang “pernah ≥ N km?”
  - Perbandingan 2 member (opsional filter)
- Memori sesi ringan via `session_id` (member/bulan/tahun diteruskan antar pertanyaan).
- Frontend single page modern (HTML/JS) dengan Health badge, tombol Refresh, dan pengaturan API Base.

---

**Arsitektur**
- Backend (FastAPI)
  - Router: `backend/app/routers/{health_router.py,strava_router.py}`
  - Core: `backend/app/core/{config.py,logger.py,utils.py,memory.py}`
  - RAG: `backend/app/services/rag/{retriever.py,answerer.py,pipeline.py}`
  - Chroma: `backend/app/services/chroma/{db_client.py,manager.py,embeddings.py}`
  - Sheets: `backend/app/services/gsheet/sync.py`
- Frontend: `frontend/index.html` (single page, no build tool)

---

**Persiapan**
- Prasyarat:
  - Python 3.12+
  - Pip/venv
- Klon & environment:
  - Buat virtualenv: `python -m venv .venv` lalu aktivasi
  - Install deps: `pip install -r backend/requirements.txt`

**Konfigurasi Environment**
- Salin `backend/.env` (opsional) dan set variabel berikut (default aman):
  - CHROMA
    - `CHROMA_PATH=./db`
    - `CHROMA_COLLECTION=strava_club`
  - Google Sheets
    - `GSHEET_NAME=StravaClubData` (jika akses by name, butuh Drive API)
    - `GSHEET_TAB=ClubActivities`
    - `GSHEET_CRED_FILE=backend/credentials.json`
    - `GSHEET_ID=` (opsional; jika diisi, hanya perlu Sheets API, gunakan ID dari URL Sheet)
  - Embedding
    - `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2`
  - Server
    - `HOST=0.0.0.0`
    - `PORT=8000`
  - LLM (opsional)
    - `LLM_PROVIDER=groq` atau `openai` atau `none`
    - `GROQ_MODEL=llama-3.1-8b-instant`
    - `OPENAI_MODEL=gpt-4o-mini`

- Letakkan file kredensial service account Google di `backend/credentials.json` dan share Spreadsheet ke `client_email` pada file tersebut (Editor/Viewer). Jika pakai `GSHEET_ID`, cukup aktifkan Google Sheets API; tanpa ID dan akses by name butuh Google Drive API.

---

**Menjalankan Backend**
- Dari root repo:
  - `uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000`
- Endpoint dasar:
  - Health: `GET /health/`
  - Status Chroma: `GET /strava/status`
  - Refresh index (GSheet → Chroma): `POST /strava/refresh`
  - Tanya:
    - `GET /strava/ask` dengan query params:
      - `query` (wajib)
      - `with_answer` (bool, default false; aktifkan untuk pakai LLM / kalkulasi deterministik)
      - `member` (opsional; memaksa fokus ke member tertentu)
      - `month` (1–12, opsional)
      - `year` (YYYY, opsional)
      - `top_k` (default 5)
      - `session_id` (opsional; memori ringan per sesi)

Contoh:
- Refresh: `curl -X POST http://localhost:8000/strava/refresh`
- Tanya retriever saja: `curl "http://localhost:8000/strava/ask?query=ringkas%20aktivitas%20Yoga"`
- Full RAG: `curl "http://localhost:8000/strava/ask?query=total%20Lussy%20September&with_answer=true"`

---

**Frontend**
- File: `frontend/index.html`
- Buka langsung di browser atau via Live Server.
- Isi “API Base” (mis. `http://localhost:8000`). Health badge harus menunjukkan “API OK • …”.
- Form menyediakan:
  - Pertanyaan + filter (member/bulan/tahun/top‑K)
  - Session ID otomatis (untuk memori percakapan)
  - Tombol “Tanya”, “Bersihkan”, dan “Refresh Data”
- Jika API tidak mengembalikan JSON, UI akan menampilkan pesan debug dan cuplikan response.

Catatan CORS:
- Backend mengaktifkan CORS global wildcard. Jika frontend di https dan API http, browser dapat memblokir (mixed content). Gunakan http untuk keduanya saat dev.

---

**Alur Data (RAG)**
1) `POST /strava/refresh`: baca Google Sheets → susun teks per member → embedding → upsert ke Chroma (doc_id = member).
2) `GET /strava/ask`: 
   - normalize query, deteksi member dari query/param/memori.
   - retrieval fokus (by doc_id/where filter operator) → contexts.
   - answerer:
     - deterministic calc untuk total jarak, pertanyaan ambang (≥ N km), dan perbandingan dua member.
     - jika `with_answer=true` dan LLM aktif, bangun prompt system/user: gaya natural, playful, tetap faktual dan pakai [rujukan].
   - memori sesi diupdate (member/bulan/tahun) untuk percakapan lanjutan.

---

**Docker (Backend)**
- Build dari folder `backend/`:
  - `docker build -t apaan-yaa-backend ./backend`
- Run:
  - `docker run -p 8000:8000 -v %cd%/backend:/app --env-file backend/.env apaan-yaa-backend`
- Pastikan `backend/credentials.json` tersedia dalam container (bind mount).

---

**Troubleshooting**
- Health 404 di Live Server:
  - Pastikan “API Base” diarahkan ke `http://localhost:8000`, bukan origin Live Server.
- CORS/Failed to fetch:
  - Restart backend (CORS middleware aktif), cocokkan protokol (http/http), cek Response Headers `Access-Control-Allow-Origin: *`.
- Google API 403 (Drive API disabled):
  - Aktifkan Drive API bila akses by name, atau gunakan `GSHEET_ID` (cukup Sheets API).
- Kredensial tidak ditemukan:
  - Set `GSHEET_CRED_FILE` ke path yang benar (contoh: `backend/datasetxxx.json`).
- Koleksi campur/inkonsisten:
  - `python backend/reset_db.py` lalu `POST /strava/refresh`.
- Model embedding unduh lama:
  - Wajar di run pertama; cache di local env container.

---

**Keamanan & Git**
- Jangan commit kredensial atau `.env`. File `.gitignore` sudah di-set untuk mengabaikan:
  - `.env*`, `backend/credentials.json`, file dataset service account, `db/`, `.venv/`, `logs/`, dsb.

---

**Roadmap**
- Leaderboard (Top KM per bulan/tahun) + endpoint dan UI.
- Intent tambahan: terjauh, tercepat (pace), terlama (durasi), rekap mingguan.
- Reranking (cross-encoder) untuk hasil retrieval lebih tajam.
- Persisten memori sesi (mis. Redis) untuk deployment multi instance.

---

**Lisensi**
- Internal project untuk komunitas “Apaan Yaa”. Tambahkan lisensi sesuai kebutuhan.

**Kontak**
- Feedback/isu: buka issue di repo atau DM maintainer.
