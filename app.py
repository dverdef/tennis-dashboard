import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="ATP Tennis Dashboard", page_icon="🎾", layout="wide")


@st.cache_resource
def get_connection():
    return psycopg2.connect(st.secrets["database"]["url"])


@st.cache_data(ttl=600)
def run_query(query, params=None):
    conn = get_connection()
    return pd.read_sql(query, conn, params=params)


st.title("🎾 ATP Tennis Dashboard")
st.caption("Data from Jeff Sackmann's tennis_atp repository")

# ---------- Sidebar filters ----------
st.sidebar.header("Filters")

surfaces = run_query("SELECT DISTINCT surface FROM atp_2026_matches ORDER BY surface")
surface_filter = st.sidebar.multiselect(
    "Surface", options=surfaces["surface"].dropna().tolist(), default=None
)

rounds = run_query("SELECT DISTINCT round FROM atp_2026_matches ORDER BY round")
round_filter = st.sidebar.multiselect(
    "Round", options=rounds["round"].dropna().tolist(), default=None
)

player_search = st.sidebar.text_input("Player name contains")

# ---------- Build dynamic query ----------
where_clauses = []
params = []

if surface_filter:
    where_clauses.append("surface = ANY(%s)")
    params.append(surface_filter)

if round_filter:
    where_clauses.append("round = ANY(%s)")
    params.append(round_filter)

if player_search:
    where_clauses.append("(winner_name ILIKE %s OR loser_name ILIKE %s)")
    params.extend([f"%{player_search}%", f"%{player_search}%"])

where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

query = f"""
    SELECT tourney_name, surface, tourney_date, round,
           winner_name, loser_name, score, minutes,
           winner_rank, loser_rank
    FROM atp_2026_matches
    {where_sql}
    ORDER BY tourney_date DESC, match_num
"""

df = run_query(query, params=params if params else None)

# ---------- Top metrics ----------
col1, col2, col3 = st.columns(3)
col1.metric("Matches", len(df))
col2.metric("Tournaments", df["tourney_name"].nunique())
col3.metric("Players", pd.concat([df["winner_name"], df["loser_name"]]).nunique())

# ---------- Tabs ----------
tab1, tab2, tab3 = st.tabs(["Match results", "Player lookup", "Charts"])

with tab1:
    st.dataframe(df, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Head-to-head / player record")
    all_players = sorted(set(df["winner_name"]).union(df["loser_name"]))
    selected_player = st.selectbox("Choose a player", options=all_players if all_players else ["No data"])

    if selected_player and selected_player != "No data":
        player_matches = df[
            (df["winner_name"] == selected_player) | (df["loser_name"] == selected_player)
        ].copy()
        wins = (player_matches["winner_name"] == selected_player).sum()
        losses = (player_matches["loser_name"] == selected_player).sum()

        c1, c2, c3 = st.columns(3)
        c1.metric("Wins", wins)
        c2.metric("Losses", losses)
        c3.metric("Win rate", f"{wins / max(wins + losses, 1) * 100:.0f}%")

        st.dataframe(player_matches, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Matches by surface")
    if not df.empty:
        surface_counts = df["surface"].value_counts().reset_index()
        surface_counts.columns = ["surface", "matches"]
        fig = px.bar(surface_counts, x="surface", y="matches")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Match duration distribution")
        duration_df = df.dropna(subset=["minutes"])
        if not duration_df.empty:
            fig2 = px.histogram(duration_df, x="minutes", nbins=30)
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No matches found for the current filters.")
