import json
import os
import pandas as pd
from dash import Dash, html, dcc, dash_table
import plotly.express as px


def load_opportunities(path="data/opportunities.json"):
    if not os.path.exists(path):
        return pd.DataFrame([])
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    opps = data.get("opportunities", [])
    if not opps:
        return pd.DataFrame([])
    df = pd.DataFrame(opps)
    return df


def create_app():
    app = Dash(__name__)
    df = load_opportunities()

    if df.empty:
        table = html.Div("No opportunities found. Run the scanner first.")
        fig = px.bar()
    else:
        table = dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in df.columns],
            data=df.to_dict("records"),
            page_size=20,
            sort_action="native",
            filter_action="native",
        )
        fig = px.bar(df, x="question", y="net_edge")

    app.layout = html.Div(
        [
            html.H2("Polymarket Arbitrage Opportunities"),
            dcc.Graph(figure=fig),
            html.H3("Raw Opportunities"),
            table,
        ]
    )
    return app
