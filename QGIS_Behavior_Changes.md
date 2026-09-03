# QGIS Behavior Changes Log

This document lists every behavioral change applied to the QGIS side of a tool during the
ArcGIS/QGIS merge, in order to make the merged common logic follow the ArcGIS behavior (the
more up-to-date reference implementation, per project instructions). Each entry describes what
the QGIS tool used to do, what it does now, and why.

Gaps that were intentionally left unmerged/deferred are also listed at the end.

---

## AssignPointToClosestPointOnRoute

- **CLOSEST/MEAN/MAX aggregation modes reconciled with ArcGIS.** The QGIS implementation had
  diverged from ArcGIS in how it aggregated multiple candidate matches per point; the merged
  common logic now follows the ArcGIS aggregation rules exactly for `CLOSEST`, `MEAN`, and `MAX`.
- **QGIS-only "2-WAY CLOSEST" mode preserved as an extra option.** This mode does not exist in
  ArcGIS. It was kept as an additional, clearly-labeled option rather than removed, since it does
  not conflict with any ArcGIS behavior and may still be useful to QGIS users.

## BedAssessment

- **Solver corrected from `Solver1Dnormal` to `SolverDirect` (most significant fix).** The QGIS
  tool was wired to use the `Solver1Dnormal` solver, while the ArcGIS tool (the authoritative,
  up-to-date version) uses `SolverDirect`. These solvers produce materially different bed-level
  results. The merged common logic now always uses the `SolverDirect` algorithm, matching ArcGIS.

## D4FlowDirection

- **Nodata sentinel value.** QGIS used `-9999`; ArcGIS (and the rest of the merged toolchain,
  e.g. Tiling) uses `-255`. Standardized on `-255` to match ArcGIS.
- **Raster-alignment check added.** ArcGIS silently assumes flow-direction and fill rasters are
  aligned; the merge added an explicit alignment check (raising a clear error) rather than
  silently producing wrong results if the two rasters don't share the same grid — this is a
  stricter safety net, not a behavior regression, and only triggers on already-invalid inputs.
- **`y_to_row` edge case fixed.** The QGIS row/column conversion helper mishandled a boundary
  coordinate case (point exactly on the last row); corrected to match ArcGIS's `RasterIO`
  behavior.

## WSsmoothing

- **Distance accumulation across reach boundaries fixed.** QGIS's along-network distance
  accumulation reset incorrectly at reach transitions in some topologies; corrected to match
  ArcGIS's continuous accumulation logic.
- **`get_lower_bound` helper fixed.** Off-by-one/boundary selection bug in the QGIS smoothing
  window lookup corrected to match ArcGIS.
- **Ramer-Douglas-Peucker (RDP) simplification step ported in.** ArcGIS applies an RDP
  simplification pass as part of the smoothing workflow that was missing from the QGIS
  implementation; it has been ported into the merged common logic so QGIS output now matches
  ArcGIS's simplified geometry.

## InterpolatePoints

- **Boundary points now always added per reach.** QGIS only added upstream/downstream boundary
  interpolation points when a reach had zero in-reach data points. ArcGIS always adds one
  upstream and one downstream boundary point per reach regardless of how many in-reach points
  exist. The merged common logic now always adds both boundary points, matching ArcGIS.

## LocatePointsAlongRoutes

- **Full attribute preservation.** QGIS stripped output features down to only `id`/`RID`/`MEAS`.
  ArcGIS preserves all original point attributes and appends the route-id/measure fields. The
  merged common logic now preserves all input point attributes, matching ArcGIS.
- **Duplicate-RID route segments no longer dropped.** QGIS built a `routes-by-RID` dictionary
  that silently kept only one segment per RID, discarding other segments sharing the same RID
  (e.g. multi-part routes). The merged logic now processes every route feature/segment,
  matching ArcGIS.

## RunHydraulicSim

- **Retry timeout corrected from 7200s to 3600s**, matching ArcGIS.
- **Discharge/zfield matching order fixed.** QGIS matched discharge values to z-field boundary
  conditions using suffix-based string matching and sorted discharges alphabetically. ArcGIS
  matches them using an ordered-list/positional correspondence and preserves the original
  (non-alphabetical) discharge order. The merged logic now follows the ArcGIS ordered-matching
  approach.
