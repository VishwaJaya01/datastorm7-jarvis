"""Richer tiled Overpass POI scraper for Member 2 feature engineering.

Version 2 expands the POI taxonomy and computes both 500m and 1000m outlet
features. It still uses cleaned Silver coordinates only and avoids the slow
one-request-per-outlet pattern.
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
OSM_POIS_PATH = OUTPUT_DIR / "osm_pois_v2.csv"
OUTLET_FEATURES_PATH = OUTPUT_DIR / "outlet_poi_features_v2.csv"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "DataStorm7-TeamJarvis-POI-v2/1.0"}
EARTH_RADIUS_M = 6_371_000.0

POI_TAGS: dict[str, list[tuple[str, str]]] = {
    "schools": [("amenity", "school")],
    "bus_stops": [("highway", "bus_stop")],
    "hospitals": [("amenity", "hospital"), ("amenity", "clinic")],
    "restaurants": [("amenity", "restaurant"), ("amenity", "cafe"), ("amenity", "fast_food")],
    "supermarkets": [("shop", "supermarket"), ("shop", "convenience")],
    "markets": [("amenity", "marketplace")],
    "banks_atms": [("amenity", "bank"), ("amenity", "atm")],
    "fuel_stations": [("amenity", "fuel")],
    "religious_places": [("amenity", "place_of_worship")],
    "tourism": [("tourism", "attraction"), ("tourism", "hotel"), ("tourism", "guest_house")],
    "railway_stations": [("railway", "station")],
}

DEMAND_DRIVER_WEIGHTS = {
    "schools": 1.0,
    "bus_stops": 0.8,
    "hospitals": 1.2,
    "restaurants": 1.0,
    "supermarkets": 1.1,
    "markets": 1.0,
    "banks_atms": 0.7,
    "fuel_stations": 0.8,
    "religious_places": 0.7,
    "tourism": 1.1,
    "railway_stations": 1.0,
}

RADII_M = (500, 1000)
OUTPUT_POI_COLUMNS = ["osm_type", "osm_id", "poi_type", "latitude", "longitude"]
POI_COUNT_COLUMNS = [f"{poi_type}_{radius}m" for poi_type in POI_TAGS for radius in RADII_M]
OUTPUT_FEATURE_COLUMNS = (
    ["Outlet_ID"]
    + POI_COUNT_COLUMNS
    + [
        "total_poi_500m",
        "total_poi_1000m",
        "demand_driver_score_500m",
        "demand_driver_score_1000m",
        "poi_available",
    ]
)


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
    """Build south/west/north/east tiles covering all Silver coordinates."""

    if outlets.empty:
        raise ValueError("No outlet coordinates available to build Overpass tiles")

    south = float(outlets["Latitude"].min()) - margin
    north = float(outlets["Latitude"].max()) + margin
    west = float(outlets["Longitude"].min()) - margin
    east = float(outlets["Longitude"].max()) + margin

    return [
        (lat, lon, min(lat + tile_size, north), min(lon + tile_size, east))
        for lat in _steps(south, north, tile_size)
        for lon in _steps(west, east, tile_size)
    ]


def fetch_pois_for_tiles(
    tiles: list[tuple[float, float, float, float]],
    output_path: Path = OSM_POIS_PATH,
    overpass_url: str = OVERPASS_URL,
    sleep_seconds: float = 1.0,
    max_retries: int = 3,
) -> pd.DataFrame:
    """Query Overpass by tile and checkpoint the deduplicated POI cache."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pois = load_existing_pois(output_path)
    print(f"Starting v2 POI cache rows: {len(pois)}")

    for index, tile in enumerate(tiles, start=1):
        print(f"Tile {index}/{len(tiles)} | bbox={_format_bbox(tile)}")
        tile_rows = query_overpass_tile(tile, overpass_url=overpass_url, max_retries=max_retries)

        if tile_rows:
            pois = pd.concat([pois, pd.DataFrame(tile_rows)], ignore_index=True)
        pois = dedupe_pois(pois)
        pois.to_csv(output_path, index=False)

        print(f"POIs collected so far: {len(pois)}")
        print_poi_type_summary(pois)
        if sleep_seconds > 0 and index < len(tiles):
            time.sleep(sleep_seconds)

    return pois


