import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

pd.set_option('display.float_format', '{:.2f}'.format)
st.set_page_config(layout="wide")

st.title("Gas S&D Weekly Dashboard")

# Load the data
def weekly_file_date(path):
    date_part = path.stem.split('_')[0]
    try:
        return pd.to_datetime(date_part, format='%Y%m%d')
    except ValueError:
        return pd.NaT


def find_weekly_files(folder="."):
    files = []
    for path in Path(folder).glob("*_Gas_SnD_weekly.csv"):
        file_dt = weekly_file_date(path)
        if not pd.isna(file_dt):
            files.append((file_dt, path))
    return sorted(files, key=lambda x: x[0])


def latest_weekly_file(folder="."):
    files = find_weekly_files(folder)
    if not files:
        raise FileNotFoundError("No *_Gas_SnD_weekly.csv files found.")
    return files[-1]


def previous_week_latest_file(current_dt, folder="."):
    week_start = current_dt.normalize() - pd.Timedelta(days=current_dt.dayofweek)
    previous_week_start = week_start - pd.Timedelta(days=7)
    previous_week_end = week_start - pd.Timedelta(days=1)

    candidates = [
        (file_dt, path)
        for file_dt, path in find_weekly_files(folder)
        if previous_week_start <= file_dt <= previous_week_end
    ]
    return candidates[-1] if candidates else (None, None)


current_date, current_path = latest_weekly_file()
filename = current_path.name

previous_date, previous_path = previous_week_latest_file(current_date)
previous_filename = previous_path.name if previous_path is not None else None
previous_label = previous_date.strftime('%Y-%m-%d') if previous_date is not None else "Previous week"

def load_weekly_df(path):
    raw = pd.read_csv(path)
    week_cols = [col for col in raw.columns if col.startswith('W')]
    data = raw.copy()
    data[week_cols] = data[week_cols].astype(object)
    numeric_mask = data['week'] != 'mon'
    data.loc[numeric_mask, week_cols] = data.loc[numeric_mask, week_cols].apply(pd.to_numeric, errors='coerce')
    return data, week_cols, raw

try:
    df, week_cols, raw_df = load_weekly_df(filename)
    st.success(f"Loaded data from {filename}")
except FileNotFoundError:
    st.error(f"File {filename} not found.")
    st.stop()
except Exception as exc:
    st.error(f"Unable to load {filename}: {exc}")
    st.stop()

mon_row = raw_df[raw_df['week'] == 'mon']

# Function to display table with total
def display_table_with_total(sub_df, title, heatmap=False):
    st.subheader(title)
    if not sub_df.empty:
        # Multiselect for rows to include in total
        rows = sub_df['week'].tolist()
        selected_rows = st.multiselect(f"Select rows for {title} total", rows, default=rows, key=title)
        
        # Filter data
        filtered_df = sub_df[sub_df['week'].isin(selected_rows)].copy()
        
        # Keep mon row values separate so date labels are preserved
        week_cols_local = [col for col in filtered_df.columns if col.startswith('W')]
        mon_df = filtered_df[filtered_df['week'] == 'mon'].copy()
        numeric_df = filtered_df[filtered_df['week'] != 'mon'].copy()
        numeric_df[week_cols_local] = numeric_df[week_cols_local].apply(pd.to_numeric, errors='coerce')
        
        # Calculate total row from numeric values only
        total_row = numeric_df[week_cols_local].sum(numeric_only=True)
        total_df = pd.DataFrame([total_row], columns=week_cols_local)
        total_df['week'] = 'Total'
        total_df = total_df[['week'] + week_cols_local]
        total_df[week_cols_local] = total_df[week_cols_local].round(2)
        
        # Round numeric display values
        numeric_df[week_cols_local] = numeric_df[week_cols_local].round(2)
        
        # Combine mon row, numeric rows, and total row
        combined_df = pd.concat([mon_df, numeric_df, total_df], ignore_index=True)

        def format_numeric(value):
            try:
                return f"{value:.2f}"
            except (TypeError, ValueError):
                return value
        
        if heatmap:
            start_index = 0
            if 'W-1' in week_cols_local:
                start_index = week_cols_local.index('W-1')
            heatmap_cols = week_cols_local[start_index:]
            numeric_subset = pd.IndexSlice[combined_df[combined_df['week'] != 'mon'].index, heatmap_cols]
            styled = combined_df.style.background_gradient(
                cmap='RdYlGn',
                subset=numeric_subset,
                axis=None
            ).format(format_numeric, subset=numeric_subset)

            def clear_na_styles(val):
                return 'background-color: transparent' if pd.isna(val) else ''

            styled = styled.map(clear_na_styles, subset=numeric_subset)
            styled = styled.set_properties(subset=['W0'], **{'color': 'red', 'font-weight': 'bold'})
            st.dataframe(styled, use_container_width=True)
            return combined_df
        else:
            styled = combined_df.style.format(format_numeric, subset=week_cols_local)
            styled = styled.set_properties(subset=['W0'], **{'color': 'red', 'font-weight': 'bold'})
            st.dataframe(styled, use_container_width=True)
            return combined_df
    else:
        st.write("No data found")
        return pd.DataFrame()