- **Boundary-condition writer coordinate order fixed** to match ArcGIS's expected axis order.
- **Turned-edge downstream sampling side fixed** to sample on the same side as ArcGIS for
  turned/bent reach edges.
- Ported ArcGIS-style `log_message`, `check_mass_file`, and `check_simulation_time` helpers into
  the common logic so QGIS gets the same run-time diagnostics and mass-balance/timing checks
  ArcGIS already had.

## Tiling

- **Nodata sentinel aligned from `-9999` to `-255`**, matching ArcGIS/D4FlowDirection convention.
- **QGIS-only "exiting lake" branch removed.** This branch set an unused `distance` attribute
  and had no ArcGIS equivalent; verified it did not affect actual output coordinates or raster
  values, and removed for parity with ArcGIS.
- **Lake segment-number indexing bug resolved.** The ArcGIS source contained
  `lakes_bci[segnumber] = shplakes[5]`, which indexes the cursor object itself rather than the
  current row's field value — almost certainly a latent ArcGIS source bug. Rather than
  reproducing the literal bug, the merged common logic implements the clearly-intended behavior
  (reading the actual field value from the current row).

## HydraulicSimPrep

- **Clip rasters now locked to the `zone{N}` template grid (most impactful fix).** ArcGIS clips
  the width/zbed/manning/mask rasters using `in_template_dataset=zone{N}` with
  `MAINTAIN_EXTENT`, forcing them to be pixel-for-pixel aligned to the already-created
  `zone{N}.tif` DEM clip. QGIS instead independently re-snapped each of these rasters to its own
  native grid — QGIS's own code comments documented this only reproduced the ArcGIS reference
  output correctly for 48 of 62 test zones. The merged common logic now locks all four clips to

## LocateMostDownstreamPoints

- **Missing-reach datapoints now hard-fail.** The QGIS-side path had been allowing reaches with
  no datapoint to drop out silently; ArcGIS assumes every reach has a datapoint and fails loudly
  instead. The merged common logic now raises an error, matching ArcGIS.

## RelateNetworks

- **Equal-feature-count requirement restored.** The QGIS metatool code had been calling the
  relate step with `strict_count=False`; ArcGIS requires the two input networks to have equal
  row counts. The merged logic now enforces the ArcGIS requirement.
- **Duplicate RID output-name collision normalized.** When both input networks use the same RID
  field name, the merged output now writes the second one as `RID_1` (or `<RID_B>_1`) instead of
  relying on QGIS-only assumptions about field naming.

## TopologicalRelateNetworks

- **ArcGIS topological-difference warning restored.** The QGIS-side path was missing ArcGIS's
  warning message when the upstream/downstream path lengths differ between the two networks
  being compared. The merged logic now emits that warning.

## CreateNetworkFromFlowDir

- **ArcGIS `ORIG_FID` behavior kept.** The old QGIS-side flow-direction tracing workflow used a
  `RID_routesmain` back-reference pattern to link traced D8 features to their source reach.
  ArcGIS instead writes an `ORIG_FID` field from the seed from-point. The merged raw tracing tool
  now keeps the ArcGIS `ORIG_FID` behavior; downstream tools use `RelateNetworks`'s output table
  as the crosswalk instead of a baked-in back-reference field.

## FlowDirectionNetwork

- **Removed QGIS-only post-relate D8 RID backfill.** The old QGIS meta-tool rewrote the traced
  D8 output after `RelateNetworks` to carry original-network RID values (`RID_routesmain`).
  ArcGIS does not do this. The merged workflow now leaves the traced D8 output in ArcGIS form and
  relies on the `RelateNetworks` relate table as the crosswalk between the two networks.

## CreateNetworkFromFC

- **Legacy QGIS wrapper path removed in favor of the ArcGIS-authoritative network build.** The
  standalone QGIS-specific tool logic was replaced by the common ArcGIS-authoritative path
  (through the shared `RiverNetworkTools` engine plus the platform I/O helpers), eliminating the
  old QGIS-side divergence point in how the initial network graph was built from a line feature
  class.

  the `zone{N}` template's exact geotransform/dimensions, matching ArcGIS and fixing the
  remaining 14 mismatched zones.
- **Nodata value preservation fixed.** QGIS hardcoded `dstNodata=-9999` for every clipped
  raster. The merged logic now preserves each source raster's own native nodata value, matching
  ArcGIS.
