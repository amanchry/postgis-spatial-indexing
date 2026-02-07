# Spatial Indexing Benchmark in PostGIS

This repository contains the code used to benchmark the impact of **spatial indexing** on common spatial queries in **PostGIS**.

Data Sources: https://data.crib.utwente.nl/bgp/netherlands.zip


```
# Create a  PostGIS database

createdb pdok_test
psql -d pdok_test -c "CREATE EXTENSION postgis;"


# Enable parallel execution:
psql -d pdok_test -c "SET max_parallel_workers_per_gather = 14;"
psql -d pdok_test -c "SET max_parallel_workers = 14;"


# import data in postgis (NO spatial index)

ogr2ogr -f PostgreSQL \
  PG:"dbname=pdok_test user=postgres password=1234" \
  point.shp \
  -nln neth_point \
  -nlt PROMOTE_TO_MULTI \
  -lco GEOMETRY_NAME=geom \
  -lco FID=gid \
  -lco SPATIAL_INDEX=NONE


ogr2ogr -f PostgreSQL \
  PG:"dbname=pdok_test user=postgres password=1234" \
  line.shp \
  -nln neth_line \
  -nlt PROMOTE_TO_MULTI \
  -lco GEOMETRY_NAME=geom \
  -lco SPATIAL_INDEX=NONE


ogr2ogr -f PostgreSQL \
  PG:"dbname=pdok_test user=postgres password=1234" \
  polygon.shp \
  -nln neth_poly \
  -nlt PROMOTE_TO_MULTI \
  -lco GEOMETRY_NAME=geom \
  -lco SPATIAL_INDEX=NONE


# Verify that spatial index exists or not
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('neth_point','neth_line','neth_poly')
ORDER BY tablename, indexname;



# Enable spatial indexing (GiST)
CREATE INDEX neth_point_gist ON neth_point USING GIST (geom);
CREATE INDEX neth_line_gist  ON neth_line  USING GIST (geom);
CREATE INDEX neth_poly_gist  ON neth_poly  USING GIST (geom);

# Update planner statistics
ANALYZE neth_point;
ANALYZE neth_line;
ANALYZE neth_poly;

```