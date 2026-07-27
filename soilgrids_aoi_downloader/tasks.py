"""Tareas QGIS para descarga SoilGrids en segundo plano."""

from __future__ import absolute_import

import os
from datetime import datetime

from qgis.core import Qgis, QgsMessageLog, QgsTask

from .core.soilgrids import (
    CONTINUOUS_PROPERTIES,
    NODATA,
    SoilGridsError,
    aggregate_filename,
    build_stack,
    depth_overlaps,
    layer_filename,
    mask_raster_to_aoi,
    unique_job_directory,
    vrt_url,
    warp_soilgrids_layer,
    weighted_average_rasters,
    write_json,
)


LOG_CATEGORY = "SoilGrids AOI Downloader"


class SoilGridsDownloadTask(QgsTask):
    """Descarga capas SoilGrids, las recorta/reproyecta y agrega por profundidad."""

    def __init__(self, options):
        QgsTask.__init__(self, "Descargar SoilGrids por AOI", QgsTask.CanCancel)
        self.options = dict(options)
        self.error_message = ""
        self.warning_message = ""
        self.cancelled_by_user = False
        self.job_directory = ""
        self.output_paths = []
        self.aggregate_paths = []
        self.stack_path = ""
        self.metadata_path = ""

    def _log(self, message, level=Qgis.Info):
        QgsMessageLog.logMessage(str(message), LOG_CATEGORY, level)

    def cancel(self):
        self.cancelled_by_user = True
        QgsTask.cancel(self)

    def _check_cancelled(self):
        if self.isCanceled():
            self.cancelled_by_user = True
            raise SoilGridsError("Descarga cancelada por el usuario")

    def _step_progress(self, current, total):
        if total <= 0:
            self.setProgress(0)
        else:
            self.setProgress(max(0, min(100, (float(current) / float(total)) * 100.0)))

    def _layer_output(self, variable, depth_label, statistic):
        return os.path.join(
            self.job_directory,
            "01_CAPAS_PROFUNDIDAD",
            layer_filename(variable, depth_label, statistic, self.options["epsg"]),
        )

    def run(self):
        try:
            output_dir = self.options["output_dir"]
            os.makedirs(output_dir, exist_ok=True)
            self.job_directory = unique_job_directory(output_dir)
            layers_dir = os.path.join(self.job_directory, "01_CAPAS_PROFUNDIDAD")
            aggregates_dir = os.path.join(self.job_directory, "02_AGREGADOS_PROFUNDIDAD")
            stack_dir = os.path.join(self.job_directory, "03_STACK")
            meta_dir = os.path.join(self.job_directory, "00_METADATA")
            for directory in (layers_dir, aggregates_dir, stack_dir, meta_dir):
                os.makedirs(directory, exist_ok=True)

            variables = list(self.options["variables"])
            statistic = self.options.get("statistic", "mean")
            depth_from = int(self.options["depth_from"])
            depth_to = int(self.options["depth_to"])
            overlaps = depth_overlaps(depth_from, depth_to)
            aoi_path = self.options["aoi_path"]
            aoi_buffer_path = self.options.get("aoi_buffer_path") or aoi_path
            epsg = int(self.options["epsg"])
            resolution = self.options.get("resolution")

            plan = []
            for variable in variables:
                if variable == "ocs":
                    if depth_from == 0 and depth_to == 30:
                        plan.append((variable, "0-30cm", 30))
                    else:
                        self.warning_message += (
                            "OCS solo esta disponible como stock 0-30 cm; se omitio para {0}-{1} cm. "
                        ).format(depth_from, depth_to)
                    continue
                for item in overlaps:
                    plan.append((variable, item["label"], item["weight_cm"]))

            if not plan:
                raise SoilGridsError("No hay capas SoilGrids que descargar para la seleccion.")

            downloaded = {}
            total_units = len(plan) + max(1, len([v for v in variables if v in CONTINUOUS_PROPERTIES]))
            done = 0

            for variable, depth_label, weight in plan:
                self._check_cancelled()
                out_path = self._layer_output(variable, depth_label, statistic)
                temp_path = out_path + ".buffer.tif"
                source_url = vrt_url(variable, depth_label, statistic)
                self._log("Descargando {0} {1}".format(variable, depth_label))
                warp_soilgrids_layer(
                    source_url=source_url,
                    output_path=temp_path,
                    aoi_path=aoi_buffer_path,
                    epsg_destino=epsg,
                    resolution_m=resolution,
                    overwrite=True,
                )
                mask_raster_to_aoi(temp_path, out_path, aoi_path)
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                downloaded[(variable, depth_label)] = out_path
                self.output_paths.append(out_path)
                done += 1
                self._step_progress(done, total_units)

            if self.options.get("aggregate", True):
                for variable in variables:
                    self._check_cancelled()
                    if variable not in CONTINUOUS_PROPERTIES:
                        continue
                    raster_paths = []
                    weights = []
                    missing = []
                    for item in overlaps:
                        path = downloaded.get((variable, item["label"]))
                        if path and os.path.isfile(path):
                            raster_paths.append(path)
                            weights.append(item["weight_cm"])
                        else:
                            missing.append(item["label"])
                    if missing:
                        self.warning_message += "No se agrego {0}; faltan {1}. ".format(
                            variable, ", ".join(missing)
                        )
                        continue
                    agg_path = os.path.join(
                        aggregates_dir,
                        aggregate_filename(variable, depth_from, depth_to, statistic, epsg),
                    )
                    self._log("Agregando {0} {1}-{2} cm".format(variable, depth_from, depth_to))
                    weighted_average_rasters(raster_paths, weights, agg_path, nodata=NODATA)
                    self.aggregate_paths.append(agg_path)
                    done += 1
                    self._step_progress(done, total_units)

            stack_inputs = []
            if self.options.get("download_layers", True):
                stack_inputs.extend(self.output_paths)
            if self.aggregate_paths:
                stack_inputs.extend(self.aggregate_paths)

            if self.options.get("stack", True) and stack_inputs:
                self._check_cancelled()
                self.stack_path = os.path.join(
                    stack_dir, "STACK_SOILGRIDS_AOI_EPSG{0}.tif".format(epsg)
                )
                build_stack(stack_inputs, self.stack_path)

            self.metadata_path = os.path.join(meta_dir, "resumen_soilgrids.json")
            write_json(
                self.metadata_path,
                {
                    "creado": datetime.now().isoformat(timespec="seconds"),
                    "aoi": aoi_path,
                    "epsg": epsg,
                    "resolution_m": resolution,
                    "depth_from_cm": depth_from,
                    "depth_to_cm": depth_to,
                    "overlaps": overlaps,
                    "variables": variables,
                    "statistic": statistic,
                    "capas": self.output_paths,
                    "agregados": self.aggregate_paths,
                    "stack": self.stack_path,
                    "warning": self.warning_message,
                },
            )
            self.setProgress(100)
            return True
        except Exception as exc:
            self.error_message = str(exc)
            self._log("Error SoilGrids: {0}".format(exc), Qgis.Critical)
            return False