def query_overpass_tile(
    tile: tuple[float, float, float, float],
    overpass_url: str = OVERPASS_URL,
    max_retries: int = 3,
) -> list[dict[str, object]]:
    """Fetch configured POI types for one bbox tile."""

    query = build_overpass_query(tile)
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                overpass_url,
                data={"data": query},
                headers=HEADERS,
                timeout=240,
            )
            if response.status_code == 429:
                wait_seconds = 60 * attempt
                print(f"Rate limited by Overpass. Waiting {wait_seconds}s...")
                time.sleep(wait_seconds)
                continue
            if response.status_code in {502, 503, 504}:
                wait_seconds = 30 * attempt
                print(f"Overpass busy ({response.status_code}). Waiting {wait_seconds}s...")
                time.sleep(wait_seconds)
                continue

            response.raise_for_status()
            return parse_overpass_elements(response.json().get("elements", []))
        except Exception as exc:
            wait_seconds = 20 * attempt
            print(f"Tile request attempt {attempt}/{max_retries} failed: {exc}")
            if attempt < max_retries:
                print(f"Waiting {wait_seconds}s before retry...")
                time.sleep(wait_seconds)

    print("Tile failed after retries; continuing with existing checkpoint.")
    return []


def build_overpass_query(tile: tuple[float, float, float, float]) -> str:
    """Build one Overpass query for all configured POI tags."""

    south, west, north, east = tile
    bbox = f"{south:.6f},{west:.6f},{north:.6f},{east:.6f}"
    selectors: list[str] = []

    for tag_pairs in POI_TAGS.values():
        for key, value in tag_pairs:
            selectors.extend(
                [
                    f'node["{key}"="{value}"]({bbox});',
                    f'way["{key}"="{value}"]({bbox});',
                    f'relation["{key}"="{value}"]({bbox});',
                ]
            )

    return f"""
    [out:json][timeout:180];
    (
      {' '.join(selectors)}
    );
    out center;
    """


