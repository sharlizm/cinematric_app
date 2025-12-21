import math
import re
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st

# CONFIG + STYLE
st.set_page_config(
    page_title="Cinematric (Netflix-style)",
    page_icon="🎬",
    layout="wide",
)

# LINEAR SEARCH
def linear_search_movies(data: list, query: str, limit: int = 10):
    # O(n)
    query = query.lower().strip()
    results = []

    for row in data:
        title = (row.get("title_clean") or "").lower()
        if query in title:
            results.append(row)
        if len(results) >= limit:
            break

    return results

# QUICK SORT
def quick_sort_movies(arr, key, descending=True):
    if len(arr) <= 1:
        return arr

    pivot = arr[len(arr) // 2]
    pivot_value = pivot.get(key) or 0

    left = []
    middle = []
    right = []

    for item in arr:
        value = item.get(key) or 0
        if value < pivot_value:
            left.append(item)
        elif value > pivot_value:
            right.append(item)
        else:
            middle.append(item)

    if descending:
        return (
            quick_sort_movies(right, key, descending)
            + middle
            + quick_sort_movies(left, key, descending)
        )
    else:
        return (
            quick_sort_movies(left, key, descending)
            + middle
            + quick_sort_movies(right, key, descending)
        )

CUSTOM_CSS = """
<style>
.block-container { padding-top: 1.1rem; padding-bottom: 2rem; }

/* --- Netflix-ish vibe --- */
.cm-hero {
  border-radius: 18px;
  padding: 18px 18px;
  border: 1px solid rgba(255,255,255,0.10);
  background: linear-gradient(180deg, rgba(255,255,255,0.06), rgba(255,255,255,0.02));
}
.cm-pill {
  display:inline-block; padding: 6px 10px; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.05);
  font-size: 12px; margin-right: 6px; margin-bottom: 6px;
}
.cm-muted { opacity: 0.80; }
.cm-card {
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(255,255,255,0.03);
  padding: 10px 10px 12px 10px;
}
.cm-title {
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-top: 8px;
  margin-bottom: 4px;
}
.cm-sub { font-size: 12px; opacity: 0.85; margin-bottom: 8px; }
.cm-hr { height:1px; background:rgba(255,255,255,0.10); margin:12px 0; }

img { border-radius: 12px; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# LOAD DATA
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1Rvj1KhbgFOrKQFz54IbssPmEUvtd5IGyXPR9f7WLuS0/export?format=csv"

@st.cache_data(show_spinner=False)
def load_data(url: str) -> pd.DataFrame:
    df = pd.read_csv(url)

    # Cols
    expected = [
        "title","genre","subgenre","rating","duration","year","vote_count","popularity",
        "budget","revenue","imdb_id","homepage","overview","tagline","director","cast",
        "keywords","release_date","production_companies","budget_adj","revenue_adj"
    ]
    for c in expected:
        if c not in df.columns:
            df[c] = None

    # Numeric
    for c in ["rating","duration","year","vote_count","popularity","budget","revenue","budget_adj","revenue_adj"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Strings
    for c in ["title","genre","subgenre","imdb_id","homepage","overview","tagline","director","cast","keywords","release_date","production_companies"]:
        df[c] = df[c].astype(str).replace({"nan": ""}).fillna("")

    df["title_clean"] = df["title"].str.strip()
    df["genre_clean"] = df["genre"].str.strip()
    df["subgenre_clean"] = df["subgenre"].str.strip()

    # finance
    df["profit"] = df["revenue"] - df["budget"]
    df["roi"] = df.apply(lambda r: (r["revenue"]/r["budget"]) if (pd.notna(r["budget"]) and r["budget"] and pd.notna(r["revenue"])) else math.nan, axis=1)

    return df

movies_df = load_data(SHEET_CSV_URL)


# HASH TABLE
@st.cache_data(show_spinner=False)
def build_movie_hash(df: pd.DataFrame):
    # buat lookup imdb_id biar dapet data film
    table = {}
    for row in df.to_dict(orient="records"):
        imdb = (row.get("imdb_id") or "").strip()
        if imdb:
            table[imdb] = row
    return table
movie_hash = build_movie_hash(movies_df)


# POSTERS & DETAILS
import os

TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if not TMDB_API_KEY:
    try:
        TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
    except Exception:
        TMDB_API_KEY = None

TMDB_BASE = "https://api.themoviedb.org/3"

# HEADER
def tmdb_headers():
    return {"Accept": "application/json"}

@st.cache_data(show_spinner=False)
def tmdb_get_configuration(api_key: str):
    url = f"{TMDB_BASE}/configuration"
    r = requests.get(url, params={"api_key": api_key}, headers=tmdb_headers(), timeout=12)
    r.raise_for_status()
    return r.json()

@st.cache_data(show_spinner=False)
def tmdb_find_movie_id_by_imdb(api_key: str, imdb_id: str):
    # ubah imdb_id jadi tmdb movie_id lewat endpoint /find
    imdb_id = (imdb_id or "").strip()
    if not imdb_id:
        return None
    if not re.match(r"^tt\d{5,}$", imdb_id):
        return None

    url = f"{TMDB_BASE}/find/{imdb_id}"
    r = requests.get(
        url,
        params={"api_key": api_key, "external_source": "imdb_id"},
        headers=tmdb_headers(),
        timeout=12,
    )
    if r.status_code != 200:
        return None

    data = r.json()
    results = data.get("movie_results") or []
    if not results:
        return None
    return results[0].get("id")

@st.cache_data(show_spinner=False)
def tmdb_movie_details(api_key: str, movie_id: int):
    # ambil detail, video, credit, dan film serupa lewat sekali call
    url = f"{TMDB_BASE}/movie/{movie_id}"
    r = requests.get(
        url,
        params={
            "api_key": api_key,
            "append_to_response": "videos,credits,similar",
        },
        headers=tmdb_headers(),
        timeout=12,
    )
    if r.status_code != 200:
        return None
    return r.json()

def build_img_url(conf, path: str, size: str = "w500"):
    if not conf or not path:
        return None
    images = conf.get("images", {})
    base = images.get("secure_base_url") or images.get("base_url")
    if not base:
        return None
    return f"{base}{size}{path}"

def imdb_url(imdb_id: str) -> str:
    imdb_id = (imdb_id or "").strip()
    if not imdb_id or not re.match(r"^tt\d{5,}$", imdb_id):
        return ""
    return f"https://www.imdb.com/title/{imdb_id}/"

def youtube_url_from_tmdb_videos(videos_block: dict) -> str:
    # pilih trailer jika ada dari TMDb videos (Yt, tipe Trailer/Teaser)
    if not videos_block:
        return ""
    results = videos_block.get("results") or []
    yt = [v for v in results if v.get("site") == "YouTube"]
    if not yt:
        return ""
    # prefer Trailer
    trailers = [v for v in yt if v.get("type") == "Trailer"]
    pick = trailers[0] if trailers else yt[0]
    key = pick.get("key")
    return f"https://www.youtube.com/watch?v={key}" if key else ""


# HELPER: WEIGHTED RATING
def weighted_rating(row, m, C):
    v = row.get("vote_count")
    R = row.get("rating")
    if pd.isna(v) or pd.isna(R):
        return math.nan
    v = float(v); R = float(R)
    return (v/(v+m))*R + (m/(v+m))*C



# SIDEBAR: GLOBAL FILTERS + NAV
st.title("🎬 Cinematric : Sistem Analisis & Dashboard Film Menggunakan Algoritma Struktur Data")

# ===== HANDLE NAVIGATION FLAG (HARUS DI ATAS RADIO) =====
if st.session_state.get("go_detail"):
    st.session_state.menu = "Detail (Direct)"
    st.session_state.go_detail = False

with st.sidebar:
    st.markdown("## 🎛️ Global Filters")

    year_min = int(movies_df["year"].dropna().min()) if movies_df["year"].notna().any() else 1900
    year_max = int(movies_df["year"].dropna().max()) if movies_df["year"].notna().any() else 2025
    yr = st.slider("Tahun rilis", year_min, year_max, (max(year_min, year_max - 25), year_max))

    rr = st.slider("Rating", 0.0, 10.0, (6.0, 10.0), 0.1)
    dr = st.slider("Durasi (menit)", 0, int(max(60, movies_df["duration"].dropna().max() if movies_df["duration"].notna().any() else 240)), (0, 240))

    all_genres = sorted([g for g in movies_df["genre_clean"].unique().tolist() if g])
    sel_genres = st.multiselect("Genre", all_genres, default=all_genres[:8] if len(all_genres) > 8 else all_genres)

    min_votes = st.number_input("Minimal vote_count", min_value=0, value=0, step=100)

    st.markdown("---")
    menu = st.radio(
        "Menu",
        ["Home", "Detail", "Analytics"],
        key = "menu"
    )

# Apply filters
filtered_df = movies_df.copy()
filtered_df = filtered_df[
    (filtered_df["year"].fillna(-1).between(yr[0], yr[1])) &
    (filtered_df["rating"].fillna(-1).between(rr[0], rr[1])) &
    (filtered_df["duration"].fillna(-1).between(dr[0], dr[1])) &
    (filtered_df["vote_count"].fillna(0) >= min_votes)
]
if sel_genres:
    filtered_df = filtered_df[filtered_df["genre_clean"].isin(sel_genres)]

# TMDb readiness check
if not TMDB_API_KEY:
    st.warning("TMDb belum aktif, perlu set **TMDB_API_KEY**.")

# STATE: SELECTED MOVIE
if "selected_imdb" not in st.session_state:
    st.session_state.selected_imdb = ""

# Read query param
qp = st.query_params
if "imdb" in qp and qp["imdb"]:
    st.session_state.selected_imdb = qp["imdb"]

def set_selected_imdb(imdb_id: str):
    st.session_state.selected_imdb = imdb_id
    st.query_params["imdb"] = imdb_id

# PAGE: HOME
if menu == "Home":
    # KPIs
    total = len(filtered_df)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Films (Filtered)", f"{total:,}")
    c2.metric("Avg Rating", f"{filtered_df['rating'].mean():.2f}" if total else "—")
    c3.metric("Median Rating", f"{filtered_df['rating'].median():.2f}" if total else "—")
    c4.metric("Top Rated (≥8)", f"{(filtered_df['rating']>=8).mean()*100:.1f}%" if total else "—")

    st.markdown('<div class="cm-hr"></div>', unsafe_allow_html=True)

    # Ranking like "Trending"
    df_rank = filtered_df.copy()
    C = float(df_rank["rating"].mean()) if df_rank["rating"].notna().any() else 0.0
    m = float(df_rank["vote_count"].quantile(0.70)) if df_rank["vote_count"].notna().any() else 0.0
    df_rank["wr"] = df_rank.apply(lambda r: weighted_rating(r, m=m, C=C), axis=1)

    sort_mode = st.selectbox(
        "Sort style",
        ["Trending (popularity)", "Top picks (weighted rating)", "Newest", "Most voted"],
        index=1
    )
    # ubah DataFrame -> list of dict
    movie_list = df_rank.to_dict(orient="records")


    # sorting pakai Quick Sort (rekursif)
    if sort_mode == "Trending (popularity)":
        movie_list = quick_sort_movies(movie_list, key="popularity")

    elif sort_mode == "Top picks (weighted rating)":
        movie_list = quick_sort_movies(movie_list, key="wr")

    elif sort_mode == "Newest":
        movie_list = quick_sort_movies(movie_list, key="year")

    else:  # Most voted
        movie_list = quick_sort_movies(movie_list, key="vote_count")


    # Search bar (LINEAR SEARCH)
    q = st.text_input("Search title", placeholder="ketik judul film…")
    if q:
        movie_list = linear_search_movies(movie_list, q, limit=len(movie_list))


    # Prepare TMDb config once
    conf = None
    if TMDB_API_KEY:
        try:
            conf = tmdb_get_configuration(TMDB_API_KEY)
        except Exception:
            conf = None

    st.markdown("### 🍿 Browse")

    total_movies = len(movie_list)

    if total_movies == 0:
        st.info("Tidak ada film untuk ditampilkan setelah filter / search.")
        st.stop()
    else:
        # Grid settings
        cols = st.slider("Jumlah kolom poster", 4, 10, 7)
        per_page = cols * 4

        page = st.number_input(
            "Halaman",
            min_value=1,
            max_value=max(1, math.ceil(total_movies / per_page)),
            value=1,
            step=1
        )
        start = (page - 1) * per_page
        end = start + per_page


        grid_df = pd.DataFrame(movie_list[start:end])

        # Build poster URLs (cache results by imdb_id)
        def poster_for_imdb(imdb_id: str):
            if not TMDB_API_KEY or not conf:
                return None
            try:
                mid = tmdb_find_movie_id_by_imdb(TMDB_API_KEY, imdb_id)
                if not mid:
                    return None
                d = tmdb_movie_details(TMDB_API_KEY, mid)
                if not d:
                    return None
                return build_img_url(conf, d.get("poster_path"), "w342")  # nice grid size
            except Exception:
                return None

        # Render grid
        rows = math.ceil(len(grid_df) / cols)
        idx = 0
        for _ in range(rows):
            col_list = st.columns(cols, gap="small")
            for c in col_list:
                if idx >= len(grid_df):
                    break
                row = grid_df.iloc[idx].to_dict()
                idx += 1

                title = row.get("title_clean", "")
                imdb_id = row.get("imdb_id", "").strip()
                rating = row.get("rating", math.nan)
                year = row.get("year", math.nan)

                poster_url = poster_for_imdb(imdb_id) if imdb_id else None

                with c:
                    st.markdown('<div class="cm-card">', unsafe_allow_html=True)

                    if poster_url:
                        st.image(poster_url, use_container_width=True)
                    else:
                        # fallback placeholder
                        st.image(
                            "https://via.placeholder.com/342x513.png?text=No+Poster",
                            use_container_width=True
                        )

                    st.markdown(f'<div class="cm-title">{title}</div>', unsafe_allow_html=True)
                    sub = f"⭐ {rating:.1f}" if pd.notna(rating) else "⭐ —"
                    sub += f"  •  📅 {int(year)}" if pd.notna(year) else ""
                    st.markdown(f'<div class="cm-sub">{sub}</div>', unsafe_allow_html=True)

                    # Click -> detail
                    if st.button("Open", key=f"open_{start}_{idx}_{imdb_id or title}"):
                        if imdb_id:
                            set_selected_imdb(imdb_id)
                            st.session_state.go_detail = True  # 👈 pindah menu
                            st.rerun()

                        else:
                            st.warning("Film ini tidak punya imdb_id di dataset, tidak bisa mapping ke TMDb")

                    st.markdown("</div>", unsafe_allow_html=True)

    st.caption("Tip: klik poster untuk masuk detail. Jika poster kosong, TMDb tidak punya data.")


# PAGE: DETAIL
elif menu == "Detail":

    # Ambil imdb_id terpilih dari state
    pick = st.session_state.selected_imdb


    # DETAIL PAGE — SEARCH MODE
    st.subheader("🔍 Cari Film")

    query = st.text_input(
        "Ketik judul film",
        placeholder="contoh: avengers, harry potter, inception"
    )

    dataset_list = movies_df.to_dict(orient="records")
    results = linear_search_movies(dataset_list, query, limit=8)


    if query and not results:
        st.warning("Tidak ada film yang cocok di dataset.")

    if results:
        for r in results:
            title = r.get("title_clean")
            year = r.get("year")
            rating = r.get("rating")
            imdb_id = r.get("imdb_id")


            cols = st.columns([4, 1])
            with cols[0]:
                st.markdown(
                    f"**{title}** "
                    f"({int(year) if pd.notna(year) else '—'})  \n"
                    f"⭐ {rating:.1f}" if pd.notna(rating) else "⭐ —"
                )
            with cols[1]:
                if st.button("Open", key=f"open_search_{imdb_id}_{title}"):
                    if imdb_id:
                        set_selected_imdb(imdb_id)
                        st.session_state.go_detail = True   # 👈 FLAG
                        st.rerun()
                    else:
                        st.warning("Film ini tidak punya imdb_id di dataset.")

    if not pick:
        st.info("Pilih film dulu.")
        st.stop()


    # Pull dataset row (HASH TABLE - O(1))
    ds = movie_hash.get((pick or "").strip(), {})

    if menu == "Detail":
        if not pick:
            st.info("Pilih film dulu.")
        else:
            if not TMDB_API_KEY:
                st.error("TMDb API key belum diset, jadi poster/detail tidak bisa diambil.")
            else:
                # Get TMDb info
                conf = None
                try:
                    conf = tmdb_get_configuration(TMDB_API_KEY)
                except Exception:
                    conf = None

                tmdb_id = tmdb_find_movie_id_by_imdb(TMDB_API_KEY, pick)
                if not tmdb_id:
                    st.error("Gagal mapping TMDb untuk imdb_id ini.")
                else:
                    details = tmdb_movie_details(TMDB_API_KEY, tmdb_id)
                    if not details:
                        st.error("Gagal mengambil detail TMDb.")
                    else:
                        # Hero
                        backdrop = build_img_url(conf, details.get("backdrop_path"), "w1280") if conf else None
                        poster = build_img_url(conf, details.get("poster_path"), "w500") if conf else None

                        left, right = st.columns([1.0, 2.2], gap="large")

                        with left:
                            if poster:
                                st.image(poster, use_container_width=True)
                            else:
                                st.image("https://via.placeholder.com/500x750.png?text=No+Poster", use_container_width=True)

                        with right:
                            st.markdown('<div class="cm-hero">', unsafe_allow_html=True)

                            title = details.get("title") or ds.get("title_clean") or "Untitled"
                            tagline = details.get("tagline") or ds.get("tagline") or ""
                            overview = details.get("overview") or ds.get("overview") or ""

                            tmdb_rating = details.get("vote_average")
                            tmdb_votes = details.get("vote_count")
                            runtime = details.get("runtime") or ds.get("duration")
                            release_date = details.get("release_date") or ds.get("release_date")
                            genres = [g.get("name") for g in (details.get("genres") or []) if g.get("name")]

                            st.markdown(f"## {title}")
                            if tagline:
                                st.markdown(f"<span class='cm-muted'>{tagline}</span>", unsafe_allow_html=True)

                            pills = []
                            if tmdb_rating is not None:
                                pills.append(f"⭐ TMDb {tmdb_rating:.1f}")
                            if tmdb_votes is not None:
                                pills.append(f"🗳️ {tmdb_votes:,} votes")
                            if runtime and not (isinstance(runtime, float) and math.isnan(runtime)):
                                pills.append(f"⏱️ {int(runtime)} min")
                            if release_date:
                                pills.append(f"📅 {release_date}")
                            for p in pills:
                                st.markdown(f"<span class='cm-pill'>{p}</span>", unsafe_allow_html=True)

                            if genres:
                                st.markdown(" ".join([f"<span class='cm-pill'>🎭 {g}</span>" for g in genres]), unsafe_allow_html=True)

                            st.markdown('<div class="cm-hr"></div>', unsafe_allow_html=True)
                            st.write(overview if overview else "Tidak ada overview.")

                            # Links
                            ytb = youtube_url_from_tmdb_videos(details.get("videos") or {})
                            imdb_link = imdb_url(pick)
                            trailer_search = f"https://www.google.com/search?q={quote_plus(title + ' official trailer')}"

                            link_row = []
                            if ytb:
                                link_row.append(f"▶️ [Watch Trailer]({ytb})")
                            else:
                                link_row.append(f"▶️ [Search Trailer]({trailer_search})")
                            if imdb_link:
                                link_row.append(f"🎬 [IMDb]({imdb_link})")
                            homepage = details.get("homepage") or ds.get("homepage")
                            if homepage and str(homepage).startswith("http"):
                                link_row.append(f"🏠 [Homepage]({homepage})")

                            st.markdown(" • ".join(link_row))
                            st.markdown("</div>", unsafe_allow_html=True)

                        if backdrop:
                            st.image(backdrop, use_container_width=True, caption="Backdrop")

                        # Credits
                        credits = details.get("credits") or {}
                        cast = credits.get("cast") or []
                        crew = credits.get("crew") or []

                        director = ""
                        for person in crew:
                            if person.get("job") == "Director":
                                director = person.get("name") or ""
                                break

                        st.markdown("### 👥 Cast & Crew")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("Director", director or (ds.get("director") or "—"))
                        c2.metric("Dataset Rating", f"{ds.get('rating'):.2f}" if pd.notna(ds.get("rating")) else "—")
                        c3.metric("Dataset Votes", f"{int(ds.get('vote_count')):,}" if pd.notna(ds.get("vote_count")) else "—")

                        # Cast grid (top 12)
                        st.markdown("#### Top Cast")
                        conf_ok = conf is not None
                        top_cast = cast[:12]
                        cc = st.columns(6, gap="small")
                        for i, person in enumerate(top_cast):
                            with cc[i % 6]:
                                name = person.get("name") or "—"
                                character = person.get("character") or ""
                                profile_path = person.get("profile_path")
                                img = build_img_url(conf, profile_path, "w185") if (conf_ok and profile_path) else None
                                if img:
                                    st.image(img, use_container_width=True)
                                else:
                                    st.image("https://via.placeholder.com/185x278.png?text=No+Photo", use_container_width=True)
                                st.caption(f"**{name}**\n\n{character}")

                        # Similar movies (poster row)
                        similar = (details.get("similar") or {}).get("results") or []
                        st.markdown("### 🎞️ Similar Movies (from TMDb)")
                        if not similar:
                            st.info("TMDb tidak ditemukan film serupa.")
                        else:
                            # show as horizontal-ish grid
                            sim_cols = st.columns(8, gap="small")
                            for i, sm in enumerate(similar[:16]):
                                with sim_cols[i % 8]:
                                    sp = sm.get("poster_path")
                                    sim_title = sm.get("title") or ""
                                    sim_img = build_img_url(conf, sp, "w342") if (conf_ok and sp) else None
                                    if sim_img:
                                        st.image(sim_img, use_container_width=True)
                                    else:
                                        st.image("https://via.placeholder.com/342x513.png?text=No+Poster", use_container_width=True)
                                    st.caption(sim_title)

                        st.markdown("---")
                        with st.expander("📦 Data dari dataset"):
                            show_cols = ["title","genre","subgenre","rating","duration","year","vote_count","popularity","budget","revenue","profit","roi","director","cast","keywords"]
                            st.dataframe(pd.DataFrame([ds]).reindex(columns=show_cols), use_container_width=True)


# PAGE: ANALYTICS
if menu == "Analytics":
    st.subheader("📊 Analytics")

    if len(filtered_df) == 0:
        st.warning("Tidak ada data setelah filter.")
    else:
        tab1, tab2, tab3 = st.tabs(["Tren", "Genre", "Finance"])

        with tab1:
            st.markdown("#### Rating rata-rata per tahun")
            ts = (
                filtered_df.dropna(subset=["year", "rating"])
                .groupby("year", as_index=False)["rating"].mean()
                .sort_values("year")
            )
            if len(ts) > 1:
                st.line_chart(ts.set_index("year"))
            else:
                st.info("Data tren tidak cukup.")

            st.markdown("#### Distribusi rating")
            dist = filtered_df["rating"].dropna().round(1).value_counts().sort_index()
            if len(dist) > 0:
                st.bar_chart(dist)
            else:
                st.info("Tidak ada rating.")


        with tab2:
            import altair as alt

            st.markdown("#### Top genre by count")

            g = (
                filtered_df["genre_clean"]
                .value_counts()
                .head(10)
                .sort_values(ascending=True)   
                .reset_index()
            )

            g.columns = ["Genre", "Jumlah Film"]

            if len(g) > 0:
                chart = (
                    alt.Chart(g)
                    .mark_bar()
                    .encode(
                        x=alt.X("Jumlah Film:Q", title="Jumlah Film"),
                        y=alt.Y("Genre:N", sort=None, title="Genre"),
                        tooltip=["Genre", "Jumlah Film"]
                    )
                    .properties(height=350)
                )
                st.altair_chart(chart, use_container_width=True)
            else:
                st.info("Tidak ada genre.")



            st.markdown("#### Genre rating terbaik (min 10 film)")
            g2 = (
                filtered_df.dropna(subset=["rating"])
                .groupby("genre_clean")
                .agg(n=("title_clean", "count"), avg=("rating", "mean"))
                .reset_index()
            )
            g2 = g2[g2["n"] >= 10].sort_values("avg", ascending=False).head(12)
            if len(g2) > 0:
                st.dataframe(g2, use_container_width=True)
            else:
                st.caption("Belum ada genre ≥ 10 film setelah filter.")

        with tab3:
            st.markdown("#### Top profit")
            fin = filtered_df.dropna(subset=["budget", "revenue"]).copy()
            fin = fin[(fin["budget"] > 0) & (fin["revenue"] > 0)]
            if len(fin) == 0:
                st.info("Data finansial tidak cukup.")
            else:
                fin["profit"] = fin["revenue"] - fin["budget"]
                fin["roi"] = fin["revenue"] / fin["budget"]
                st.dataframe(
                    fin.sort_values("profit", ascending=False)[
                        ["title","budget","revenue","profit","roi","year","genre","rating","vote_count"]
                    ].head(20),
                    use_container_width=True
                )

    st.download_button(
        "⬇️ Download filtered CSV",
        data=filtered_df.to_csv(index=False).encode("utf-8"),
        file_name="cinematric_filtered.csv",
        mime="text/csv"
    )

st.caption("Cinematric - Netflix-style grid via TMDb")
