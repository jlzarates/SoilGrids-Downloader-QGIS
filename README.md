# SoilGrids AOI Downloader para QGIS 3

Complemento QGIS para descargar variables SoilGrids de ISRIC a partir de un
poligono de delimitacion. El plugin recorta, reproyecta y genera agregados por
profundidad con ponderacion proporcional por espesor.

## Instalacion

1. Construya el ZIP con:

   ```powershell
   python build_zip.py
   ```

2. En QGIS abra **Complementos > Administrar e instalar complementos**.
3. Entre en **Instalar a partir de ZIP**.
4. Seleccione `dist/SoilGrids_AOI_Downloader_0.1.1.zip`.
5. Abra el panel desde **Web > SoilGrids AOI Downloader**.

## Uso

1. Cargue en QGIS una capa poligonal de delimitacion o indique un archivo
   `SHP/GPKG/GeoJSON`.
2. Seleccione las variables SoilGrids.
3. Defina la profundidad desde/hasta entre 0 y 60 cm.
4. Ajuste el buffer anti-borde. Por defecto son 750 m.
5. Seleccione carpeta de salida.
6. Pulse **Descargar SoilGrids**.

Para un intervalo como `0-20 cm`, el plugin usa estos pesos:

- `0-5 cm`: 5 cm
- `5-15 cm`: 10 cm
- `15-30 cm`: 5 cm

La formula general es:

```text
valor_agregado = sum(valor_capa * espesor_solapado) / sum(espesor_solapado)
```

Para reducir artefactos de borde, el plugin descarga y reproyecta primero con
un AOI bufferizado y despues aplica una mascara exacta con el poligono original.

## Salidas

Cada ejecucion crea una carpeta `SOILGRIDS_AAAAMMDD_HHMMSS` con:

- `01_CAPAS_PROFUNDIDAD`: capas SoilGrids descargadas y recortadas.
- `02_AGREGADOS_PROFUNDIDAD`: rasters ponderados por profundidad.
- `03_STACK`: stack multibanda opcional.
- `00_METADATA`: resumen JSON con AOI, variables, solapes y rutas.

## Variables

Disponibles en esta primera version:

- `bdod`
- `cec`
- `cfvo`
- `clay`
- `sand`
- `silt`
- `nitrogen`
- `phh2o`
- `soc`
- `ocd`
- `ocs`

`ocs` es un caso especial: SoilGrids lo publica como stock acumulado `0-30 cm`.
Si se pide otro intervalo, se omite con aviso.

## Supuestos

- QGIS 3.22 o superior.
- Windows con QGIS y GDAL funcional.
- AOI con CRS definido.
- CRS final por defecto: `EPSG:25830`.
- Agregacion vertical solo para `mean`.
- SoilGrids tiene resolucion aproximada de 250 m; no debe interpretarse con el
  detalle espacial de un MDT PNOA/LiDAR.
