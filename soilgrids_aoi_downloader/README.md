# SoilGrids AOI Downloader

Plugin QGIS para descargar SoilGrids por AOI y profundidad arbitraria entre
0 y 60 cm. Usa GDAL para recortar/reproyectar y NumPy para ponderar por
espesor.

Salida por ejecucion:

- `01_CAPAS_PROFUNDIDAD`
- `02_AGREGADOS_PROFUNDIDAD`
- `03_STACK`
- `00_METADATA/resumen_soilgrids.json`

