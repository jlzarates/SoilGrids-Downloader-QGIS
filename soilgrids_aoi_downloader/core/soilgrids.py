"""Utilidades GDAL para descargar y agregar SoilGrids."""

from __future__ import absolute_import

import json
import os
from datetime import datetime

import numpy as np
from osgeo import gdal


DATA_URL = "https://files.isric.org/soilgrids/latest/data"
SOILGRIDS_SOURCE_SRS = "ESRI:54052"
NODATA = -9999.0

DEPTHS = [
    ("0-5cm", 0, 5),
    ("5-15cm", 5, 15),
    ("15-30cm", 15, 30),
    ("30-60cm", 30, 60),
]

PROPERTIES = {
    "bdod": "Densidad aparente de tierra fina",
    "cec": "Capacidad de intercambio cationico",
    "cfvo": "Fragmentos gruesos volumetricos",
    "clay": "Arcilla",
    "sand": "Arena",
    "silt": "Limo",
    "nitrogen": "Nitrogeno total",
    "phh2o": "pH en agua",
    "soc": "Carbono organico del suelo",
    "ocd": "Densidad de carbono organico",
    "ocs": "Stock de carbono organico 0-30 cm",
}

CONTINUOUS_PROPERTIES = [
    "bdod",
    "cec",
    "cfvo",
    "clay",
    "sand",
    "silt",
    "nitrogen",
    "phh2o",
    "soc",
    "ocd",
]


class SoilGridsError(Exception):
    """Error controlado del flujo SoilGrids."""


def safe_name(value):
    allowed = []
    for char in str(value):
        if char.isalnum() or char in ("_", "-"):
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed)


def unique_job_directory(base_directory):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = "SOILGRIDS_{0}".format(stamp)
    candidate = os.path.join(base_directory, base_name)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(base_directory, "{0}_{1}".format(base_name, counter))
        counter += 1
    os.makedirs(candidate)
    return candidate


def depth_overlaps(depth_from, depth_to):
    if depth_from < 0 or depth_to > 60 or depth_from >= depth_to:
        raise SoilGridsError("La profundidad debe cumplir 0 <= desde < hasta <= 60 cm.")

    overlaps = []
    for label, lower, upper in DEPTHS:
        overlap = max(0, min(depth_to, upper) - max(depth_from, lower))
        if overlap > 0:
            overlaps.append(
                {
                    "label": label,
                    "lower_cm": lower,
                    "upper_cm": upper,
                    "weight_cm": overlap,
                }
            )
    if not overlaps:
        raise SoilGridsError("No hay capas SoilGrids para el intervalo solicitado.")
    return overlaps


def vrt_url(propiedad, profundidad, estadistico):
    layer = "{0}_{1}_{2}".format(propiedad, profundidad, estadistico)
    return "/vsicurl/{0}/{1}/{2}.vrt".format(DATA_URL, propiedad, layer)


def layer_filename(propiedad, profundidad, estadistico, epsg):
    layer = "{0}_{1}_{2}".format(propiedad, profundidad, estadistico)
    return "SG_{0}_EPSG{1}.tif".format(safe_name(layer), epsg)


def aggregate_filename(propiedad, depth_from, depth_to, estadistico, epsg):
    return "SG_{0}_{1}-{2}cm_{3}_ponderado_EPSG{4}.tif".format(
        safe_name(propiedad), int(depth_from), int(depth_to), safe_name(estadistico), epsg
    )


