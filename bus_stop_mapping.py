### MTA Bus Stops and Routes Mapping from multiple GTFS feeds (All Boroughs)

import os, glob, io, zipfile, webbrowser
import pandas as pd
import geopandas as gpd
from shapely.geometry import LineString, Point
from pathlib import Path
import folium
from folium.plugins import MarkerCluster

# If any packages or modules are missing, do pip install packagename 
# (Ex: pip install geopandas) in any cell or in Bash/PowerShell

### Download all bus gtfs zipped files from https://www.mta.info/developers
### and add them to a folder in your working directory named "bus_gtfs"
FOLDER = Path("./bus_gtfs")  # or change to another working path
print("FOLDER exists?", FOLDER.exists())

### Verify the paths found in FOLDER
zip_paths = sorted(FOLDER.glob("gtfs_*.zip"))
print("Found:", [p.name for p in zip_paths])
assert zip_paths, f"No GTFS zips found in {FOLDER}/gtfs_*.zip"

# Set the pattern of the zipped filenames
ZIP_PATTERN = "gtfs_*.zip"
REQUIRED_FILES = ["shapes.txt", "stops.txt", "routes.txt", "trips.txt"]
buckets = {k: [] for k in REQUIRED_FILES}

zips = sorted(glob.glob(os.path.join(FOLDER, ZIP_PATTERN)))
assert zips, f"No GTFS zips found in {FOLDER}/{ZIP_PATTERN}"

for zp in zips:
    feed_name = os.path.splitext(os.path.basename(zp))[0]  # e.g., 'gtfs_m'
    with zipfile.ZipFile(zp) as z:
        names = set(z.namelist())
        for fn in REQUIRED_FILES:
            if fn in names:
                df = pd.read_csv(z.open(fn), dtype=str, low_memory=False)
                df["borough_feed"] = feed_name
                buckets[fn].append(df)
            else:
                print(f"[WARN] {fn} missing in {feed_name}")


# concat and normalize dtypes
shapes = pd.concat(buckets["shapes.txt"], ignore_index=True)
stops  = pd.concat(buckets["stops.txt"],  ignore_index=True)
routes = pd.concat(buckets["routes.txt"], ignore_index=True)
trips  = pd.concat(buckets["trips.txt"],  ignore_index=True)

# cast numeric columns
for col in ["shape_pt_lat", "shape_pt_lon"]:
    shapes[col] = shapes[col].astype(float)
shapes["shape_pt_sequence"] = shapes["shape_pt_sequence"].astype(int)

stops["stop_lat"] = stops["stop_lat"].astype(float)
stops["stop_lon"] = stops["stop_lon"].astype(float)

# make a collision-proof shape key (shape_id can repeat across feeds)
shapes["shape_uid"] = shapes["borough_feed"] + "_" + shapes["shape_id"]

# Mapping for shapes and route labels (short/long name)
# Merge trips to routes
shape2route = (
    trips[["route_id", "shape_id", "borough_feed"]].dropna()
    .drop_duplicates(["shape_id", "borough_feed"])
    .merge(
        routes[["route_id", "route_short_name", "route_long_name", "route_color", "borough_feed"]],
        on=["route_id", "borough_feed"], how="left"
    )
)
shape2route["shape_uid"] = shape2route["borough_feed"] + "_" + shape2route["shape_id"]

# build LineStrings per shapes (shape_uid)
shapes_sorted = shapes.sort_values(["shape_uid", "shape_pt_sequence"])
lines = (
    shapes_sorted
      .groupby("shape_uid")[["shape_pt_lon", "shape_pt_lat"]]
      .apply(lambda df: LineString(df.to_numpy()))
      .to_frame("geometry")
      .reset_index()
)


# Merge shapes with routes geodataframe 
routes_gdf = gpd.GeoDataFrame(lines, geometry="geometry", crs="EPSG:4326")
routes_gdf = (
    routes_gdf
    .merge(
        shape2route[["shape_uid", "route_id", "route_short_name", "route_long_name", "route_color", "borough_feed"]],
        on="shape_uid", how="left"
    )
)

# filter for few specific routes if needed (specially If the map feels slow)
# routes_gdf = routes_gdf[routes_gdf["route_id"].isin(["Q43","Q1","Q17","Q83"])]

# Get stops GeoDataFrame (keep borough_feed to avoid ID ambiguity)
stops_gdf = gpd.GeoDataFrame(
    stops[["stop_id", "stop_name", "stop_lat", "stop_lon", "borough_feed"]],
    geometry=gpd.points_from_xy(stops["stop_lon"], stops["stop_lat"]),
    crs="EPSG:4326"
)

# Create base folium map
m = folium.Map(tiles="cartodbpositron", zoom_start=11, prefer_canvas=True)

# Fit to route bounds
minx, miny, maxx, maxy = routes_gdf.total_bounds
m.fit_bounds([[miny, minx], [maxy, maxx]])

# Create explicit panes so stops are ABOVE routes
folium.map.CustomPane("routes", z_index=400).add_to(m)
folium.map.CustomPane("stops",  z_index=650).add_to(m)


# draw each shape (LineString) as a polyline
def line_to_latlon_coords(geom):
    # geom is a shapely LineString or MultiLineString
    if geom.geom_type == "LineString":
        return [(lat, lon) for lon, lat in geom.coords]
    elif geom.geom_type == "MultiLineString":
        coords = []
        for part in geom.geoms:
            coords.extend([(lat, lon) for lon, lat in part.coords])
        return coords
    else:
        return []

# color by route (simple cycle)
# Challenge: Use route_color from routes_gdf
palette = [
    "red","blue","green","purple","orange","darkred","lightred","mediumgreen",
    "darkblue","darkgreen","cadetblue","darkpurple","brown","pink","lightblue",
    "lightgreen","gray","navy","lightgray", "maroon", "mediumyellow"
]
color_map = {}

# Tooltip fields if present
tooltip_fields = [f for f in ["route_id","route_long_name"] if f in routes_gdf.columns]

for i, row in routes_gdf.iterrows():
    route = row.get("route_id") or row.get("route_short_name") or "route"
    if route not in color_map:
        color_map[route] = palette[len(color_map) % len(palette)]
    coords = line_to_latlon_coords(row.geometry)
    if coords:
        folium.PolyLine(
            locations=coords,
            color=color_map[route],
            weight=4,
            opacity=0.9,
            tooltip=f"Route ID: {route}",
        ).add_to(m)


# Add stops as dots
stops_raw = folium.FeatureGroup(name="Stops (dots)", show=True)
for _, s in stops_gdf.iterrows():
    folium.CircleMarker(
        location=[s["stop_lat"], s["stop_lon"]],
        radius=2,
        color="#111",
        fill=True,
        fill_opacity=0.8,
        opacity=0.8,
        tooltip=f"{s.get('stop_name','')} (ID: {s.get('stop_id','')})"
    ).add_to(stops_raw)

stops_raw.add_to(m)
folium.LayerControl(collapsed=False).add_to(m)

# Open map on the web
out = Path("mta_bus_map.html").resolve()
m.save(str(out))
print(f"Wrote {out}")
webbrowser.open(out.as_uri(), new=2)
