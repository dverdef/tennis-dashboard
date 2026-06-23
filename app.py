import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "Match results", "Player lookup", "Head-to-head",
    "Win rates", "Surfaces", "Timeline"
])

# ── Tab 1: Match results ──────────────────────────────────────────────────────
with tab1:
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── Tab 2: Player lookup ──────────────────────────────────────────────────────
with tab2:
    st.subheader("Player record")
    all_players = sorted(set(df["winner_name"]).union(df["loser_name"]))
    selected_player = st.selectbox("Choose a player", options=all_players if all_players else ["No data"], key="player_lookup")

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

        # Match duration vs ranking scatter
        st.subheader("Match duration vs opponent ranking")
        scatter_df = player_matches.dropna(subset=["minutes"]).copy()
        scatter_df["opponent"] = scatter_df.apply(
            lambda r: r["loser_name"] if r["winner_name"] == selected_player else r["winner_name"], axis=1
        )
        scatter_df["opponent_rank"] = scatter_df.apply(
            lambda r: r["loser_rank"] if r["winner_name"] == selected_player else r["winner_rank"], axis=1
        )
        scatter_df["result"] = scatter_df["winner_name"].apply(
            lambda w: "Win" if w == selected_player else "Loss"
        )
        if not scatter_df.empty:
            fig_scatter = px.scatter(
                scatter_df, x="opponent_rank", y="minutes",
                color="result", hover_data=["opponent", "tourney_name", "score"],
                color_discrete_map={"Win": "#2ecc71", "Loss": "#e74c3c"},
                labels={"opponent_rank": "Opponent Ranking", "minutes": "Match Duration (min)"},
                title=f"{selected_player} — Match Duration vs Opponent Ranking"
            )
            st.plotly_chart(fig_scatter, use_container_width=True, config={"toImageButtonOptions": {"format": "svg", "filename": "tennis_chart"}})

        st.dataframe(player_matches, use_container_width=True, hide_index=True)

# ── Tab 3: Head-to-head ───────────────────────────────────────────────────────
with tab3:
    st.subheader("Head-to-head comparison")
    all_players_h2h = sorted(set(df["winner_name"]).union(df["loser_name"]))
    col_a, col_b = st.columns(2)
    player_a = col_a.selectbox("Player A", options=all_players_h2h, key="h2h_a")
    player_b = col_b.selectbox("Player B", options=all_players_h2h, index=1, key="h2h_b")

    if player_a != player_b:
        h2h = df[
            ((df["winner_name"] == player_a) & (df["loser_name"] == player_b)) |
            ((df["winner_name"] == player_b) & (df["loser_name"] == player_a))
        ].copy()

        if h2h.empty:
            st.info(f"No matches found between {player_a} and {player_b} in this dataset.")
        else:
            a_wins = (h2h["winner_name"] == player_a).sum()
            b_wins = (h2h["winner_name"] == player_b).sum()

            c1, c2, c3 = st.columns(3)
            c1.metric(f"{player_a} wins", a_wins)
            c2.metric("Total matches", len(h2h))
            c3.metric(f"{player_b} wins", b_wins)

            fig_h2h = go.Figure(go.Bar(
                x=[player_a, player_b],
                y=[a_wins, b_wins],
                marker_color=["#3498db", "#e74c3c"]
            ))
            fig_h2h.update_layout(title="Head-to-head wins", yaxis_title="Wins")
            st.plotly_chart(fig_h2h, use_container_width=True, config={"toImageButtonOptions": {"format": "svg", "filename": "tennis_chart"}})
            st.dataframe(h2h[["tourney_name", "surface", "round", "winner_name", "loser_name", "score"]], use_container_width=True, hide_index=True)
    else:
        st.warning("Please select two different players.")

