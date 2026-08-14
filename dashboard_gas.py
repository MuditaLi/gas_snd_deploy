import subprocess
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path

pd.set_option('display.float_format', '{:.2f}'.format)
st.set_page_config(layout="wide")

st.title("Gas S&D Weekly Dashboard")

# Auto-pull once per browser session (on first page load).
if "pulled_on_load" not in st.session_state:
    subprocess.run(["git", "pull"], capture_output=True, cwd=Path(__file__).parent)
    st.session_state.pulled_on_load = True

col1, col2 = st.columns([1, 6])
with col1:
    if st.button("Pull latest data"):
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
        )
        with col2:
            if result.returncode == 0:
                st.success(result.stdout.strip() or "Already up to date.")
            else:
                st.error(result.stderr.strip())
        st.rerun()

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


current_date, current_path = latest_weekly_file()
filename = current_path.name


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
def display_table_with_total(sub_df, title, heatmap=False, key=None):
    st.subheader(title)
    if not sub_df.empty:
        # Multiselect for rows to include in total.
        # `key` is namespaced per selected file by the caller: row labels have
        # changed between file generations, and Streamlit raises if a stored
        # selection contains options the new file does not offer.
        rows = sub_df['week'].tolist()
        selected_rows = st.multiselect(f"Select rows for {title} total", rows, default=rows, key=key or title)
        
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
                if pd.isna(value):
                    return ''
                return f"{value:.2f}"
            except (TypeError, ValueError):
                return str(value) if value is not None else ''

        # Convert mixed string/float columns to strings for Arrow compatibility
        display_df = combined_df.copy()
        display_df['week'] = display_df['week'].replace('mon', 'date')
        for col in week_cols_local:
            display_df[col] = display_df[col].apply(format_numeric)

        date_idx = display_df[display_df['week'] == 'date'].index
        non_date_idx = display_df[display_df['week'] != 'date'].index

        DARK = '#2d3748'

        def style_date_row(row):
            if row.name in date_idx:
                return [f'background-color: {DARK}; color: white; font-weight: bold'] * len(row)
            return [''] * len(row)

        header_styles = [{'selector': 'th', 'props': [
            ('background-color', DARK), ('color', 'white'), ('font-weight', 'bold')
        ]}]

        if heatmap:
            start_index = 0
            if 'W-1' in week_cols_local:
                start_index = week_cols_local.index('W-1')
            heatmap_cols = week_cols_local[start_index:]
            non_mon_idx = combined_df[combined_df['week'] != 'mon'].index
            numeric_subset = pd.IndexSlice[non_mon_idx, heatmap_cols]

            # Extract numeric values for gradient before string conversion
            gmap = combined_df.loc[non_mon_idx, heatmap_cols].apply(pd.to_numeric, errors='coerce')

            styled = display_df.style.background_gradient(
                cmap='RdYlGn',
                subset=numeric_subset,
                gmap=gmap,
                axis=None
            )

            def clear_na_styles(val):
                return 'background-color: transparent' if val == '' else ''

            styled = styled.map(clear_na_styles, subset=numeric_subset)
            styled = styled.apply(style_date_row, axis=1)
            styled = styled.set_table_styles(header_styles)
            if 'W0' in week_cols_local and len(non_date_idx) > 0:
                styled = styled.set_properties(
                    subset=pd.IndexSlice[non_date_idx, ['W0']],
                    **{'color': 'red', 'font-weight': 'bold'}
                )
            st.dataframe(styled, width='stretch')
            return combined_df
        else:
            styled = display_df.style.apply(style_date_row, axis=1)
            styled = styled.set_table_styles(header_styles)
            if 'W0' in week_cols_local and len(non_date_idx) > 0:
                styled = styled.set_properties(
                    subset=pd.IndexSlice[non_date_idx, ['W0']],
                    **{'color': 'red', 'font-weight': 'bold'}
                )
            st.dataframe(styled, width='stretch')
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
            'North Africa flow',
            'Other flow',
            'Regas/LNG',
            # Legacy labels: files up to 20260727 named these two rows
            # 'East pipeline flow' / 'South pipeline flow'. Kept so older
            # files selected for comparison still show a complete Supply table.
            'East pipeline flow',
            'South pipeline flow',
        ])
    )


