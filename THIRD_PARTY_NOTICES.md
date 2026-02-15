# Third-Party Notices

This repository includes generated map output and third-party libraries/assets.
The notices below summarize key licenses/attributions and point to upstream sources.

## Bundled / referenced software

- Leaflet (`js/leaflet.js`)  
  License: BSD-2-Clause  
  Source: https://github.com/Leaflet/Leaflet

- MapLibre GL JS (loaded from unpkg CDN)  
  License: BSD-3-Clause  
  Source: https://github.com/maplibre/maplibre-gl-js

- qgis2web (used to generate web map output)  
  License: GPL-2.0  
  Source: https://github.com/tomchadwin/qgis2web

- OSM Buildings (`js/OSMBuildings-Leaflet.js`)  
  License and third-party notices: see upstream `LICENSE.md`  
  Source: https://github.com/OSMBuildings/OSMBuildings

## Data / tiles / service attribution

- OpenStreetMap data  
  License: ODbL 1.0  
  Copyright: OpenStreetMap contributors  
  Source: https://www.openstreetmap.org/copyright

- OpenStreetMap standard tile service (`https://tile.openstreetmap.org/...`)  
  Usage policy (including limits): https://operations.osmfoundation.org/policies/tiles/

- OpenFreeMap Positron style (`https://tiles.openfreemap.org/styles/positron`)  
  OpenFreeMap attribution guidance: https://openfreemap.org/quick_start/  
  OpenFreeMap code license: MIT (upstream)  
  Source: https://github.com/hyperknot/openfreemap

- OSM Buildings hosted tiles (`https://{s}.data.osmbuildings.org/...`)  
  Terms of use: https://osmbuildings.org/documentation/terms-of-use/

## Notes for this project

- Keep map/data attribution visible in the map UI and attribution control.
- If publishing a high-traffic public site, review tile provider terms and move to a provider appropriate for expected load.
- If using hosted OSM Buildings data, verify allowed use for your deployment context.
