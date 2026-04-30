from datetime import date

import dash
from dash import Input, Output, State, dash_table, dcc, html

from irs_schedule import (
    BusinessDayConvention,
    CalendarType,
    DayCountConvention,
    Frequency,
    Schedule,
    StubType,
)

app = dash.Dash(__name__)

_LABEL_STYLE = {"fontWeight": "600", "marginBottom": "4px", "fontSize": "13px"}
_INPUT_STYLE = {"width": "100%", "padding": "6px", "borderRadius": "4px",
                "border": "1px solid #ccc", "fontSize": "13px"}
_DROPDOWN_STYLE = {"fontSize": "13px"}

def _field(label, component):
    return html.Div([
        html.Label(label, style=_LABEL_STYLE),
        component,
    ], style={"display": "flex", "flexDirection": "column", "gap": "4px"})


app.layout = html.Div([
    html.H2("IRS Schedule Generator", style={"marginBottom": "24px", "color": "#1a1a2e"}),

    html.Div([
        # Row 1
        html.Div([
            _field("Effective Date", dcc.DatePickerSingle(
                id="effective-date",
                date=date(2024, 3, 20).isoformat(),
                display_format="YYYY-MM-DD",
                style={"width": "100%"},
            )),
            _field("Termination Date", dcc.DatePickerSingle(
                id="termination-date",
                date=date(2026, 3, 20).isoformat(),
                display_format="YYYY-MM-DD",
                style={"width": "100%"},
            )),
            _field("Frequency", dcc.Dropdown(
                id="frequency",
                options=[{"label": f.name.replace("_", " ").title(), "value": f.name}
                         for f in Frequency],
                value="SEMI_ANNUAL",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
            _field("Calendar", dcc.Dropdown(
                id="calendar",
                options=[{"label": c.value, "value": c.name} for c in CalendarType],
                value="USD",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr 1fr", "gap": "16px"}),

        # Row 2
        html.Div([
            _field("Day Count Convention", dcc.Dropdown(
                id="day-count",
                options=[{"label": d.value, "value": d.name} for d in DayCountConvention],
                value="ACT_360",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
            _field("Business Day Convention", dcc.Dropdown(
                id="bdc",
                options=[{"label": b.name.replace("_", " ").title(), "value": b.name}
                         for b in BusinessDayConvention],
                value="MODIFIED_FOLLOWING",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
            _field("Stub Type", dcc.Dropdown(
                id="stub-type",
                options=[{"label": s.name.replace("_", " ").title(), "value": s.name}
                         for s in StubType],
                value="SHORT_BACK",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
            _field("End of Month", dcc.Dropdown(
                id="eom",
                options=[{"label": "Yes", "value": "true"},
                         {"label": "No",  "value": "false"}],
                value="false",
                clearable=False,
                style=_DROPDOWN_STYLE,
            )),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr 1fr 1fr", "gap": "16px",
                  "marginTop": "16px"}),

    ], style={"background": "#f8f9fa", "padding": "20px", "borderRadius": "8px",
              "border": "1px solid #dee2e6"}),

    html.Div([
        html.Button("Generate Schedule", id="generate-btn", n_clicks=0, style={
            "background": "#e94560", "color": "white", "border": "none",
            "padding": "10px 24px", "borderRadius": "6px", "fontSize": "14px",
            "fontWeight": "600", "cursor": "pointer",
        }),
    ], style={"marginTop": "16px"}),

    html.Div(id="error-msg", style={"color": "#e94560", "marginTop": "12px", "fontSize": "13px"}),

    html.Div(id="summary", style={"marginTop": "12px", "fontSize": "13px", "color": "#555"}),

    dash_table.DataTable(
        id="schedule-table",
        columns=[
            {"name": "Accrual Start", "id": "accrual_start"},
            {"name": "Accrual End",   "id": "accrual_end"},
            {"name": "Pay Date",      "id": "pay_date"},
            {"name": "DCF",           "id": "dcf"},
        ],
        data=[],
        style_table={"marginTop": "16px", "overflowX": "auto"},
        style_header={"backgroundColor": "#1a1a2e", "color": "white",
                      "fontWeight": "600", "fontSize": "13px"},
        style_cell={"fontSize": "13px", "padding": "8px 12px",
                    "textAlign": "left", "fontFamily": "monospace"},
        style_data_conditional=[
            {"if": {"row_index": "odd"}, "backgroundColor": "#f8f9fa"},
        ],
        page_size=50,
    ),

], style={"maxWidth": "1100px", "margin": "40px auto", "fontFamily": "Segoe UI, sans-serif",
          "padding": "0 24px"})


@app.callback(
    Output("schedule-table", "data"),
    Output("error-msg", "children"),
    Output("summary", "children"),
    Input("generate-btn", "n_clicks"),
    State("effective-date",   "date"),
    State("termination-date", "date"),
    State("frequency",        "value"),
    State("calendar",         "value"),
    State("day-count",        "value"),
    State("bdc",              "value"),
    State("stub-type",        "value"),
    State("eom",              "value"),
    prevent_initial_call=True,
)
def generate(n_clicks, effective, termination, frequency, calendar,
             day_count, bdc, stub_type, eom):
    try:
        sch = Schedule(
            effective_date=date.fromisoformat(effective),
            termination_date=date.fromisoformat(termination),
            frequency=Frequency[frequency],
            day_count_convention=DayCountConvention[day_count],
            business_day_convention=BusinessDayConvention[bdc],
            calendar=CalendarType[calendar],
            end_of_month=(eom == "true"),
            stub_type=StubType[stub_type],
        )
        periods = sch.generate()
        rows = [
            {
                "accrual_start": str(p.accrual_start),
                "accrual_end":   str(p.accrual_end),
                "pay_date":      str(p.pay_date),
                "dcf":           f"{p.dcf:.6f}",
            }
            for p in periods
        ]
        total_dcf = sum(p.dcf for p in periods)
        summary = f"{len(periods)} periods · Total DCF: {total_dcf:.6f}"
        return rows, "", summary

    except Exception as e:
        return [], str(e), ""


if __name__ == "__main__":
    app.run(debug=True)