# ── Tab 4: Player win rates ───────────────────────────────────────────────────
with tab4:
    st.subheader("Top players by win rate")
    min_matches = st.slider("Minimum matches played", 5, 30, 10)

    winners = df["winner_name"].value_counts().rename("wins")
    losers = df["loser_name"].value_counts().rename("losses")
    player_stats = pd.concat([winners, losers], axis=1).fillna(0)
    player_stats["total"] = player_stats["wins"] + player_stats["losses"]
    player_stats["win_rate"] = (player_stats["wins"] / player_stats["total"] * 100).round(1)
    player_stats = player_stats[player_stats["total"] >= min_matches].sort_values("win_rate", ascending=False).head(20).reset_index()
    player_stats.columns = ["player", "wins", "losses", "total", "win_rate"]

    fig_wr = px.bar(
        player_stats, x="win_rate", y="player", orientation="h",
        color="win_rate", color_continuous_scale="Teal",
        labels={"win_rate": "Win Rate (%)", "player": ""},
        title=f"Top 20 players by win rate (min {min_matches} matches)"
    )
    fig_wr.update_layout(yaxis={"categoryorder": "total ascending"}, showlegend=False)
    st.plotly_chart(fig_wr, use_container_width=True, config={"toImageButtonOptions": {"format": "svg", "filename": "tennis_chart"}})

# ── Tab 5: Surface breakdown ──────────────────────────────────────────────────
with tab5:
    st.subheader("Surface win % per player")
    surf_player = st.selectbox("Choose a player", options=sorted(set(df["winner_name"]).union(df["loser_name"])), key="surf_player")

    surf_df = df[
        (df["winner_name"] == surf_player) | (df["loser_name"] == surf_player)
    ].copy()
    surf_df["result"] = surf_df["winner_name"].apply(lambda w: "Win" if w == surf_player else "Loss")

    if not surf_df.empty:
        surface_breakdown = surf_df.groupby(["surface", "result"]).size().unstack(fill_value=0).reset_index()
        if "Win" not in surface_breakdown.columns:
            surface_breakdown["Win"] = 0
        if "Loss" not in surface_breakdown.columns:
            surface_breakdown["Loss"] = 0
        surface_breakdown["total"] = surface_breakdown["Win"] + surface_breakdown["Loss"]
        surface_breakdown["win_pct"] = (surface_breakdown["Win"] / surface_breakdown["total"] * 100).round(1)

        fig_surf = px.bar(
            surface_breakdown, x="surface", y="win_pct",
            color="surface", text="win_pct",
            labels={"win_pct": "Win %", "surface": "Surface"},
            title=f"{surf_player} — Win % by surface"
        )
        fig_surf.update_traces(texttemplate="%{text}%", textposition="outside")
        fig_surf.update_layout(showlegend=False, yaxis_range=[0, 110])
        st.plotly_chart(fig_surf, use_container_width=True, config={"toImageButtonOptions": {"format": "svg", "filename": "tennis_chart"}})

        st.dataframe(surface_breakdown[["surface", "Win", "Loss", "total", "win_pct"]], use_container_width=True, hide_index=True)

# ── Tab 6: Tournament timeline ────────────────────────────────────────────────
with tab6:
    st.subheader("Tournament results timeline")
    timeline_df = run_query("""
        SELECT tourney_name, surface, tourney_date,
               COUNT(*) as matches,
               COUNT(DISTINCT winner_name) as unique_winners
        FROM atp_2026_matches
        GROUP BY tourney_name, surface, tourney_date
        ORDER BY tourney_date
    """)

    if not timeline_df.empty:
        timeline_df["tourney_date"] = pd.to_datetime(timeline_df["tourney_date"].astype(str), format="%Y%m%d", errors="coerce")

        fig_timeline = px.scatter(
            timeline_df, x="tourney_date", y="matches",
            color="surface", size="matches", hover_name="tourney_name",
            hover_data=["surface", "matches"],
            labels={"tourney_date": "Date", "matches": "Matches played"},
            title="Tournaments across the 2026 season"
        )
        fig_timeline.update_layout(xaxis_title="Date", yaxis_title="Matches played")
        st.plotly_chart(fig_timeline, use_container_width=True, config={"toImageButtonOptions": {"format": "svg", "filename": "tennis_chart"}})

        st.dataframe(timeline_df, use_container_width=True, hide_index=True)