def build_summary_table(data_frame):
    week_cols = [col for col in data_frame.columns if col.startswith('W')]
    mon_row = data_frame[data_frame['week'] == 'mon']
    demand_mask = (
        data_frame['week'].str.startswith('LDZ, ') |
        data_frame['week'].str.startswith('GFP, ') |
        data_frame['week'].str.startswith('Ind, ')
    )
    supply_mask = is_supply_row(data_frame['week'])
    demand_sum = data_frame.loc[demand_mask, week_cols].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
    supply_sum = data_frame.loc[supply_mask, week_cols].apply(pd.to_numeric, errors='coerce').sum(numeric_only=True)
    # residual_sum = pd.Series(40.0, index=week_cols)   # constant 40 each week
    snd_sum = supply_sum - demand_sum # + residual_sum

    summary_df = pd.DataFrame([
        demand_sum,
        supply_sum,
      #  residual_sum,
        snd_sum
    ], columns=week_cols)
    summary_df['week'] = ['Demand', 'Supply', 'SnD']
    summary_df = summary_df[['week'] + week_cols]
    summary_df[week_cols] = summary_df[week_cols].round(2)

    if not mon_row.empty:
        date_row = mon_row[['week'] + week_cols].copy()
        date_row['week'] = 'date'
        summary_df = pd.concat([date_row, summary_df], ignore_index=True)
    return summary_df


def selected_rows_for_table(sub_df, key):
    rows = sub_df['week'].tolist()
    return st.session_state.get(key, rows)


def filter_for_summary(data_frame, label_prefix="", key_prefix=None):
    if key_prefix is None:
        key_prefix = label_prefix
    mon_mask = data_frame['week'] == 'mon'

    ldz_mask = data_frame['week'].str.startswith('LDZ, ') & ~data_frame['week'].str.contains('Total')
    gfp_mask = data_frame['week'].str.startswith('GFP, ') & ~data_frame['week'].str.contains('Total')
    industry_mask = data_frame['week'].str.startswith('Ind, ') & ~data_frame['week'].str.contains('Total')
    supply_mask = is_supply_row(data_frame['week'])

    groups = [
        (ldz_mask, f"{key_prefix}LDZ Demand"),
        (gfp_mask, f"{key_prefix}GFP Demand"),
        (industry_mask, f"{key_prefix}Industry Demand"),
        (supply_mask, f"{key_prefix}Supply"),
    ]

    keep_parts = [data_frame[mon_mask]]
    for mask, key in groups:
        sub_df = data_frame[mask]
        selected = selected_rows_for_table(insert_mon_row(sub_df, data_frame[mon_mask]), key)
        selected = [row for row in selected if row != 'mon']
        keep_parts.append(sub_df[sub_df['week'].isin(selected)])

    return pd.concat(keep_parts, ignore_index=True)


def display_summary_table(summary_df, heatmap=False):
    week_cols = [col for col in summary_df.columns if col.startswith('W')]

    def format_numeric(value):
        try:
            if pd.isna(value):
                return ''
            return f"{value:.2f}"
        except (TypeError, ValueError):
            return str(value) if value is not None else ''

    display_df = summary_df.copy()
    for col in week_cols:
        display_df[col] = display_df[col].apply(format_numeric)

    date_idx = display_df[display_df['week'] == 'date'].index
    non_date_idx = display_df[display_df['week'] != 'date'].index

    DARK = '#2d3748'

    def style_date_row(row):
        if row.name in date_idx:
            return [f'background-color: {DARK}; color: white; font-weight: bold'] * len(row)
        return [''] * len(row)

    if heatmap and len(non_date_idx) > 0:
        start_index = 0
        if 'W-1' in week_cols:
            start_index = week_cols.index('W-1')
        heatmap_cols = week_cols[start_index:]

        if heatmap_cols:
            numeric_subset = pd.IndexSlice[non_date_idx, heatmap_cols]
            gmap = summary_df.loc[non_date_idx, heatmap_cols].apply(pd.to_numeric, errors='coerce')
            styled = display_df.style.background_gradient(
                cmap='RdYlGn', subset=numeric_subset, gmap=gmap, axis=None
            )
            styled = styled.map(
                lambda v: 'background-color: transparent' if v == '' else '',
                subset=numeric_subset
            )
        else:
            styled = display_df.style
    else:
        styled = display_df.style

    styled = styled.apply(style_date_row, axis=1)
    styled = styled.set_table_styles([{'selector': 'th', 'props': [
        ('background-color', DARK), ('color', 'white'), ('font-weight', 'bold')
    ]}])
    if 'W0' in summary_df.columns and len(non_date_idx) > 0:
        styled = styled.set_properties(
            subset=pd.IndexSlice[non_date_idx, ['W0']],
            **{'color': 'red', 'font-weight': 'bold'}
        )
    st.dataframe(styled, width='stretch')


