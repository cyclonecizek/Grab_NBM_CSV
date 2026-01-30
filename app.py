import datetime as dt
import io
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="NBM 1D Viewer Latest CSV", layout="wide")

# -------------------------
# CONFIG
# -------------------------
STATIONS = ["KXMR", "KTTS", "X1K", "KCOF", "KMLB", "KTIX"]

NBM_VERSIONS_TO_TRY = ["NBM4.2", "NBM4.1", "NBM4.0"]
DAYS_BACK = 3               # search today UTC + previous 2 days
TIMEOUT = 20                # seconds
HOURS_DESC = list(range(23, -1, -1))

BASE = "https://apps.gsl.noaa.gov/nbmviewer/data/archive"


# -------------------------
# HELPERS
# -------------------------
def build_url(y: int, m: int, d: int, hh: int, nbm_version: str, station: str) -> str:
    return f"{BASE}/{y:04d}/{m:02d}/{d:02d}/{nbm_version}/{hh:02d}/{station}.csv"


@st.cache_data(show_spinner=False, ttl=300)
def url_exists(url: str) -> bool:
    """
    Check if URL exists. Prefer HEAD; fallback to small GET if HEAD is blocked.
    Cached for 5 minutes to reduce repeated checks.
    """
    try:
        r = requests.head(url, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return True
        if r.status_code in (403, 405):  # HEAD not allowed
            raise RuntimeError("HEAD blocked")
        return False
    except Exception:
        try:
            rg = requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True)
            return rg.status_code == 200
        except Exception:
            return False


@st.cache_data(show_spinner=False, ttl=300)
def find_latest_csv(station: str):
    """
    Search newest-to-oldest:
      - today (UTC) then previous days
      - hour 23..0
      - versions in NBM_VERSIONS_TO_TRY order
    Returns dict with url and run metadata, or None.
    """
    today_utc = dt.datetime.utcnow().date()

    for day_offset in range(DAYS_BACK):
        day = today_utc - dt.timedelta(days=day_offset)
        y, m, d = day.year, day.month, day.day

        for hh in HOURS_DESC:
            for ver in NBM_VERSIONS_TO_TRY:
                url = build_url(y, m, d, hh, ver, station)
                if url_exists(url):
                    return {"url": url, "year": y, "month": m, "day": d, "hour": hh, "version": ver}

    return None


@st.cache_data(show_spinner=True, ttl=300)
def download_csv_bytes(url: str) -> bytes:
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.content


# -------------------------
# UI
# -------------------------
st.title("NBM 1D Viewer — Latest CSV Downloader")
st.caption("Pulls the newest archived station CSV from the NOAA/GSL NBM Viewer backend (no GRIB parsing).")

station = st.selectbox("Choose station", STATIONS, index=0)

colA, colB = st.columns([1, 1])
with colA:
    st.write("Search settings")
    st.write(f"- Versions tried: `{', '.join(NBM_VERSIONS_TO_TRY)}`")
    st.write(f"- Days back (UTC): `{DAYS_BACK}`")
with colB:
    st.write("Tip")
    st.write("If a cycle is missing, the app automatically walks backward until it finds the newest available file.")

if st.button("Get most recent CSV", type="primary"):
    with st.spinner("Searching for latest available run..."):
        found = find_latest_csv(station)

    if not found:
        st.error(f"No CSV found for {station} in the last {DAYS_BACK} day(s). Try increasing DAYS_BACK.")
        st.stop()

    st.success(
        f"Found latest: {found['year']:04d}-{found['month']:02d}-{found['day']:02d} "
        f"{found['hour']:02d}Z ({found['version']})"
    )
    st.write("Source URL:", found["url"])

    with st.spinner("Downloading CSV..."):
        csv_bytes = download_csv_bytes(found["url"])

    # Preview in dataframe
    df = pd.read_csv(io.BytesIO(csv_bytes))
    st.write(f"Rows: **{df.shape[0]}**, Columns: **{df.shape[1]}**")
    st.dataframe(df.head(30), use_container_width=True)

    # Download button
    filename = f"{station}_{found['year']:04d}{found['month']:02d}{found['day']:02d}{found['hour']:02d}_{found['version']}.csv"
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=filename,
        mime="text/csv",
    )
