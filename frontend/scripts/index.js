let sessionId = "session_" + Date.now();
let currentLeaderboardFilter = "week";

// Toggle Mobile Menu
function toggleMobileMenu() {
  document.getElementById("navLinks").classList.toggle("active");
}

// Smooth Scroll & Active Nav
function scrollToSection(id, evt) {
  const element = document.getElementById(id);
  const offset = 80;
  const bodyRect = document.body.getBoundingClientRect().top;
  const elementRect = element.getBoundingClientRect().top;
  const elementPosition = elementRect - bodyRect;
  const offsetPosition = elementPosition - offset;
  window.scrollTo({ top: offsetPosition, behavior: "smooth" });

  // Update active nav (fallback ke window.event bila evt tidak dikirim)
  const e = evt || window.event || null;
  const links = document.querySelectorAll(".nav-links a");
  links.forEach((a) => a.classList.remove("active"));
  if (e && e.target) {
    e.preventDefault?.();
    e.stopPropagation?.();
    e.target.classList.add("active");
  } else {
    // jika tidak ada event, aktifkan link sesuai id anchor
    links.forEach((a) => {
      if (a.getAttribute("href") === `#${id}`) a.classList.add("active");
    });
  }

  // Close mobile menu
  document.getElementById("navLinks").classList.remove("active");
}

// Check API Health
async function checkHealth() {
  const apiBase = document.getElementById("apiBase").value;
  try {
    const response = await fetch(`${apiBase}/health/`);
    if (response.ok) {
      document.getElementById("chatStatus").textContent = "API OK";
      loadInitialData();
    } else {
      document.getElementById("chatStatus").textContent = "API Error";
    }
  } catch (error) {
    document.getElementById("chatStatus").textContent = "Offline";
  }
}

// Load Initial Data
async function loadInitialData() {
  await loadMembers();
  await loadLeaderboard("month");
}

// Load Members (Mock data - replace with real API)
async function loadMembers() {
  const apiBase = document.getElementById("apiBase").value;
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  const url = `${apiBase}/strava/leaderboard?scope=month&year=${y}&month=${m}`;
  const grid = document.getElementById("membersGrid");
  grid.innerHTML = "";
  try {
    const res = await fetch(url);
    const data = await res.json();
    const list = data && data.leaderboard ? data.leaderboard : [];
    list.slice(0, 12).forEach((r) => {
      const name = r.member || r.name || "-";
      const total = (r.total_km ?? r.distance ?? 0).toFixed(2);
      const acts = r.activities ?? 0;
      const card = document.createElement("div");
      card.className = "member-card";
      card.innerHTML = `
                        <div class="member-avatar">${name.charAt(0)}</div>
                        <div class="member-name">${name}</div>
                        <div class="member-stats">
                            <div class="member-stat">
                                <span>Total Distance</span>
                                <span class="member-stat-value">${total} km</span>
                            </div>
                            <div class="member-stat">
                                <span>Activities</span>
                                <span class="member-stat-value">${acts}</span>
                            </div>
                        </div>`;
      grid.appendChild(card);
    });
    const totalKm = list.reduce((s, r) => s + (r.total_km ?? 0), 0);
    const totalAct = list.reduce((s, r) => s + (r.activities ?? 0), 0);
    document.getElementById("totalMembers").textContent = list.length;
    document.getElementById("totalDistance").textContent = totalKm.toFixed(0);
    document.getElementById("totalActivities").textContent = totalAct;
  } catch (e) {
    document.getElementById("totalMembers").textContent = "0";
    document.getElementById("totalDistance").textContent = "0";
    document.getElementById("totalActivities").textContent = "0";
  }
}

// Load Leaderboard (mock)
async function loadLeaderboard(period) {
  const apiBase = document.getElementById("apiBase").value;
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth() + 1;
  let url = `${apiBase}/strava/leaderboard?scope=${period}`;
  if (period === "month") url += `&year=${y}&month=${m}`;
  if (period === "year") url += `&year=${y}`;
  if (period === "week") {
    const temp = new Date(
      Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
    );
    const dayNum = temp.getUTCDay() || 7;
    temp.setUTCDate(temp.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(temp.getUTCFullYear(), 0, 1));
    const week = Math.ceil(((temp - yearStart) / 86400000 + 1) / 7);
    url += `&year=${y}&week=${week}`;
  }
  const content = document.getElementById("leaderboardContent");
  content.innerHTML = "";
  try {
    const res = await fetch(url);
    const data = await res.json();
    const list = data && data.leaderboard ? data.leaderboard : [];
    list.forEach((r, index) => {
      const rank = index + 1;
      const name = r.member || r.name || "-";
      const distance = (r.total_km ?? r.distance ?? 0).toFixed(2);
      const acts = r.activities ?? 0;
      let rankClass =
        rank === 1
          ? "gold"
          : rank === 2
          ? "silver"
          : rank === 3
          ? "bronze"
          : "";
      const row = document.createElement("div");
      row.className = "leaderboard-row";
      row.innerHTML = `
                        <div class="rank ${rankClass}">#${rank}</div>
                        <div class="runner-info">
                            <div class="runner-avatar">${name.charAt(0)}</div>
                            <div>${name}</div>
                        </div>
                        <div class="distance-value">${distance} km</div>
                        <div class="activities-col">${acts} runs</div>
                    `;
      content.appendChild(row);
    });
  } catch (e) {
    content.innerHTML = '<div class="muted">Gagal memuat leaderboard.</div>';
  }
  const btns = document.querySelectorAll(".filter-btn");
  btns.forEach((b) => b.classList.remove("active"));
  const map = { week: 0, month: 1, year: 2 };
  if (map[period] !== undefined && btns[map[period]])
    btns[map[period]].classList.add("active");
}

