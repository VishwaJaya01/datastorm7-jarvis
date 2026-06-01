"""Advanced Spatial Distance-Decay & Competitive Saturation Feature Builder.

Data Storm v7.0 - Final Round
"""

import os
from pathlib import Path
import numpy as np
import pandas as pd

def compute_advanced_spatial_features():
    """Reads cleaned silver coordinates and raw POI caches to generate continuous non-linear spatial signals."""
    
    # Establish relative project path structure
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    SILVER_DIR = PROJECT_ROOT / "data" / "silver"
    EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"
    
    input_coords_path = SILVER_DIR / "outlet_coordinates.csv"
    input_poi_path = EXTERNAL_DIR / "osm_pois_v2.csv"
    output_features_path = SILVER_DIR / "outlet_spatial_decay_features.csv"
    
    # Validation Guardrails
    if not input_coords_path.exists():
        raise FileNotFoundError(f"❌ Cleaned Silver coordinates not found at {input_coords_path}. Run silver_pipeline first!")
    if not input_poi_path.exists():
        raise FileNotFoundError(f"❌ Raw POI v2 cache not found at {input_poi_path}!")
        
    print("🚀 Initializing Vectorized Distance-Decay & Saturation Pipeline...")
    
    df_outlets = pd.read_csv(input_coords_path)
    df_pois = pd.read_csv(input_poi_path)
    
    outlet_coords = df_outlets[['Latitude', 'Longitude']].to_numpy()
    poi_coords = df_pois[['latitude', 'longitude']].to_numpy()
    EARTH_RADIUS_M = 6371000.0  # Earth's radius in meters
    
    def compute_decay_score(poi_type_list, scale_meters):
        """Applies decay_weight = exp(-distance / scale) across spatial matrices."""
        mask = df_pois['poi_type'].isin(poi_type_list)
        filtered_poi_coords = np.radians(poi_coords[mask])
        
        if len(filtered_poi_coords) == 0:
            return np.zeros(len(df_outlets))
        
        out_rad = np.radians(outlet_coords)
        
        # Pairwise Haversine Matrix Calculation
        dlat = out_rad[:, 0, None] - filtered_poi_coords[None, :, 0]
        dlon = out_rad[:, 1, None] - filtered_poi_coords[None, :, 1]
        a = np.sin(dlat/2)**2 + np.cos(out_rad[:, 0, None]) * np.cos(filtered_poi_coords[None, :, 0]) * np.sin(dlon/2)**2
        distances_meters = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
        
        # Apply exponential distance-decay function
        decay_matrix = np.exp(-distances_meters / scale_meters)
        return np.sum(decay_matrix, axis=1)

    print("🧠 Engineering Non-Linear Distance-Decay Features...")
    # Tailoring decay matrices based on your target specifications
    df_outlets['school_decay_score'] = compute_decay_score(['schools'], scale_meters=150.0)
    df_outlets['transit_decay_score'] = compute_decay_score(['bus_stops', 'railway_stations'], scale_meters=200.0)
    df_outlets['commercial_decay_score'] = compute_decay_score(['supermarkets', 'markets', 'restaurants', 'banks_atms'], scale_meters=300.0)
    df_outlets['overall_spatial_gravity_score'] = compute_decay_score(df_pois['poi_type'].unique().tolist(), scale_meters=250.0)

    print("⚔️ Engineering Competitive Catchment Saturation Metrics...")
    out_rad = np.radians(outlet_coords)
    dlat = out_rad[:, 0, None] - out_rad[None, :, 0]
    dlon = out_rad[:, 1, None] - out_rad[None, :, 1]
    a = np.sin(dlat/2)**2 + np.cos(out_rad[:, 0, None]) * np.cos(out_rad[None, :, 0]) * np.sin(dlon/2)**2
    inter_store_distances = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))
    
    # Density score calculation within a 500m radius threshold (excluding self-match)
    df_outlets['competitor_catchment_density'] = np.sum(inter_store_distances <= 500.0, axis=1) - 1

    # Extract clean final feature subset
    output_features = df_outlets[[
        'Outlet_ID', 'school_decay_score', 'transit_decay_score', 
        'commercial_decay_score', 'overall_spatial_gravity_score', 'competitor_catchment_density'
    ]]
    
    output_features.to_csv(output_features_path, index=False)
    print(f"🏆 SUCCESS: 20,000 retail vectors processed. Asset generated at: {output_features_path}")

if __name__ == "__main__":
    compute_advanced_spatial_features()