def render_week_tables(data_frame, label_prefix="", heatmap=False, mon_row=None, key_prefix=None):
    if key_prefix is None:
        key_prefix = label_prefix
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

    edited_ldz = display_table_with_total(
        ldz_demand, f"{label_prefix}LDZ Demand", heatmap=heatmap, key=f"{key_prefix}LDZ Demand")
    edited_gfp = display_table_with_total(
        gfp_demand, f"{label_prefix}GFP Demand", heatmap=heatmap, key=f"{key_prefix}GFP Demand")
    edited_industry = display_table_with_total(
        industry_demand, f"{label_prefix}Industry Demand", heatmap=heatmap, key=f"{key_prefix}Industry Demand")
    edited_supply = display_table_with_total(
        supply, f"{label_prefix}Supply", heatmap=heatmap, key=f"{key_prefix}Supply")
    edited_injection = display_table_with_total(
        net_injection, f"{label_prefix}Net Injection", heatmap=heatmap, key=f"{key_prefix}Net Injection")
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

# Every weekly file except the current one is a valid comparison target,
# newest first so index 0 is the immediately preceding week (the old default).
comparison_files = [
    (file_dt, path) for file_dt, path in reversed(find_weekly_files())
    if path.name != current_path.name
]

# Set inside previous_tab and reused by delta_tab. Streamlit executes tab
# bodies top to bottom in one pass, so previous_tab always runs first.
selected_prev = None

with previous_tab:
    if not comparison_files:
        st.warning("No other weekly files found to compare against.")
    else:
        options = list(range(len(comparison_files)))
        choice = st.selectbox(
            "Compare against",
            options,
            index=0,
            format_func=lambda i: comparison_files[i][0].strftime('%Y-%m-%d'),
            key="comparison_file_idx",
        )
        selected_prev_date, selected_prev_path = comparison_files[choice]
        selected_prev_label = selected_prev_date.strftime('%Y-%m-%d')

        try:
            prev_df, _, prev_raw = load_weekly_df(selected_prev_path.name)
        except Exception as exc:
            st.error(f"Unable to load {selected_prev_path.name}: {exc}")
        else:
            selected_prev = (selected_prev_path, selected_prev_label, prev_df, prev_raw)
            prev_mon_row = prev_raw[prev_raw['week'] == 'mon']
            st.write(f"Showing data for {selected_prev_label} ({selected_prev_path.name})")
            st.subheader('Summary')
            # Widget keys are namespaced by filename so switching files does not
            # carry stale row selections into a file with different row labels.
            key_prefix = f"Previous {selected_prev_path.name} "
            prev_summary_df = build_summary_table(
                filter_for_summary(prev_df, label_prefix="Previous ", key_prefix=key_prefix))
            display_summary_table(prev_summary_df)
            render_week_tables(prev_df, label_prefix="Previous ",
                               mon_row=prev_mon_row, key_prefix=key_prefix)

with delta_tab:
    if selected_prev is not None:
        selected_prev_path, selected_prev_label, prev_df, prev_raw = selected_prev
        delta_df = compute_delta(df, prev_df, raw_df, prev_raw)
        if delta_df.empty:
            st.warning("No matching rows available to compute delta.")
        else:
            st.subheader(f'Delta: {current_label} vs {selected_prev_label}')
            st.write(
                f'Latest file `{current_path.name}` minus `{selected_prev_path.name}`. '
                'Positive values mean an increase vs the selected file; negative values mean a decrease. '
                'Weeks are matched on their Monday date, so blanks are weeks the two files do not share.'
            )
            delta_key_prefix = f"Delta {selected_prev_path.name} "
            delta_summary_df = build_summary_table(
                filter_for_summary(delta_df, label_prefix="Delta ", key_prefix=delta_key_prefix))
            # delta_df has no mon row — prepend date row from current week
            if not mon_row.empty:
                summary_week_cols = [c for c in delta_summary_df.columns if c.startswith('W')]
                date_row = mon_row[['week'] + [c for c in summary_week_cols if c in mon_row.columns]].copy()
                date_row['week'] = 'date'
                delta_summary_df = pd.concat([date_row, delta_summary_df], ignore_index=True)
            display_summary_table(delta_summary_df, heatmap=True)
            render_week_tables(delta_df, label_prefix="Delta ", heatmap=True,
                               mon_row=mon_row, key_prefix=delta_key_prefix)
    else:
        st.warning("Select a file to compare against on the 'previous week' tab.")

# Option to save changes
if st.button("Save Changes"):
    combined = pd.concat([edited_ldz, edited_gfp, edited_industry, edited_supply, edited_injection], ignore_index=True)
    mon_row = df[df['week'] == 'mon']
    wide = pd.concat([mon_row, combined], ignore_index=True)
    totals = df[df['week'].str.contains('Total')]
    wide = pd.concat([wide, totals], ignore_index=True)
    wide.to_csv(filename, index=False)
    st.success("Changes saved to file!")
