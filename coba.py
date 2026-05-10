import math
import re
from urllib.parse import quote_plus

import numpy as np
import pandas as pd
import requests
import streamlit as st

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="Cinematric AI",
    page_icon="🎬",
    layout="wide",
)

# =========================================================
# CUSTOM CSS (MODERN NETFLIX STYLE)
# =========================================================

CUSTOM_CSS = """
<style>

html, body, [class*="css"] {
    background-color: #0b0f1a;
    color: white;
    font-family: 'Inter', sans-serif;
}

/* remove top spacing */
.block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
}

/* HERO */
.hero {
    position: relative;
    border-radius: 24px;
    overflow: hidden;
    margin-bottom: 2rem;
}

.hero-overlay {
    position: absolute;
    inset: 0;
    background:
        linear-gradient(
            90deg,
            rgba(0,0,0,0.92) 15%,
            rgba(0,0,0,0.55) 45%,
            rgba(0,0,0,0.15) 100%
        );
}

.hero-content {
    position: absolute;
    bottom: 40px;
    left: 40px;
    width: 45%;
    z-index: 10;
}

.hero-title {
    font-size: 52px;
    font-weight: 800;
    line-height: 1;
    margin-bottom: 1rem;
}

.hero-sub {
    color: rgba(255,255,255,0.75);
    font-size: 16px;
    line-height: 1.6;
}

/* SECTION */
.section-title {
    font-size: 26px;
    font-weight: 700;
    margin-top: 2rem;
    margin-bottom: 1rem;
}

/* CARD */
.movie-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 18px;
    overflow: hidden;
    transition: all 0.25s ease;
}

.movie-card:hover {
    transform: scale(1.03);
    border: 1px solid rgba(255,255,255,0.16);
}

.movie-title {
    font-weight: 700;
    font-size: 15px;
    margin-top: 10px;
}

.movie-sub {
    color: rgba(255,255,255,0.72);
    font-size: 12px;
    margin-bottom: 10px;
}

/* PILLS */
.pill {
    display:inline-block;
    padding:6px 12px;
    border-radius:999px;
    background:rgba(255,255,255,0.08);
    border:1px solid rgba(255,255,255,0.08);
    margin-right:8px;
    margin-bottom:8px;
    font-size:12px;
}

/* BUTTON */
.stButton > button {
    width: 100%;
    border-radius: 12px;
    border: none;
    background: #e50914;
    color: white;
    font-weight: 700;
    padding: 0.6rem 1rem;
}

.stButton > button:hover {
    background: #ff2b36;
}

/* INPUT */
.stTextInput input {
    background: rgba(255,255,255,0.05);
    border-radius: 14px;
    border: 1px solid rgba(255,255,255,0.08);
    color: white;
}

</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# =========================================================
# DATA
# =========================================================

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1Rvj1KhbgFOrKQFz54IbssPmEUvtd5IGyXPR9f7WLuS0/export?format=csv"


@st.cache_data(show_spinner=False)
def load_data(url):
    df = pd.read_csv(url)

    needed = [
        "title",
        "genre",
        "overview",
        "keywords",
        "cast",
        "director",
        "vote_count",
        "rating",
        "popularity",
        "year",
        "imdb_id",
    ]

    for c in needed:
        if c not in df.columns:
            df[c] = ""

    numeric_cols = [
        "vote_count",
        "rating",
        "popularity",
        "year",
    ]

    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    text_cols = [
        "title",
        "genre",
        "overview",
        "keywords",
        "cast",
        "director",
        "imdb_id",
    ]

    for c in text_cols:
        df[c] = df[c].fillna("").astype(str)

    df["title_clean"] = df["title"].str.strip()

    return df


movies_df = load_data(SHEET_CSV_URL)

# =========================================================
# RECOMMENDATION ENGINE
# =========================================================

movies_df["content"] = (
    movies_df["genre"] + " " +
    movies_df["overview"] + " " +
    movies_df["keywords"] + " " +
    movies_df["cast"] + " " +
    movies_df["director"]
)

tfidf = TfidfVectorizer(stop_words="english")

tfidf_matrix = tfidf.fit_transform(movies_df["content"])

cosine_sim = cosine_similarity(tfidf_matrix, tfidf_matrix)

indices = pd.Series(
    movies_df.index,
    index=movies_df["title_clean"]
).drop_duplicates()


# =========================================================
# WEIGHTED RATING
# =========================================================

def weighted_rating(row, m, C):

    v = row["vote_count"]
    R = row["rating"]

    return (v / (v + m) * R) + (m / (m + v) * C)


C = movies_df["rating"].mean()
m = movies_df["vote_count"].quantile(0.75)

movies_df["weighted_score"] = movies_df.apply(
    lambda x: weighted_rating(x, m, C),
    axis=1
)


# =========================================================
# TMDB
# =========================================================

TMDB_API_KEY = st.secrets["TMDB_API_KEY"]

TMDB_BASE = "https://api.themoviedb.org/3"


@st.cache_data(show_spinner=False)
def tmdb_get(path, params={}):
    url = f"{TMDB_BASE}/{path}"

    params["api_key"] = TMDB_API_KEY

    r = requests.get(url, params=params)

    if r.status_code != 200:
        return {}

    return r.json()


@st.cache_data(show_spinner=False)
def get_poster(imdb_id):

    if not imdb_id:
        return None

    find = tmdb_get(
        f"find/{imdb_id}",
        {"external_source": "imdb_id"}
    )

    results = find.get("movie_results", [])

    if not results:
        return None

    poster = results[0].get("poster_path")

    if not poster:
        return None

    return f"https://image.tmdb.org/t/p/w500{poster}"


@st.cache_data(show_spinner=False)
def get_backdrop(imdb_id):

    if not imdb_id:
        return None

    find = tmdb_get(
        f"find/{imdb_id}",
        {"external_source": "imdb_id"}
    )

    results = find.get("movie_results", [])

    if not results:
        return None

    backdrop = results[0].get("backdrop_path")

    if not backdrop:
        return None

    return f"https://image.tmdb.org/t/p/original{backdrop}"


# =========================================================
# HYBRID RECOMMENDATION
# =========================================================

def hybrid_recommendation(title, top_n=12):

    if title not in indices:
        return pd.DataFrame()

    idx = indices[title]

    sim_scores = list(enumerate(cosine_sim[idx]))

    sim_scores = sorted(
        sim_scores,
        key=lambda x: x[1],
        reverse=True
    )

    sim_scores = sim_scores[1:top_n + 20]

    movie_indices = [i[0] for i in sim_scores]

    recs = movies_df.iloc[movie_indices].copy()

    recs["similarity"] = [i[1] for i in sim_scores]

    # HYBRID SCORE
    recs["final_score"] = (
        recs["similarity"] * 0.6 +
        (recs["weighted_score"] / 10) * 0.3 +
        (recs["popularity"] / recs["popularity"].max()) * 0.1
    )

    recs = recs.sort_values(
        "final_score",
        ascending=False
    )

    return recs.head(top_n)


# =========================================================
# SEARCH
# =========================================================

def search_movies(query):

    query = query.lower()

    results = movies_df[
        movies_df["title_clean"]
        .str.lower()
        .str.contains(query)
    ]

    return results.head(12)


# =========================================================
# SESSION STATE
# =========================================================

if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = "Interstellar"

selected_movie = st.session_state.selected_movie

# =========================================================
# HERO
# =========================================================

hero_movie = movies_df.sort_values(
    "popularity",
    ascending=False
).iloc[0]

hero_backdrop = get_backdrop(hero_movie["imdb_id"])

if hero_backdrop:

    st.image(
        hero_backdrop,
        use_container_width=True
    )

    st.markdown(
        f"""
        # 🎬 {hero_movie["title"]}

        AI-Powered Hybrid Recommendation System  
        inspired by Netflix recommendation architecture.

        Discover movies using:
        - Content-Based Recommendation
        - Hybrid Recommendation
        - Cosine Similarity
        - Popularity Scoring
        """,
    )

else:

    st.title("🎬 Cinematric AI")

    st.write(
        "AI-Powered Hybrid Recommendation System"
    )

# =========================================================
# SEARCH BAR
# =========================================================

st.markdown(
    '<div class="section-title">🔎 Search Movies</div>',
    unsafe_allow_html=True
)

query = st.text_input(
    "",
    placeholder="Search movies..."
)

if query:

    search_result = search_movies(query)

    cols = st.columns(6)

    for idx, (_, row) in enumerate(search_result.iterrows()):

        with cols[idx % 6]:

            poster = get_poster(row["imdb_id"])

            st.markdown(
                '<div class="movie-card">',
                unsafe_allow_html=True
            )

            if poster:
                st.image(
                    poster,
                    use_container_width=True
                )

            st.markdown(
                f"""
                <div class="movie-title">
                    {row["title"]}
                </div>

                <div class="movie-sub">
                    ⭐ {row["rating"]:.1f}
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button(
                "Select",
                key=f"search_{idx}"
            ):
                st.session_state.selected_movie = row["title"]
                st.rerun()

            st.markdown(
                '</div>',
                unsafe_allow_html=True
            )

