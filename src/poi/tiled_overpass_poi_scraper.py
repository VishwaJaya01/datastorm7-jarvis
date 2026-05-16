"""Fast tiled Overpass POI scraper and local outlet distance counter.

This script replaces one-request-per-outlet scraping with:
1. one Overpass query per geographic tile, then
2. local 500m outlet-to-POI counts.

It reads only cleaned Silver coordinates from data/silver/outlet_coordinates.csv.
Generated files are written under data/external/, which is ignored by Git.
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests


INPUT_PATH = Path("data/silver/outlet_coordinates.csv")
OUTPUT_DIR = Path("data/external")
OSM_POIS_PATH = OUTPUT_DIR / "osm_pois.csv"
OUTLET_FEATURES_PATH = OUTPUT_DIR / "outlet_poi_features_FINAL.csv"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "DataStorm7-TeamJarvis-POI/1.0"}

POI_TAGS = {
    "school": ("amenity", "school"),
    "bus_stop": ("highway", "bus_stop"),
    "hospital": ("amenity", "hospital"),
}

OUTPUT_POI_COLUMNS = ["osm_type", "osm_id", "poi_type", "latitude", "longitude"]
OUTPUT_FEATURE_COLUMNS = [
    "Outlet_ID",
    "schools_500m",
    "bus_stops_500m",
    "hospitals_500m",
    "total_poi_500m",
    "poi_available",
]
EARTH_RADIUS_M = 6_371_000.0


def load_outlet_coordinates(path: Path = INPUT_PATH) -> pd.DataFrame:
    """Load cleaned Silver outlet coordinates."""

    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run the Silver pipeline first: python -m src.data.silver_pipeline"
        )

    outlets = pd.read_csv(path)
    required = {"Outlet_ID", "Latitude", "Longitude", "coord_status"}
    missing = required.difference(outlets.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

    outlets = outlets[["Outlet_ID", "Latitude", "Longitude", "coord_status"]].copy()
    outlets["Latitude"] = pd.to_numeric(outlets["Latitude"], errors="coerce")
    outlets["Longitude"] = pd.to_numeric(outlets["Longitude"], errors="coerce")
    outlets = outlets.dropna(subset=["Outlet_ID", "Latitude", "Longitude"])
    outlets = outlets.drop_duplicates("Outlet_ID")
    return outlets


def build_tiles(outlets: pd.DataFrame, tile_size: float, margin: float) -> list[tuple[float, float, float, float]]:
    """Build south/west/north/east grid tiles covering all outlets."""

    south = float(outlets["Latitude"].min()) - margin
    north = float(outlets["Latitude"].max()) + margin
    west = float(outlets["Longitude"].min()) - margin
    east = float(outlets["Longitude"].max()) + margin

    lat_steps = _steps(south, north, tile_size)
    lon_steps = _steps(west, east, tile_size)
    return [
        (lat1, lon1, min(lat1 + tile_size, north), min(lon1 + tile_size, east))
        for lat1 in lat_steps
        for lon1 in lon_steps
    ]


def fetch_pois_for_tiles(
    tiles: list[tuple[float, float, float, float]],
    output_path: Path = OSM_POIS_PATH,
    overpass_url: str = OVERPASS_URL,
    sleep_seconds: float = 1.0,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Query Overpass by tile and save a deduplicated POI checkpoint after each tile."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pois = load_existing_pois(output_path)
    print(f"Starting POI cache rows: {len(pois)}")

    for index, tile in enumerate(tiles, start=1):
        print(f"Tile {index}/{len(tiles)} | bbox={_format_bbox(tile)}")
        tile_pois = query_overpass_tile(tile, overpass_url=overpass_url, max_retries=max_retries)

        if tile_pois:
            pois = pd.concat([pois, pd.DataFrame(tile_pois)], ignore_index=True)
            pois = dedupe_pois(pois)
        else:
            pois = dedupe_pois(pois)

        pois.to_csv(output_path, index=False)
        print(f"POIs collected so far: {len(pois)}")
        if sleep_seconds > 0 and index < len(tiles):
            time.sleep(sleep_seconds)

    return pois


def query_overpass_tile(
    tile: tuple[float, float, float, float],
    overpass_url: str = OVERPASS_URL,
    max_retries: int = 3,
) -> list[dict[str, object]]:
    """Fetch configured POIs for one Overpass bbox tile."""

    query = build_overpass_query(tile)
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                overpass_url,
                data={"data": query},
                headers=HEADERS,
                timeout=180,
            )
            if response.status_code == 429:
                wait = 60 * attempt
                print(f"Rate limited by Overpass. Waiting {wait}s...")
                time.sleep(wait)
                continue
            if response.status_code in {502, 503, 504}:
                wait = 30 * attempt
                print(f"Overpass busy ({response.status_code}). Waiting {wait}s...")
                time.sleep(wait)
                continue

            response.raise_for_status()
            return parse_overpass_elements(response.json().get("elements", []))
        except Exception as exc:  # requests/json errors should retry politely.
            wait = 20 * attempt
            print(f"Tile request attempt {attempt}/{max_retries} failed: {exc}")
            if attempt < max_retries:
                print(f"Waiting {wait}s before retry...")
                time.sleep(wait)

    print("Tile failed after retries; continuing with existing checkpoint.")
    return []


def build_overpass_query(tile: tuple[float, float, float, float]) -> str:
    """Build an Overpass query for nodes, ways, and relations in one tile."""

    south, west, north, east = tile
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    selectors: list[str] = []
    for key, value in POI_TAGS.values():
        selectors.extend(
            [
                f'node["{key}"="{value}"]({bbox});',
                f'way["{key}"="{value}"]({bbox});',
                f'relation["{key}"="{value}"]({bbox});',
            ]
        )

    return f"""
    [out:json][timeout:120];
    (
      {' '.join(selectors)}
    );
    out center;
    """


def parse_overpass_elements(elements: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize Overpass elements to the raw POI output schema."""

    rows: list[dict[str, object]] = []
    for element in elements:
        tags = element.get("tags", {}) or {}
        poi_type = resolve_poi_type(tags)
        if poi_type is None:
            continue

        lat, lon = extract_coordinates(element)
        if lat is None or lon is None:
            continue

        rows.append(
            {
                "osm_type": element.get("type"),
                "osm_id": element.get("id"),
                "poi_type": poi_type,
                "latitude": lat,
                "longitude": lon,
            }
        )
    return rows