- **Raster-alignment mismatch now hard-fails.** ArcGIS logs a warning and continues if a
  mismatch is detected; the merged logic raises an error instead, which is safer given the
  above grid-alignment fix is critical to correct output. This is a deliberate strengthening,
  not a behavior regression relative to ArcGIS's documented intent.

## BridgeCorrection

- **Hydrological fill step restored.** The QGIS implementation only pasted each bridge zone's
  minimum DEM value back into bridge pixels. ArcGIS replaces bridge zones with their minimum
  elevation, then runs a fill and writes the filled values back only on bridge cells. The merged
  logic now follows the ArcGIS sequence.
- **Bridge rasterization narrowed from QGIS `ALL_TOUCHED` polygons to ArcGIS polygon-plus-boundary
  rasterization.** QGIS had been rasterizing full polygons with `ALL_TOUCHED=TRUE`, which can
  widen corrected bridge footprints by extra edge pixels. The merged logic now matches ArcGIS's
  authoritative polygon/interior + polygon-boundary combination on the DEM grid.
- **Manual NoData parameter removed.** QGIS exposed a user-entered NoData value (default `-9999`).
  ArcGIS uses the input DEM's own native NoData value. The merged logic now reads and preserves
  the source raster's actual NoData definition.

## BatchProcessAggregate

- **Aggregation options reconciled with ArcGIS.** QGIS exposed `average/median/mode/minimum/maximum`.
  ArcGIS exposes `SUM/MAXIMUM/MEAN/MEDIAN/MINIMUM`. The merged tool now uses the ArcGIS option set
  and semantics, so QGIS's old `mode` behavior is replaced by ArcGIS `SUM`.
- **Extent-handling parameter restored.** The old QGIS tool always expanded/snap-aligned extents in
  its own GDAL-specific way. ArcGIS has an explicit `EXPAND` vs `TRUNCATE` choice. The merged
  logic now follows the ArcGIS extent-handling modes exactly.
- **Cross-raster snap alignment now follows ArcGIS.** ArcGIS aggregates the first raster, then uses
  that aggregated output as the snap raster for all subsequent rasters. The old QGIS tool snapped
  each raster independently to target-resolution multiples. The merged logic now matches ArcGIS's
  first-output snap behavior.

## FlowDirectionForWS

- **Outlet detection changed from "all boundary crossings" to ArcGIS start-vertex exits.** The old
  QGIS implementation opened the wall at every route/footprint boundary crossing. ArcGIS intersects
  each footprint with `routes_main`, converts the resulting in-footprint line segments to START
  points, and only buffers those start points as exits. The merged logic now follows the ArcGIS
  outlet selection.
- **Per-footprint output naming aligned to ArcGIS.** QGIS wrote `fd_{oid}.tif`; ArcGIS writes
  `dem{OID}` datasets in the chosen output workspace. The merged logic now uses the ArcGIS naming
  convention (`dem{oid}`; `.tif` is added automatically on the QGIS file-system side).
- **Whitebox workflow now mirrors ArcGIS fill/flow-direction steps more closely.** The old QGIS
  tool used a QGIS-specific valid-boundary-crossing workflow plus `BreachDepressions`. The merged
  logic now constructs the ArcGIS-style walled DEM first, then runs the standard fill followed by
  D8 flow direction, matching the ArcGIS sequence.

## SpatializeQLIDARFromGaugingStations

- **Per-discharge upstream/downstream station selection corrected.** The old QGIS metatool kept
  one combined upstream/downstream station set across all LiDAR discharge days, so a station
  missing a value for one day could still influence that day's interpolation. The merged common
  logic now matches ArcGIS by selecting usable reference stations independently for each discharge
  day.
- **QGIS-only `RID_routesmain` dependency removed.** The old QGIS wrapper relied on a QGIS-specific
  `RID_routesmain` field carried on `routesD8`. ArcGIS uses the external D8-to-main-network relate
  table instead. The merged tool now follows ArcGIS and uses the relate table as the authoritative
  crosswalk.
- **Output schema aligned to ArcGIS.** QGIS previously copied the full `pathpointsD8` attribute set
  and renamed the original D8 RID field. The merged tool now writes the ArcGIS-style reduced D8
  point fields and adds the relate-table crosswalk fields separately.
