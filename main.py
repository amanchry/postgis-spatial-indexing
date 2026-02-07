import time
import statistics as stats
import psycopg
import csv
import geopandas as gpd

DSN = "host=localhost dbname=pdok_test user=postgres password=1234"

POINT_TBL = "neth_point"
LINE_TBL  = "neth_line"
POLY_TBL  = "neth_poly"

# OUT_CSV = "baseline_spatial_ops_index.csv"   
OUT_CSV = "baseline_spatial_ops_no_index.csv"  

SRID = 4326
DIST = 0.01   # degrees (SRID 4326 only)
REPEATS = 5
WARMUP = 1

POINTS_GEOJSON = "reference_points.geojson"


def run_cmd(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)


def run_scalar(conn, sql: str):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()[0]


def time_query(conn, sql: str, repeats=REPEATS, warmup=WARMUP):
    for _ in range(warmup):
        run_scalar(conn, sql)

    times = []
    val = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        val = run_scalar(conn, sql)
        t1 = time.perf_counter()
        times.append((t1 - t0) * 1000.0)
    return val, times


def load_ref_points(path: str, target_epsg: int = 4326):
    gdf = gpd.read_file(path)

    if gdf.empty:
        raise ValueError("GeoJSON is empty.")

    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=target_epsg)
    elif gdf.crs.to_epsg() != target_epsg:
        gdf = gdf.to_crs(epsg=target_epsg)

    gdf = gdf[gdf.geometry.type == "Point"].copy()
    if gdf.empty:
        raise ValueError("No Point geometries found in GeoJSON.")

    if "id" not in gdf.columns:
        gdf["id"] = range(1, len(gdf) + 1)

    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y

    return list(zip(gdf["id"].astype(str), gdf["lon"], gdf["lat"]))


def summarize(rows, operation, geom_type, ref_id, lon, lat, count_val, times):
    rows.append({
        "operation": operation,           # dwithin / intersects / contains
        "geometry_type": geom_type,       # points / lines / polygons
        "ref_point_id": ref_id,
        "longitude": float(lon),
        "latitude": float(lat),
        "matched_features": int(count_val),
        "median_ms": round(stats.median(times), 2),
        "avg_ms": round(stats.mean(times), 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
    })


def main():
    rows = []

    with psycopg.connect(DSN, autocommit=True) as conn:
        ref_points = load_ref_points(POINTS_GEOJSON, target_epsg=SRID)

        # Stabilize benchmark
        run_cmd(conn, "SET jit = off;")

        # Ensure baseline stats are current (do this for both phases in your full benchmark)
        for tbl in [POINT_TBL, LINE_TBL, POLY_TBL]:
            run_cmd(conn, f"ANALYZE {tbl};")

        for ref_id, lon, lat in ref_points:
            # Common geometries
            pt = f"ST_SetSRID(ST_Point({lon},{lat}), {SRID})"
            buf = f"ST_Buffer({pt}, {DIST})"  # buffer polygon around point (degrees)

            # ST_DWithin (points/lines/polygons near point) ---
            q_dwithin = {
                "points": f"SELECT count(*) FROM {POINT_TBL} WHERE ST_DWithin(geom, {pt}, {DIST});",
                "lines":  f"SELECT count(*) FROM {LINE_TBL}  WHERE ST_DWithin(geom, {pt}, {DIST});",
                "polygons":f"SELECT count(*) FROM {POLY_TBL}  WHERE ST_DWithin(geom, {pt}, {DIST});",
            }

            # ST_Intersects (features intersect buffer polygon) ---
            q_intersects = {
                "points": f"SELECT count(*) FROM {POINT_TBL} WHERE ST_Intersects(geom, {buf});",
                "lines":  f"SELECT count(*) FROM {LINE_TBL}  WHERE ST_Intersects(geom, {buf});",
                "polygons":f"SELECT count(*) FROM {POLY_TBL}  WHERE ST_Intersects(geom, {buf});",
            }

            # ST_Contains (polygons that contain the point) ---
            # Only meaningful for polygons (contains a point).
            q_contains = {
                "polygons": f"SELECT count(*) FROM {POLY_TBL} WHERE ST_Contains(geom, {pt});"
            }

            # Run dwithin
            for geom_type, sql in q_dwithin.items():
                count_val, times = time_query(conn, sql)
                summarize(rows, "ST_DWithin", geom_type, ref_id, lon, lat, count_val, times)
                print(f"ST_DWithin | {geom_type} | ref {ref_id}: count={count_val}, median={stats.median(times):.2f} ms")

            # Run intersects
            for geom_type, sql in q_intersects.items():
                count_val, times = time_query(conn, sql)
                summarize(rows, "ST_Intersects", geom_type, ref_id, lon, lat, count_val, times)
                print(f"ST_Intersects | {geom_type} | ref {ref_id}: count={count_val}, median={stats.median(times):.2f} ms")

            # Run contains (polygons only)
            for geom_type, sql in q_contains.items():
                count_val, times = time_query(conn, sql)
                summarize(rows, "ST_Contains", geom_type, ref_id, lon, lat, count_val, times)
                print(f"ST_Contains | {geom_type} | ref {ref_id}: count={count_val}, median={stats.median(times):.2f} ms")

    # Write CSV
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote results to {OUT_CSV}")


if __name__ == "__main__":
    main()