def parse_overpass_elements(elements: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize Overpass elements into the v2 POI cache schema."""

    rows: list[dict[str, object]] = []
    for element in elements:
        tags = element.get("tags", {}) or {}
        poi_types = resolve_poi_types(tags)
        if not poi_types:
            continue

        lat, lon = extract_coordinates(element)
        if lat is None or lon is None:
            continue

        for poi_type in poi_types:
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


def resolve_poi_types(tags: dict[str, object]) -> list[str]:
    """Return all configured POI categories matched by an OSM tag set."""

    matched: list[str] = []
    for poi_type, tag_pairs in POI_TAGS.items():
        if any(tags.get(key) == value for key, value in tag_pairs):
            matched.append(poi_type)
    return matched


def extract_coordinates(element: dict[str, object]) -> tuple[float | None, float | None]:
    """Use node coordinates or Overpass center coordinates for ways/relations."""

    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])

    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])

    return None, None


def load_existing_pois(path: Path = OSM_POIS_PATH) -> pd.DataFrame:
    """Load an existing v2 POI cache."""

    if not path.exists():
        return pd.DataFrame(columns=OUTPUT_POI_COLUMNS)

    pois = pd.read_csv(path)
    missing = set(OUTPUT_POI_COLUMNS).difference(pois.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    return dedupe_pois(pois[OUTPUT_POI_COLUMNS])


def dedupe_pois(pois: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate by osm_type, osm_id, and poi_type."""

    if pois.empty:
        return pd.DataFrame(columns=OUTPUT_POI_COLUMNS)

    clean = pois[OUTPUT_POI_COLUMNS].copy()
    clean["latitude"] = pd.to_numeric(clean["latitude"], errors="coerce")
    clean["longitude"] = pd.to_numeric(clean["longitude"], errors="coerce")
    clean = clean.dropna(subset=["osm_type", "osm_id", "poi_type", "latitude", "longitude"])
    clean = clean.drop_duplicates(["osm_type", "osm_id", "poi_type"])
    clean = clean.loc[clean["poi_type"].isin(POI_TAGS)]
    return clean.sort_values(["poi_type", "osm_type", "osm_id"]).reset_index(drop=True)


def calculate_outlet_poi_features(outlets: pd.DataFrame, pois: pd.DataFrame) -> pd.DataFrame:
    """Count all configured POI categories within 500m and 1000m."""

    features = outlets[["Outlet_ID"]].copy()
    for column in POI_COUNT_COLUMNS:
        features[column] = 0

    for poi_type in POI_TAGS:
        subset = pois.loc[pois["poi_type"].eq(poi_type)].copy()
        if subset.empty:
            continue

        counts_by_radius = count_pois_within_radii(outlets, subset, radii_m=RADII_M)
        for radius_m, counts in counts_by_radius.items():
            features[f"{poi_type}_{radius_m}m"] = counts

    for radius_m in RADII_M:
        radius_columns = [f"{poi_type}_{radius_m}m" for poi_type in POI_TAGS]
        features[f"total_poi_{radius_m}m"] = features[radius_columns].sum(axis=1)
        features[f"demand_driver_score_{radius_m}m"] = 0.0
        for poi_type, weight in DEMAND_DRIVER_WEIGHTS.items():
            features[f"demand_driver_score_{radius_m}m"] += weight * features[f"{poi_type}_{radius_m}m"]

    features["poi_available"] = features["total_poi_1000m"].gt(0)
    return features[OUTPUT_FEATURE_COLUMNS]


def count_pois_within_radii(
    outlets: pd.DataFrame,
    pois: pd.DataFrame,
    radii_m: tuple[int, ...] = RADII_M,
) -> dict[int, np.ndarray]:
    """Count nearby POIs with BallTree when available, otherwise haversine chunks."""

    try:
        from sklearn.neighbors import BallTree

        outlet_rad = np.radians(outlets[["Latitude", "Longitude"]].to_numpy(dtype=float))
        poi_rad = np.radians(pois[["latitude", "longitude"]].to_numpy(dtype=float))
        tree = BallTree(poi_rad, metric="haversine")
        return {
            radius_m: np.array(
                [len(matches) for matches in tree.query_radius(outlet_rad, r=radius_m / EARTH_RADIUS_M)],
                dtype=int,
            )
            for radius_m in radii_m
        }
    except Exception as exc:
        print(f"BallTree unavailable or failed ({exc}); using haversine fallback.")
        return count_pois_with_haversine_fallback(outlets, pois, radii_m=radii_m)


def count_pois_with_haversine_fallback(
    outlets: pd.DataFrame,
    pois: pd.DataFrame,
    radii_m: tuple[int, ...] = RADII_M,
    outlet_chunk_size: int = 250,
    poi_chunk_size: int = 5000,
) -> dict[int, np.ndarray]:
    """Chunked haversine fallback that avoids one request or loop per outlet."""

    outlet_coords = outlets[["Latitude", "Longitude"]].to_numpy(dtype=float)
    poi_coords = pois[["latitude", "longitude"]].to_numpy(dtype=float)
    counts = {radius_m: np.zeros(len(outlet_coords), dtype=int) for radius_m in radii_m}

    for outlet_start in range(0, len(outlet_coords), outlet_chunk_size):
        outlet_end = min(outlet_start + outlet_chunk_size, len(outlet_coords))
        outlet_chunk = outlet_coords[outlet_start:outlet_end]

        for poi_start in range(0, len(poi_coords), poi_chunk_size):
            poi_end = min(poi_start + poi_chunk_size, len(poi_coords))
            distances = haversine_matrix_m(outlet_chunk, poi_coords[poi_start:poi_end])
            for radius_m in radii_m:
                counts[radius_m][outlet_start:outlet_end] += (distances <= radius_m).sum(axis=1)

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
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(path, index=False)


def print_poi_type_summary(pois: pd.DataFrame) -> None:
    """Print POI counts by category."""

    if pois.empty:
        print("POIs by type: none")
        return

    counts = pois["poi_type"].value_counts().reindex(POI_TAGS.keys(), fill_value=0)
    summary = ", ".join(f"{poi_type}={int(count)}" for poi_type, count in counts.items())
    print(f"POIs by type: {summary}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tiled Overpass v2 POI scrape and outlet feature builder.")
    parser.add_argument("--input", type=Path, default=INPUT_PATH, help="Cleaned Silver outlet coordinates CSV.")
    parser.add_argument("--osm-output", type=Path, default=OSM_POIS_PATH, help="v2 OSM POI cache CSV.")
    parser.add_argument("--features-output", type=Path, default=OUTLET_FEATURES_PATH, help="v2 outlet feature CSV.")
    parser.add_argument("--tile-size", type=float, default=0.25, help="Tile size in decimal degrees.")
    parser.add_argument("--margin", type=float, default=0.02, help="Bounding box margin in decimal degrees.")
    parser.add_argument("--sleep-seconds", type=float, default=1.0, help="Pause between Overpass tile requests.")
    parser.add_argument("--overpass-url", default=OVERPASS_URL, help="Overpass API interpreter URL.")
    parser.add_argument(
        "--refresh-overpass",
        action="store_true",
        help="Query Overpass even if osm_pois_v2.csv already exists.",
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
        print(f"Existing v2 POI cache found: {args.osm_output}")
        print("Skipping Overpass API calls and recomputing outlet features only.")
        pois = load_existing_pois(args.osm_output)
    else:
        pois = fetch_pois_for_tiles(
            tiles=tiles,
            output_path=args.osm_output,
            overpass_url=args.overpass_url,
            sleep_seconds=args.sleep_seconds,
        )

    pois = dedupe_pois(pois)
    print(f"Final deduplicated POIs collected: {len(pois)}")
    print_poi_type_summary(pois)

    features = calculate_outlet_poi_features(outlets, pois)
    save_outlet_features(features, args.features_output)

    print(f"Final outlet feature rows: {len(features)}")
    print(f"Outlets with poi_available=True: {int(features['poi_available'].sum())}")
    print(f"v2 POI cache saved to: {args.osm_output}")
    print(f"v2 outlet POI features saved to: {args.features_output}")


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
