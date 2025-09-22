"""

Map all MTA bus stops (from GTFS static) on an interactive Folium map.

What this script does:
1) Reads every GTFS ZIP in ./bus_gtfs (e.g., gtfs_m.zip, gtfs_q.zip, ...).
2) Extracts stops.txt from each ZIP and combines them into one table.
3) Converts (lon, lat) to point geometry (EPSG:4326).
4) Plots ALL stops as tiny dots on a Folium map you can pan/zoom.

Notes for students:
- GTFS "stops.txt" has stop_id, stop_name, stop_lat, stop_lon.
- EPSG:4326 means "latitude/longitude (WGS84)" — the usual map coords.
- If the map feels slow with *all* stops visible: lower the dot size or filter.
"""

from pathlib import Path
import zipfile
import webbrowser
import pandas as pd
import geopandas as gpd
import folium

# If any packages or modules are missing, do pip install packagename 
# (Ex: pip install geopandas) in any cell or in Bash/PowerShell

### Download all bus gtfs zipped files from https://www.mta.info/developers 
### and add them to a folder in your working directory named "bus_gtfs"

FOLDER = Path("./bus_gtfs")  # or change to another working path
print("FOLDER exists?", FOLDER.exists())
zip_paths = sorted(FOLDER.glob("gtfs_*.zip"))
print("Found ZIPs:", [p.name for p in zip_paths]) 
assert zip_paths, f"No GTFS zips found in {FOLDER}/gtfs_*.zip" # Assertion Error if no zips

# Read stops.txt from each ZIP and combine
frames = []
for zp in zip_paths:
    with zipfile.ZipFile(zp) as z:
        if "stops.txt" not in z.namelist():
            print(f"[WARN] stops.txt missing in {zp.name}")
            continue
        df = pd.read_csv(z.open("stops.txt"), dtype=str, low_memory=False)
        df["borough_feed"] = zp.stem  # to remember which ZIP it came from
        frames.append(df)

assert frames, "No stops.txt found in any ZIP."
stops = pd.concat(frames, ignore_index=True)

# Basic cleanup: drop bad lat/lon rows, cast to float
stops = stops.dropna(subset=["stop_lat", "stop_lon"])
stops["stop_lat"] = stops["stop_lat"].astype(float)
stops["stop_lon"] = stops["stop_lon"].astype(float)

# Drop duplicates for stop_id that shows up in multiple zips
# keep one row per location:
stops = stops.drop_duplicates(subset=["stop_id", "stop_lat", "stop_lon"])

# Create stops GeoDataFrame
stops_gdf = gpd.GeoDataFrame(
    stops[["stop_id", "stop_name", "stop_lat", "stop_lon"]],
    geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]),
    crs="EPSG:4326"
)
print(f"Total stops: {len(stops_gdf):,}")

# Create base folium  map
folium_map = folium.Map(tiles="cartodbpositron", zoom_start=11, prefer_canvas=True)

# Fit to stops bounds
minx, miny, maxx, maxy = stops_gdf.total_bounds
folium_map.fit_bounds([[miny, minx], [maxy, maxx]])
folium.map.CustomPane("stops",  z_index=650).add_to(folium_map)

# Add stops as raw dots
stops_raw = folium.FeatureGroup(name="Stops (dots)", show=True)
for _, s in stops_gdf.iterrows():
    folium.CircleMarker(
        location=[s["stop_lat"], s["stop_lon"]],
        radius=1.8,
        # color="#111",
        fill=True,
        fill_opacity=0.8,
        opacity=0.8,
        tooltip=f"{s.get('stop_name','')} (ID: {s.get('stop_id','')})"
    ).add_to(stops_raw)



stops_raw.add_to(folium_map)
folium.LayerControl(collapsed=False).add_to(folium_map)

# Save and open in your browser
out = Path("mta_bus_map.html").resolve()
folium_map.save(str(out))
print(f"Wrote {out}")
webbrowser.open(out.as_uri(), new=2)