def resolve_poi_type(tags: dict[str, object]) -> str | None:
    """Map OSM tags to the small competition POI taxonomy."""

    for poi_type, (key, value) in POI_TAGS.items():
        if tags.get(key) == value:
            return poi_type
    return None


def extract_coordinates(element: dict[str, object]) -> tuple[float | None, float | None]:
    """Return node coordinates or way/relation center coordinates."""

    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])

    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])

    return None, None


def load_existing_pois(path: Path = OSM_POIS_PATH) -> pd.DataFrame:
    """Load existing POI cache or return an empty normalized DataFrame."""

    if not path.exists():
        return pd.DataFrame(columns=OUTPUT_POI_COLUMNS)

    pois = pd.read_csv(path)
    missing = set(OUTPUT_POI_COLUMNS).difference(pois.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return dedupe_pois(pois[OUTPUT_POI_COLUMNS])


def dedupe_pois(pois: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate POIs by OSM identity and POI type."""

    if pois.empty:
        return pd.DataFrame(columns=OUTPUT_POI_COLUMNS)

    clean = pois[OUTPUT_POI_COLUMNS].copy()
    clean["latitude"] = pd.to_numeric(clean["latitude"], errors="coerce")
    clean["longitude"] = pd.to_numeric(clean["longitude"], errors="coerce")
    clean = clean.dropna(subset=["osm_type", "osm_id", "poi_type", "latitude", "longitude"])
    clean = clean.drop_duplicates(["osm_type", "osm_id", "poi_type"])
    return clean.sort_values(["poi_type", "osm_type", "osm_id"]).reset_index(drop=True)


def calculate_outlet_poi_features(
    outlets: pd.DataFrame,
    pois: pd.DataFrame,
    radius_m: float = 500.0,
) -> pd.DataFrame:
    """Calculate POI counts within radius for each outlet."""

    features = outlets[["Outlet_ID"]].copy()
    features["schools_500m"] = 0
    features["bus_stops_500m"] = 0
    features["hospitals_500m"] = 0

    if pois.empty:
        features["total_poi_500m"] = 0
        features["poi_available"] = False
        return features[OUTPUT_FEATURE_COLUMNS]

    for poi_type, output_column in [
        ("school", "schools_500m"),
        ("bus_stop", "bus_stops_500m"),
        ("hospital", "hospitals_500m"),
    ]:
        subset = pois.loc[pois["poi_type"].eq(poi_type)].copy()
        if subset.empty:
            continue
        features[output_column] = count_pois_within_radius(outlets, subset, radius_m=radius_m)

    count_columns = ["schools_500m", "bus_stops_500m", "hospitals_500m"]
    features["total_poi_500m"] = features[count_columns].sum(axis=1)
    features["poi_available"] = features["total_poi_500m"].gt(0)
    return features[OUTPUT_FEATURE_COLUMNS]


def count_pois_within_radius(outlets: pd.DataFrame, pois: pd.DataFrame, radius_m: float) -> np.ndarray:
    """Count nearby POIs using BallTree when available, with a haversine fallback."""

    try:
        from sklearn.neighbors import BallTree

        outlet_rad = np.radians(outlets[["Latitude", "Longitude"]].to_numpy(dtype=float))
        poi_rad = np.radians(pois[["latitude", "longitude"]].to_numpy(dtype=float))
        tree = BallTree(poi_rad, metric="haversine")
        matches = tree.query_radius(outlet_rad, r=radius_m / EARTH_RADIUS_M)
        return np.array([len(match) for match in matches], dtype=int)
    except Exception as exc:
        print(f"BallTree unavailable or failed ({exc}); using haversine fallback.")
        return count_pois_with_haversine_fallback(outlets, pois, radius_m=radius_m)


def count_pois_with_haversine_fallback(
    outlets: pd.DataFrame,
    pois: pd.DataFrame,
    radius_m: float,
    chunk_size: int = 500,
) -> np.ndarray:
    """Simple chunked haversine fallback to avoid one API call per outlet."""

    outlet_coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    poi_coords = pois[["latitude", "longitude"]].to_numpy(dtype=float)
    counts = np.zeros(len(outlet_coords), dtype=int)

    for start in range(0, len(outlet_coords), chunk_size):
        end = min(start + chunk_size, len(outlet_coords))
        distances = haversine_matrix_m(outlet_coords[start:end], poi_coords)
        counts[start:end] = (distances <= radius_m).sum(axis=1)

    return counts


def haversine_matrix_m(outlet_coords: np.ndarray, poi_coords: np.ndarray) -> np.ndarray:
    """Return pairwise haversine distances in meters."""

    outlet_lat = np.radians(outlet_coords[:, 0])[:, None]
    outlet_lon = np.radians(outlet_coords[:, 1])[:, None]
    poi_lat = np.radians(poi_coords[:, 0])[None, :]
    poi_lon = np.radians(poi_coords[:, 1])[None, :]

    dlat = poi_lat - outlet_lat
    dlon = poi_lon - outlet_lon
    a = np.sin(dlat / 2.0) ** 2 + np.cos(outlet_lat) * np.cos(poi_lat) * np.sin(dlon / 2.0) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def save_outlet_features(features: pd.DataFrame, path: Path = OUTLET_FEATURES_PATH) -> None:
    """Save outlet-level POI features."""

    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(path, index=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiled Overpass POI scrape and 500m outlet POI features.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Cleaned Silver outlet coordinates CSV.")
    parser.add_argument("--osm-output", type=Path, default=OSM_POIS_PATH, help="Raw/deduplicated OSM POI cache CSV.")
    parser.add_argument(
        "--features-output",
        type=Path,
        default=OUTLET_FEATURES_PATH,
        help="Outlet-level POI feature output CSV.",
    )
    parser.add_argument("--tile-size", type=float, default=0.25, help="Tile size in decimal degrees.")
    parser.add_argument("--margin", type=float, default=0.02, help="Bounding box margin in decimal degrees.")
    parser.add_argument("--radius-m", type=float, default=500.0, help="Outlet POI count radius in meters.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Pause between Overpass tile requests.")
    parser.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass API interpreter URL.")
    parser.add_argument(
        "--refresh-overpass",
        action="store_true",
        help="Query Overpass even if the POI cache already exists.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    outlets = load_outlet_coordinates(args.input)
    print(f"Outlet coordinates loaded: {len(outlets)}")

    tiles = build_tiles(outlets, tile_size=args.tile_size, margin=args.margin)
    print(f"Number of tiles: {len(tiles)}")
    print(f"Tile size: {args.tile_size} degrees | Margin: {args.margin} degrees")

    if args.osm_output.exists() and not args.refresh_overpass:
        print(f"Existing POI cache found: {args.osm_output}")
        print("Skipping Overpass API calls and recomputing outlet counts only.")
        pois = load_existing_pois(args.osm_output)
    else:
        pois = fetch_pois_for_tiles(
            tiles,
            output_path=args.osm_output,
            overpass_url=args.overpass_url,
            sleep_seconds=args.sleep_seconds,
        )

    print(f"Final deduplicated POIs collected: {len(pois)}")
    features = calculate_outlet_poi_features(outlets, pois, radius_m=args.radius_m)
    save_outlet_features(features, args.features_output)

    print(f"Final outlet POI rows: {len(features)}")
    print(f"POI cache saved to: {args.osm_output}")
    print(f"Outlet POI features saved to: {args.features_output}")


def _steps(start: float, stop: float, step: float) -> list[float]:
    if step <= 0:
        raise ValueError("tile size must be positive")

    count = max(1, math.ceil((stop - start) / step))
    return [start + i * step for i in range(count)]


def _format_bbox(tile: tuple[float, float, float, float]) -> str:
    south, west, north, east = tile
    return f"{south:.4f},{west:.4f},{north:.4f},{east:.4f}"


if __name__ == "__main__":
    main()