// Filter Leaderboard
function filterLeaderboard(period, btn) {
  currentLeaderboardFilter = period;
  document
    .querySelectorAll(".filter-btn")
    .forEach((b) => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  loadLeaderboard(period);
}

// Toggle Settings
function toggleSettings() {
  document.getElementById("settingsPanel").classList.toggle("active");
}

async function refreshData() {
  const apiBase = document.getElementById("apiBase").value;
  addMessage("bot", "Memperbarui data dari Google Sheets...");
  try {
    const response = await fetch(`${apiBase}/strava/refresh`, {
      method: "POST",
    });
    const data = await safeJson(response);
    if (response.ok) {
      const upd = (data && data.updated) ?? 0;
      const skp = (data && data.skipped) ?? 0;
      addMessage(
        "bot",
        `Data berhasil diperbarui. updated=${upd} skipped=${skp}`
      );
      await loadInitialData();
    } else {
      addMessage(
        "bot",
        `Gagal memperbarui data: ${data?.detail || "Unknown error"}`
      );
    }
  } catch (error) {
    addMessage("bot", "Koneksi ke API gagal. Pastikan backend berjalan.");
  }
  toggleSettings();
}

// Chat: enter to send
function handleKeyPress(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

// Chat: send message (COMPLETED)
async function sendMessage() {
  const input = document.getElementById("chatInput");
  const query = input.value.trim();
  if (!query) return;

  addMessage("user", query);
  input.value = "";
  showTyping();

  const apiBase = document.getElementById("apiBase").value;
  const member = document.getElementById("memberFilter").value;
  const month = document.getElementById("monthFilter").value;
  const year = document.getElementById("yearFilter").value;

  const params = new URLSearchParams({
    query: query,
    with_answer: "true",
    session_id: sessionId,
  });
  if (member) params.append("member", member);
  if (month) params.append("month", month);
  if (year) params.append("year", year);

  try {
    const response = await fetch(`${apiBase}/strava/ask?${params.toString()}`);
    const data = await safeJson(response);
    hideTyping();

    if (response.ok) {
      const text = renderAnswer(data);
      addMessage("bot", text);
    } else {
      addMessage(
        "bot",
        `❌ Error (${response.status}): ${data?.detail || "Permintaan gagal."}`
      );
    }
  } catch (err) {
    hideTyping();
    addMessage(
      "bot",
      "❌ Koneksi ke API gagal. Periksa URL API atau jaringanmu."
    );
  }
}

// Helper: render answer from backend payloads yang bervariasi
function renderAnswer(data) {
  if (!data) return "Tidak ada respons.";
  // Dukungan beberapa bentuk respon:
  const main =
    data.answer ||
    data.response ||
    data.message ||
    (typeof data === "string" ? data : "");

  // Tambahkan referensi jika ada
  let refs = "";
  const refArr = data.references || data.refs || data.sources || [];
  if (Array.isArray(refArr) && refArr.length) {
    const labels = refArr.map((r, i) => `[${i + 1}]`).join(" ");
    refs = `\n\nReferensi: ${labels}`;
  }
  return (main || "—") + refs;
}

// Helper: aman membaca JSON (hindari throw kalau bukan JSON)
async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

// UI: typing indicator
function showTyping() {
  const t = document.getElementById("typingIndicator");
  t.classList.add("active");
  scrollMessagesToBottom();
}
function hideTyping() {
  const t = document.getElementById("typingIndicator");
  t.classList.remove("active");
  scrollMessagesToBottom();
}

// UI: tambah pesan + auto scroll
function addMessage(who, text) {
  const wrap = document.createElement("div");
  wrap.className = `message ${who === "user" ? "user" : "bot"}`;
  wrap.innerHTML = escapeAndKeepBasicFormatting(text);
  const box = document.getElementById("chatMessages");
  box.appendChild(wrap);
  scrollMessagesToBottom();
}

function scrollMessagesToBottom() {
  const box = document.getElementById("chatMessages");
  box.scrollTop = box.scrollHeight;
}

// Minimal sanitizer (bolehkan line break & link polos)
function escapeAndKeepBasicFormatting(s) {
  if (!s) return "";
  const esc = s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // hyperlink otomatis (http/https)
  const linked = esc.replace(
    /(https?:\/\/[^\s]+)/g,
    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>'
  );
  // ganti \n jadi <br>
  return linked.replace(/\n/g, "<br>");
}

// Inisialisasi saat load
window.addEventListener("DOMContentLoaded", () => {
  // Pastikan tombol filter punya state aktif sesuai default
  loadInitialData();
  checkHealth();

  // Sinkronkan tombol filter agar pakai parameter btn bila diklik
  document.querySelectorAll(".filter-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      document
        .querySelectorAll(".filter-btn")
        .forEach((b) => b.classList.remove("active"));
      e.currentTarget.classList.add("active");
    });
  });
});