def insert_mon_row(sub_df, mon_row):
    if mon_row.empty:
        return sub_df
    if sub_df.empty:
        return mon_row.copy()
    combined = pd.concat([mon_row, sub_df], ignore_index=True)
    return combined


def is_supply_row(series):
    return (
        series.isin([
            'Local production',
            'NO pipeline flow',
            'East pipeline flow',
            'South pipeline flow',
            'Regas/LNG',
        ])
    )


def build_summary_table(data_frame):
    week_cols = [col for col in data_frame.columns if col.startswith('W')]
    demand_mask = (
        data_frame['week'].str.startswith('LDZ, ') |
        data_frame['week'].str.startswith('GFP, ') |
        data_frame['week'].str.startswith('Ind, ')
    )
    supply_mask = is_supply_row(data_frame['week'])
    demand_sum = data_frame.loc[demand_mask, week_cols].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
    supply_sum = data_frame.loc[supply_mask, week_cols].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
    snd_sum = supply_sum - demand_sum

    summary_df = pd.DataFrame([
        demand_sum,
        supply_sum,
        snd_sum
    ], columns=week_cols)
    summary_df['week'] = ['Demand', 'Supply', 'SnD']
    summary_df = summary_df[['week'] + week_cols]
    summary_df[week_cols] = summary_df[week_cols].round(2)
    return summary_df


def selected_rows_for_table(sub_df, title):
    rows = sub_df['week'].tolist()
    return st.session_state.get(title, rows)


def filter_for_summary(data_frame, label_prefix=""):
    mon_mask = data_frame['week'] == 'mon'

    ldz_mask = data_frame['week'].str.startswith('LDZ, ') & ~data_frame['week'].str.contains('Total')
    gfp_mask = data_frame['week'].str.startswith('GFP, ') & ~data_frame['week'].str.contains('Total')
    industry_mask = data_frame['week'].str.startswith('Ind, ') & ~data_frame['week'].str.contains('Total')
    supply_mask = is_supply_row(data_frame['week'])

    groups = [
        (ldz_mask, f"{label_prefix}LDZ Demand"),
        (gfp_mask, f"{label_prefix}GFP Demand"),
        (industry_mask, f"{label_prefix}Industry Demand"),
        (supply_mask, f"{label_prefix}Supply"),
    ]

    keep_parts = [data_frame[mon_mask]]
    for mask, title in groups:
        sub_df = data_frame[mask]
        selected = selected_rows_for_table(insert_mon_row(sub_df, data_frame[mon_mask]), title)
        selected = [row for row in selected if row != 'mon']
        keep_parts.append(sub_df[sub_df['week'].isin(selected)])

    return pd.concat(keep_parts, ignore_index=True)


def display_summary_table(summary_df):
    week_cols = [col for col in summary_df.columns if col.startswith('W')]

    def format_numeric(value):
        try:
            return f"{value:.2f}"
        except (TypeError, ValueError):
            return value

    styled = summary_df.style.format(format_numeric, subset=week_cols)
    if 'W0' in summary_df.columns:
        styled = styled.set_properties(subset=['W0'], **{'color': 'red', 'font-weight': 'bold'})
    st.dataframe(styled, use_container_width=True)


def render_week_tables(data_frame, label_prefix="", heatmap=False, mon_row=None):
    if mon_row is None:
        mon_row = data_frame[data_frame['week'] == 'mon']
    ldz_demand = data_frame[data_frame['week'].str.startswith('LDZ, ') & ~data_frame['week'].str.contains('Total')]
    gfp_demand = data_frame[data_frame['week'].str.startswith('GFP, ') & ~data_frame['week'].str.contains('Total')]
    industry_demand = data_frame[data_frame['week'].str.startswith('Ind, ') & ~data_frame['week'].str.contains('Total')]
    supply = data_frame[is_supply_row(data_frame['week'])]
    net_injection = data_frame[data_frame['week'].str.startswith('Injection, ') & ~data_frame['week'].str.contains('Total')]

    ldz_demand = insert_mon_row(ldz_demand, mon_row)
    gfp_demand = insert_mon_row(gfp_demand, mon_row)
    industry_demand = insert_mon_row(industry_demand, mon_row)
    supply = insert_mon_row(supply, mon_row)
    net_injection = insert_mon_row(net_injection, mon_row)

    edited_ldz = display_table_with_total(ldz_demand, f"{label_prefix}LDZ Demand", heatmap=heatmap)
    edited_gfp = display_table_with_total(gfp_demand, f"{label_prefix}GFP Demand", heatmap=heatmap)
    edited_industry = display_table_with_total(industry_demand, f"{label_prefix}Industry Demand", heatmap=heatmap)
    edited_supply = display_table_with_total(supply, f"{label_prefix}Supply", heatmap=heatmap)
    edited_injection = display_table_with_total(net_injection, f"{label_prefix}Net Injection", heatmap=heatmap)
    return edited_ldz, edited_gfp, edited_industry, edited_supply, edited_injection