- **Missing gauging-station CSV columns now fail immediately.** The old QGIS implementation only
  warned and skipped stations absent from the CSV. ArcGIS treats that situation as an error
  condition. The merged tool now stops with a clear error instead of silently computing from an
  incomplete station set.

## SpatializeQFloodFromGaugingStations

- **Station location step restored.** The old QGIS wrapper expected RID/MEAS to already exist on
  the gauging-station layer and never re-located stations to the D8 network. ArcGIS always runs
  the locate-along-route step inside the tool. The merged tool now does the ArcGIS locate step
  internally, using the supplied search distance.
- **Output fields aligned to ArcGIS.** QGIS previously preserved the full `pathpointsD8` schema.
  The merged flood-discharge tool now writes the ArcGIS-style D8-point fields plus the computed
  scenario field named after the selected discharge field.
- **No additional flood-mode discrepancy remained after restoring the ArcGIS locate step.** Flood
  mode carries only one discharge scenario at a time, so once station location was reconciled, the
  remaining browse/interpolation logic already matched the ArcGIS single-scenario behavior.

## SpatializeQ

- **No prior documented QGIS implementation existed to reconcile.** This merge introduces a new
  QGIS interface for the detailed `SpatializeQ` tool and wires it directly to the
  ArcGIS-authoritative common logic.
- **ArcGIS downstream-first / upstream-fallback reference-point behavior preserved.** The merged
  tool keeps the original ArcGIS drainage-area scaling workflow for choosing the controlling
  reference discharge point, so there was no separate QGIS behavior change beyond exposing the tool
  in QGIS.

## WatershedScaleDEMprocessing

- **New QGIS orchestration tool added.** There had been no prior single QGIS tool for the full
  watershed-scale DEM-preparation workflow. The merge adds a new `QGIS_WatershedScaleDEMprocessing`
  metatool that mirrors ArcGIS's one-click sequence: rasterize burn masks, burn the DEM, fill,
  compute D8 flow direction and flow accumulation, build both river-network variants, trace the D8
  network, and assign `Qorder`.
- **Flow accumulation is computed from the D8 pointer raster in WhiteboxTools pointer mode.**
  QGIS now runs `wbt:D8FlowAccumulation` with `pntr=True`, `esri_pntr=True`, `out_type='cells'`,
  `log=False`, and `clip=False` so the accumulation surface matches ArcGIS's expected ESRI-coded
  D8, cell-count workflow as closely as the available QGIS building blocks allow.
- **Documented caveat: WhiteboxTools remains the hydrology engine on QGIS.** Even with ESRI-pointer
  mode enabled, local tie-breaking, edge handling, and NoData propagation remain WhiteboxTools
  implementation details rather than ArcGIS Spatial Analyst internals, so minor raster-value
  differences may still occur near ambiguous-flow or boundary cases.

## LisfloodDataConversion

- **New QGIS orchestration tool added.** There had been no prior one-click QGIS metatool for the
  Lisflood D4 conversion workflow. The merge adds `QGIS_LisfloodDataConversion`, wired directly to
  the ArcGIS-authoritative shared logic: derive D4 flow direction, trace the D4 network, copy
  `Qorder`, project bathymetry/width to D4 path points, interpolate, and rasterize the final
  values.
- **Relate-table field transfer is now handled explicitly in portable code.** ArcGIS used layered
  `AddJoin`/`CalculateField` steps to move `Qorder` from `routes_main` onto `routesD4`. The merged
  workflow performs the same transfer through a shared relate-table lookup helper so QGIS gets the
  same output field without relying on ArcGIS-only join state.
- **Documented caveat: QGIS rasterization uses a GDAL-aligned custom "most frequent per cell"
  pass.** QGIS does not have a direct `PointToRaster(..., MOST_FREQUENT)` equivalent for this
  workflow, so the merge rasterizes against the flow-direction grid in shared snapped coordinates
  and resolves equal-frequency ties by first-seen point order. This preserves ArcGIS-style grid
  alignment and modal aggregation, but tie outcomes may differ from ArcGIS's undocumented internal
  tie-breaker in cells containing multiple distinct values with identical counts.

## ExtractWaterSurface

- **Legacy QGIS's simple network-pair relate was replaced by ArcGIS's topological upstream-fit
  crosswalk.** The old QGIS tool called `relate_networks(...)` directly on the two route layers and
  wrote a simple `RID_main`/`RID_D8`/`PART_COUNT` table. The merged tool now runs the shared
  `execute_CheckNetFitFromUpStream(..., final_selection="ENDS")` step first, using the supplied
  D8/main links tables plus `frompoints`, and writes the ArcGIS-style relate table with
  match-quality fields (`MATCH_ID`, `TYPO`, `CLOSEST`, `SCORE`).