def warp_soilgrids_layer(
    source_url,
    output_path,
    aoi_path,
    epsg_destino,
    resolution_m=None,
    overwrite=True,
):
    if os.path.exists(output_path) and not overwrite:
        return output_path

    options = {
        "format": "GTiff",
        "srcSRS": SOILGRIDS_SOURCE_SRS,
        "dstSRS": "EPSG:{0}".format(epsg_destino),
        "cutlineDSName": aoi_path,
        "cropToCutline": True,
        "dstNodata": NODATA,
        "multithread": True,
        "resampleAlg": "bilinear",
        "creationOptions": ["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    }
    if resolution_m:
        options["xRes"] = float(resolution_m)
        options["yRes"] = float(resolution_m)
        options["targetAlignedPixels"] = True

    result = gdal.Warp(output_path, source_url, **options)
    if result is None:
        raise SoilGridsError("GDAL no pudo crear {0}".format(output_path))
    result.FlushCache()
    result = None
    return output_path


def mask_raster_to_aoi(input_path, output_path, aoi_path, nodata=NODATA):
    """Aplica mascara exacta del AOI conservando la grilla del raster de entrada."""
    source = gdal.Open(input_path)
    if source is None:
        raise SoilGridsError("No se pudo abrir raster para mascara: {0}".format(input_path))
    gt = source.GetGeoTransform()
    x_size = source.RasterXSize
    y_size = source.RasterYSize
    min_x = gt[0]
    max_y = gt[3]
    max_x = min_x + gt[1] * x_size
    min_y = max_y + gt[5] * y_size
    x_res = abs(gt[1])
    y_res = abs(gt[5])
    projection = source.GetProjection()
    source = None

    result = gdal.Warp(
        output_path,
        input_path,
        format="GTiff",
        dstSRS=projection,
        outputBounds=(min_x, min_y, max_x, max_y),
        xRes=x_res,
        yRes=y_res,
        targetAlignedPixels=False,
        cutlineDSName=aoi_path,
        cropToCutline=False,
        dstNodata=nodata,
        multithread=True,
        resampleAlg="near",
        warpOptions=["INIT_DEST=NO_DATA"],
        creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if result is None:
        raise SoilGridsError("No se pudo aplicar mascara exacta: {0}".format(output_path))
    result.FlushCache()
    result = None
    return output_path


def weighted_average_rasters(raster_paths, weights, output_path, nodata=NODATA):
    if len(raster_paths) != len(weights):
        raise SoilGridsError("Numero de rasters y pesos no coincide.")
    if not raster_paths:
        raise SoilGridsError("No hay rasters para agregar.")

    datasets = [gdal.Open(path) for path in raster_paths]
    if any(ds is None for ds in datasets):
        missing = [path for path, ds in zip(raster_paths, datasets) if ds is None]
        raise SoilGridsError("No se pudieron abrir rasters: {0}".format(", ".join(missing)))

    base = datasets[0]
    x_size = base.RasterXSize
    y_size = base.RasterYSize
    geotransform = base.GetGeoTransform()
    projection = base.GetProjection()

    for path, ds in zip(raster_paths[1:], datasets[1:]):
        if ds.RasterXSize != x_size or ds.RasterYSize != y_size:
            raise SoilGridsError("Raster no alineado: {0}".format(path))
        if ds.GetGeoTransform() != geotransform:
            raise SoilGridsError("Geotransform distinto en: {0}".format(path))

    driver = gdal.GetDriverByName("GTiff")
    out = driver.Create(
        output_path,
        x_size,
        y_size,
        1,
        gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if out is None:
        raise SoilGridsError("No se pudo crear {0}".format(output_path))

    out.SetGeoTransform(geotransform)
    out.SetProjection(projection)
    out_band = out.GetRasterBand(1)
    out_band.SetNoDataValue(nodata)

    block_x, block_y = base.GetRasterBand(1).GetBlockSize()
    if block_x <= 0:
        block_x = min(512, x_size)
    if block_y <= 0:
        block_y = min(512, y_size)

    weights = np.asarray(weights, dtype="float32")
    for y in range(0, y_size, block_y):
        rows = min(block_y, y_size - y)
        for x in range(0, x_size, block_x):
            cols = min(block_x, x_size - x)
            numerator = np.zeros((rows, cols), dtype="float64")
            denominator = np.zeros((rows, cols), dtype="float64")

            for ds, weight in zip(datasets, weights):
                band = ds.GetRasterBand(1)
                arr = band.ReadAsArray(x, y, cols, rows).astype("float64")
                src_nodata = band.GetNoDataValue()
                valid = np.isfinite(arr)
                if src_nodata is not None:
                    valid &= arr != src_nodata
                valid &= arr != nodata
                numerator[valid] += arr[valid] * float(weight)
                denominator[valid] += float(weight)

            result = np.full((rows, cols), nodata, dtype="float32")
            valid_den = denominator > 0
            result[valid_den] = (numerator[valid_den] / denominator[valid_den]).astype("float32")
            out_band.WriteArray(result, x, y)

    out_band.FlushCache()
    out.FlushCache()
    for ds in datasets:
        ds = None
    out = None
    return output_path


def build_stack(raster_paths, output_path):
    if not raster_paths:
        return None
    vrt_path = output_path + ".vrt"
    vrt = gdal.BuildVRT(vrt_path, raster_paths, separate=True)
    if vrt is None:
        raise SoilGridsError("No se pudo construir VRT del stack.")
    vrt.FlushCache()
    vrt = None

    out = gdal.Translate(
        output_path,
        vrt_path,
        format="GTiff",
        creationOptions=["COMPRESS=LZW", "TILED=YES", "BIGTIFF=IF_SAFER"],
    )
    if out is None:
        raise SoilGridsError("No se pudo crear el stack {0}".format(output_path))
    out.FlushCache()
    out = None
    return output_path


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