def compute_delta(current, previous, current_raw, previous_raw):
    current_week_cols = [col for col in current.columns if col.startswith('W')]
    previous_week_cols = [col for col in previous.columns if col.startswith('W')]

    current_mon = current_raw[current_raw['week'] == 'mon'].iloc[0]
    previous_mon = previous_raw[previous_raw['week'] == 'mon'].iloc[0]

    current_date_map = current_mon[current_week_cols].to_dict()
    previous_date_map = previous_mon[previous_week_cols].to_dict()

    def to_long(df, date_map, week_cols):
        long = df[df['week'] != 'mon'].melt(
            id_vars=['week'],
            value_vars=week_cols,
            var_name='week_col',
            value_name='value'
        )
        long['date_label'] = long['week_col'].map(date_map)
        long['value'] = pd.to_numeric(long['value'], errors='coerce')
        return long

    current_long = to_long(current, current_date_map, current_week_cols)
    previous_long = to_long(previous, previous_date_map, previous_week_cols)

    merged = pd.merge(
        current_long,
        previous_long,
        on=['week', 'date_label'],
        how='left',
        suffixes=('_curr', '_prev')
    )
    merged['delta'] = merged['value_curr'] - merged['value_prev']

    if 'week_col' not in merged.columns:
        if 'week_col_curr' in merged.columns:
            merged['week_col'] = merged['week_col_curr']
        elif 'week_col_prev' in merged.columns:
            merged['week_col'] = merged['week_col_prev']
        else:
            raise KeyError('week_col not found after merge')

    delta_wide = merged.pivot(index='week', columns='week_col', values='delta').reset_index()
    delta_wide = delta_wide[['week'] + current_week_cols]
    delta_wide[current_week_cols] = delta_wide[current_week_cols].round(2)
    return delta_wide

current_label = current_date.strftime('%Y-%m-%d')
current_tab, previous_tab, delta_tab = st.tabs(['this week', 'previous week', 'delta'])

with current_tab:
    st.write(f"Showing data for {current_label}")
    st.subheader('Summary')
    summary_df = build_summary_table(filter_for_summary(df))
    display_summary_table(summary_df)
    edited_ldz, edited_gfp, edited_industry, edited_supply, edited_injection = render_week_tables(df, mon_row=mon_row)

with previous_tab:
    prev_path = Path(previous_filename) if previous_filename else None
    if prev_path is not None and prev_path.exists():
        prev_df, _, prev_raw = load_weekly_df(previous_filename)
        prev_mon_row = prev_raw[prev_raw['week'] == 'mon']
        st.write(f"Showing data for {previous_label}")
        st.subheader('Summary')
        prev_summary_df = build_summary_table(filter_for_summary(prev_df, label_prefix="Previous "))
        display_summary_table(prev_summary_df)
        render_week_tables(prev_df, label_prefix="Previous ", mon_row=prev_mon_row)
    else:
        st.warning("Previous week file not found.")

with delta_tab:
    prev_path = Path(previous_filename) if previous_filename else None
    if prev_path is not None and prev_path.exists():
        prev_df, _, prev_raw = load_weekly_df(previous_filename)
        delta_df = compute_delta(df, prev_df, raw_df, prev_raw)
        if delta_df.empty:
            st.warning("No matching rows available to compute delta.")
        else:
            st.subheader('Delta vs previous week')
            st.write('Positive values mean an increase vs previous week; negative values mean a decrease.')
            delta_summary_df = build_summary_table(filter_for_summary(delta_df, label_prefix="Delta "))
            display_summary_table(delta_summary_df)
            render_week_tables(delta_df, label_prefix="Delta ", heatmap=True, mon_row=mon_row)
    else:
        st.warning("Cannot compute delta without previous week file.")

# Option to save changes
if st.button("Save Changes"):
    combined = pd.concat([edited_ldz, edited_gfp, edited_industry, edited_supply, edited_injection], ignore_index=True)
    mon_row = df[df['week'] == 'mon']
    wide = pd.concat([mon_row, combined], ignore_index=True)
    totals = df[df['week'].str.contains('Total')]
    wide = pd.concat([wide, totals], ignore_index=True)
    wide.to_csv(filename, index=False)
    st.success("Changes saved to file!")