- **D8 path-point sampling now follows ArcGIS's X/Y-driven workflow.** The legacy QGIS tool trusted
  the input point geometry and even reused an existing `lidar3m_forws` attribute if it was already
  present. The merged workflow materializes/samples from the supplied X/Y fields every run and names
  the sampled field from the selected raster's basename, matching ArcGIS's
  `MakeXYEventLayer + ExtractMultiValuesToPoints` pattern instead of the old hard-coded/reuse path.
- **QGIS raster sampling now uses a shared GDAL point-sampler helper with explicit outside/NoData
  handling.** ArcGIS uses Spatial Analyst's `ExtractMultiValuesToPoints`; QGIS now uses the new
  `sample_raster_at_points(...)` helper, which returns `None` for points outside the raster extent
  or on NoData cells. Grid-boundary outcomes therefore follow the repo's shared GDAL row/column math
  rather than ArcGIS Spatial Analyst internals in those edge cases.
- **Target-point geometry is now rebuilt from RID/MEAS on the main routes before assignment and
  interpolation.** The legacy QGIS tool operated on the incoming target-point geometry directly. The
  merged workflow re-materializes route-event points from the target table's RID/measure fields,
  matching ArcGIS and snapping any slightly off-route legacy inputs back onto the route geometry.
- **Output registration and schemas now match the ArcGIS/main-toolbox workflow.** The QGIS wrapper
  moved from the old `"ConcordiaRiverLab-FloodTools: Modeling"` group to the main
  `"Large Scale Flood Modelling Toolbox"` group/groupId, and the final smoothed-points output now
  follows the ArcGIS `execute_WSprocessing` field set (target id/RID/measure, sampled water-surface
  field, DEM id, and smoothing fields) instead of copying every target-point attribute.
- **`2-WAY CLOSEST` assignment was kept explicitly.** No QGIS divergence remained here: the legacy
  QGIS tool was already using `stat="2-WAY CLOSEST"`, which matches the ArcGIS-authoritative 2021
  update, so the merged shared workflow preserves that mode unchanged.

## ExtractDischarges

- **New QGIS detailed tool added.** There had been no prior QGIS implementation of
  `ExtractDischarges`; the merge adds `QGIS_ExtractDischarges`, wired directly to the
  ArcGIS-authoritative shared `ExtractDischarges.py` workflow, and registers it in the
  `"Large Scale Flood Modelling Toolbox - Detailed Tools"` / `large_scale_flood_modelling_toolbox_detailed_tools`
  group.
- **ArcGIS's `SpatialJoin(..., CLOSEST, search_radius=0.1)` step is now exposed through a shared
  `snap_points_to_nearest_line(...)` helper on both GIS backends.** The merged QGIS path uses a
  spatial index plus the repo's shared point-to-segment distance math to choose the nearest line
  within the requested tolerance, so it matches ArcGIS's 0.1-unit snap-tolerance intent without
  depending on ArcGIS-only join state.
- **Documented caveat: exact nearest-line ties are resolved deterministically but may not be
  identical to ArcGIS in edge cases.** The QGIS helper keeps the first-seen candidate line when two
  lines are at the same computed distance (within floating-point tolerance), whereas ArcGIS
  `SpatialJoin`'s internal `CLOSEST` tie-breaker is undocumented; both implementations also drop
  unmatched points when a tolerance is supplied.

## WidthByCrossSections

- **New QGIS main-toolbox tool added.** There had been no prior QGIS implementation of
  `WidthByCrossSections`; the merged tool adds `QGIS_WidthByCrossSections`, wired directly to the
  new shared `WidthByCrossSections.py` entry point and registered in the main
  `"Large Scale Flood Modelling Toolbox"` / `large_scale_flood_modelling_toolbox` group.
- **Confluence/source/outlet classification is rebuilt from routed line endpoints rather than ArcGIS's
  `FeatureVerticesToPoints(..., DANGLE)` tool.** The QGIS port counts coincident start/end coordinates
  (rounded to a small tolerance) to identify dangles and confluences, so slightly unsnapped network
  endpoints may classify differently than ArcGIS's native topology tool.
