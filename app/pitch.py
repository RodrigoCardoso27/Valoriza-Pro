import plotly.graph_objects as go

# coordenadas simples (0..100) por formação
FORMATION_COORDS = {
    "4-3-3": {
        "GOL": [(10, 50)],
        "ZAG": [(25, 40), (25, 60)],
        "LAT": [(25, 20), (25, 80)],
        "MEI": [(50, 35), (50, 50), (50, 65)],
        "ATA": [(75, 25), (75, 50), (75, 75)],
        "TEC": [(95, 50)],
    },
    "4-4-2": {
        "GOL": [(10, 50)],
        "ZAG": [(25, 40), (25, 60)],
        "LAT": [(25, 20), (25, 80)],
        "MEI": [(50, 25), (50, 45), (50, 55), (50, 75)],
        "ATA": [(75, 40), (75, 60)],
        "TEC": [(95, 50)],
    },
    # adicione outras se quiser (3-5-2 etc.)
}

def draw_pitch(team_df, formation: str):
    coords = FORMATION_COORDS.get(formation)
    if not coords:
        return None

    fig = go.Figure()

    # Campo (retângulo)
    fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(width=2))
    fig.update_xaxes(visible=False, range=[0, 100])
    fig.update_yaxes(visible=False, range=[0, 100], scaleanchor="x", scaleratio=1)

    # plotar jogadores
    used = {k: 0 for k in coords.keys()}
    xs, ys, texts = [], [], []

    for _, row in team_df.iterrows():
        pos = row["posicao"]
        if pos not in coords:
            continue
        i = used[pos]
        if i >= len(coords[pos]):
            continue
        x, y = coords[pos][i]
        used[pos] += 1

        xs.append(x); ys.append(y)
        texts.append(f"{row['apelido']}<br>C$ {row['preco']}")

    fig.add_trace(go.Scatter(
        x=xs, y=ys,
        mode="markers+text",
        text=[t.split("<br>")[0] for t in texts],
        textposition="bottom center",
        hovertext=texts,
        hoverinfo="text",
        marker=dict(size=18)
    ))

    fig.update_layout(margin=dict(l=5, r=5, t=5, b=5), height=520)
    return fig