# =========================================================
# TRENDING
# =========================================================

st.markdown(
    '<div class="section-title">🔥 Trending Now</div>',
    unsafe_allow_html=True
)

trending = movies_df.sort_values(
    "popularity",
    ascending=False
).head(12)

cols = st.columns(6)

for idx, (_, row) in enumerate(trending.iterrows()):

    with cols[idx % 6]:

        poster = get_poster(row["imdb_id"])

        st.markdown(
            '<div class="movie-card">',
            unsafe_allow_html=True
        )

        if poster:
            st.image(
                poster,
                use_container_width=True
            )

        st.markdown(
            f"""
            <div class="movie-title">
                {row["title"]}
            </div>

            <div class="movie-sub">
                ⭐ {row["rating"]:.1f}
            </div>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            "Watch",
            key=f"trend_{idx}"
        ):
            st.session_state.selected_movie = row["title"]
            st.rerun()

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

# =========================================================
# RECOMMENDATION SECTION
# =========================================================

st.markdown(
    f'''
    <div class="section-title">
    🎯 Because You Watched "{selected_movie}"
    </div>
    ''',
    unsafe_allow_html=True
)

recommendations = hybrid_recommendation(selected_movie)

cols = st.columns(6)

for idx, (_, row) in enumerate(recommendations.iterrows()):

    with cols[idx % 6]:

        poster = get_poster(row["imdb_id"])

        st.markdown(
            '<div class="movie-card">',
            unsafe_allow_html=True
        )

        if poster:
            st.image(
                poster,
                use_container_width=True
            )

        st.markdown(
            f"""
            <div class="movie-title">
                {row["title"]}
            </div>

            <div class="movie-sub">
                ⭐ {row["rating"]:.1f}
                <br>
                Similarity:
                {row["similarity"]*100:.0f}%
            </div>
            """,
            unsafe_allow_html=True
        )

        # WHY RECOMMENDED
        genre = row["genre"]

        st.markdown(
            f"""
            <span class="pill">
                🎭 {genre}
            </span>
            """,
            unsafe_allow_html=True
        )

        if st.button(
            "Recommend",
            key=f"rec_{idx}"
        ):
            st.session_state.selected_movie = row["title"]
            st.rerun()

        st.markdown(
            '</div>',
            unsafe_allow_html=True
        )

# =========================================================
# DETAIL SECTION
# =========================================================

selected_data = movies_df[
    movies_df["title_clean"] == selected_movie
]

if len(selected_data):

    movie = selected_data.iloc[0]

    st.markdown(
        '<div class="section-title">🎬 Movie Detail</div>',
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([1, 2])

    with c1:

        poster = get_poster(movie["imdb_id"])

        if poster:
            st.image(
                poster,
                use_container_width=True
            )

    with c2:

        st.markdown(
            f"# {movie['title']}"
        )

        st.markdown(
            f"""
            <span class="pill">
                ⭐ {movie['rating']:.1f}
            </span>

            <span class="pill">
                🎭 {movie['genre']}
            </span>

            <span class="pill">
                📅 {int(movie['year'])}
            </span>
            """,
            unsafe_allow_html=True
        )

        st.write(movie["overview"])

        st.markdown("### Why Recommended?")

        st.success(
            f"""
            This movie is recommended because it has:
            - Similar genre and keywords
            - Similar cast/director
            - High cosine similarity score
            - Strong popularity & weighted rating
            """
        )

# =========================================================
# FOOTER
# =========================================================

st.markdown("---")

st.caption("""
Cinematric AI — Hybrid Recommendation System
using TF-IDF, Cosine Similarity, Popularity Analysis,
and TMDb API.
""")