- **Variable-radius confluence buffers are generated with PyQGIS geometry buffering after nearest-bank
  distance lookup.** The hard-coded `NEAR_DIST + 8m` rule is preserved, but equal-distance bank ties and
  the segmented approximation of round buffers remain QGIS geometry-engine details rather than ArcGIS
  Spatial Analyst internals.
- **Buffered confluence trimming keeps the matching-route segment that touches the original endpoint and,
  if several candidates remain, prefers the longest touching segment.** This reproduces the legacy
  "correct branch only" intent without relying on ArcGIS's `Intersect(..., LINE)` output ordering, whose
  tie-break behavior is undocumented when a reach re-enters the same buffer.
- **Cross-section offsets are generated from the local route-segment direction at each `Distance_m`
  measure instead of ArcGIS `MakeRouteEventLayer`'s internal offset normal.** This is a close geometric
  equivalent on ordinary reaches, but at an exact bend vertex the chosen local segment can yield a
  slightly different perpendicular than ArcGIS.
- **Riverbank clipping and crossing cleanup use explicit `QgsGeometry` intersection counting rather than
  ArcGIS `SplitLineAtPoint` / `Intersect(..., ONLY_FID)` / `Statistics` pipelines.** The same `0.05m`,
  `0.1m`, and `1m` tolerances plus the `5→3` iterative cleanup loop are preserved, but near-coincident
  touches, overlapping segments, and exact tie cases can be counted or pruned slightly differently by
  the QGIS geometry engine.
- **Final point-to-transect transfer keeps the closest surviving transect within `1m`.** ArcGIS's
  `SpatialJoin(..., WITHIN_A_DISTANCE, JOIN_ONE_TO_ONE)` does not document how equal-distance ties are
  broken, so only degenerate cases with multiple surviving transects inside the hard-coded `1m`
  tolerance may differ.

## WidthPostProc

- **New QGIS main-toolbox tool added.** There had been no prior QGIS implementation of
  `WidthPostProc`; the merge adds `QGIS_WidthPostProc`, wired directly to the new shared
  `WidthPostProc.py` workflow and registered in the main
  `"Large Scale Flood Modelling Toolbox"` / `large_scale_flood_modelling_toolbox` group.
- **Split-to-unsplit reach matching now uses midpoint snapping to the nearest main-network line
  rather than ArcGIS `SpatialJoin(..., WITHIN)`.** The shared workflow materializes one midpoint per
  split reach and resolves its containing/parent unsplit RID through the repo's shared
  `snap_points_to_nearest_line(...)` helper. This is equivalent when split reaches lie cleanly on
  their parent main route, but exact containment-tie behavior is now the helper's deterministic
  nearest-line rule rather than ArcGIS's undocumented `WITHIN` join internals.
- **Secondary-channel reprojection uses the shared `locate_features_along_routes_records(...)`
  wrapper against the explicitly identified downstream main reach.** ArcGIS still remains the
  behavioral reference for the overall downstream-main-reach selection, but QGIS measure placement
  comes from PyQGIS nearest-point / `lineLocatePoint()` calculations inside that shared helper
  instead of ArcGIS `LocateFeaturesAlongRoutes` internals, so tiny measure differences can occur on
  sharply segmented or numerically ambiguous geometries.
- **The legacy numpy-structured-array implementation was translated to `RiverNetworkTools`
  `PointsCollection`/`DataPoint` objects plus list-of-dict row buffers.** The downstream walk,
  inversion detection, furthest-boundary-point search, per-secondary zero-width boundary insertion,
  and additive interpolation sequence were kept 1:1, but any edge-case differences now come from
  Python object ordering / float coercion rather than numpy record-array mechanics.
- **Final route-event materialization is rebuilt from route vertices instead of ArcGIS
  `MakeRouteEventLayer`.** The shared helper clamps measures to the route length and interpolates XY
  directly along the stored vertices, which is portable across ArcGIS and QGIS but can differ by
  sub-segment floating-point details from ArcGIS's native route-event layer engine.

---

## Deferred / not merged in this pass

- **"Create by-day LAS files" (`LASfiles_preprocessing*.py`)** — documented in the ArcGIS
  methodology, with no QGIS equivalent. Left as ArcGIS-only per explicit scope decision; not
  reconciled or ported.
