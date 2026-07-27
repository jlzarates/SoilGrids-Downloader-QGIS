"""Integracion del complemento SoilGrids con QGIS."""

from __future__ import absolute_import

import os

from qgis.PyQt.QtCore import QStandardPaths, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMapLayer,
    QgsMessageLog,
    QgsProject,
    QgsRasterLayer,
    QgsVectorLayer,
    QgsVectorFileWriter,
)
from qgis.PyQt.QtCore import QVariant

from .dialog import SoilGridsDockWidget
from .tasks import LOG_CATEGORY, SoilGridsDownloadTask


class SoilGridsAoiDownloaderPlugin(object):
    """Controlador del panel y de las tareas SoilGrids."""

    MENU_NAME = "&SoilGrids AOI Downloader"

    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dock = None
        self.current_task = None
        self._unloaded = False

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.svg")
        self.action = QAction(QIcon(icon_path), "SoilGrids AOI Downloader", self.iface.mainWindow())
        self.action.setObjectName("SoilGridsAoiDownloaderAction")
        self.action.setToolTip("Descargar SoilGrids por poligono AOI")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToWebMenu(self.MENU_NAME, self.action)

    def unload(self):
        self._unloaded = True
        if self.current_task is not None:
            self.current_task.cancel()
        if self.action is not None:
            self.iface.removePluginWebMenu(self.MENU_NAME, self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.deleteLater()
            self.action = None
        if self.dock is not None:
            self.dock.deleteLater()
            self.dock = None

    def run(self):
        if self.dock is None:
            self._create_dock()
        self.refresh_polygon_layers()
        self.dock.show()
        self.dock.activateWindow()
        self.dock.raise_()

    def _create_dock(self):
        self.dock = SoilGridsDockWidget(self.iface.mainWindow())
        self.dock.refresh_layers_button.clicked.connect(self.refresh_polygon_layers)
        self.dock.download_button.clicked.connect(self.start_download)
        self.dock.cancel_button.clicked.connect(self.cancel_current_task)

        documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        if not documents:
            documents = os.path.expanduser("~")
        self.dock.set_default_output(os.path.join(documents, "SOILGRIDS_QGIS"))

    def _message(self, message, level=Qgis.Info, duration=8):
        QgsMessageLog.logMessage(str(message), LOG_CATEGORY, level)
        if not self._unloaded:
            self.iface.messageBar().pushMessage(
                "SoilGrids AOI Downloader", str(message), level=level, duration=duration
            )

    def _set_progress(self, value):
        if self.dock is not None and not self._unloaded:
            self.dock.progress_bar.setValue(max(0, min(100, int(round(value)))))

    def refresh_polygon_layers(self):
        if self.dock is None:
            return
        layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == 2:
                layers.append(layer)
        layers.sort(key=lambda lyr: lyr.name().lower())
        self.dock.set_layers(layers)

    @staticmethod
    def _validate_output_directory(path):
        if not path:
            raise ValueError("Seleccione una carpeta de salida.")
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".soilgrids_write_test_{0}.tmp".format(os.getpid()))
        try:
            with open(probe, "wb") as handle:
                handle.write(b"ok")
        finally:
            try:
                os.remove(probe)
            except OSError:
                pass

    @staticmethod
    def _write_aoi_copy(layer, output_path, epsg, buffer_m=0.0, layer_name="aoi"):
        if layer is None or not layer.isValid():
            raise ValueError("Seleccione una capa de poligono valida.")
        if layer.geometryType() != 2:
            raise ValueError("La capa AOI debe ser de poligonos.")

        target_crs = QgsCoordinateReferenceSystem("EPSG:{0}".format(int(epsg)))
        transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
        memory = QgsVectorLayer(
            "MultiPolygon?crs=EPSG:{0}".format(int(epsg)),
            layer_name,
            "memory",
        )
        provider = memory.dataProvider()
        provider.addAttributes([QgsField("id", QVariant.Int)])
        memory.updateFields()

        features = []
        fid = 1
        for source_feature in layer.getFeatures():
            geom = QgsGeometry(source_feature.geometry())
            if geom.isEmpty():
                continue
            geom.transform(transform)
            try:
                if not geom.isGeosValid():
                    geom = geom.makeValid()
            except AttributeError:
                pass
            if buffer_m and buffer_m > 0:
                geom = geom.buffer(float(buffer_m), 12)
            if geom.isEmpty():
                continue
            feature = QgsFeature(memory.fields())
            feature.setGeometry(geom)
            feature.setAttributes([fid])
            features.append(feature)
            fid += 1

        if not features:
            raise ValueError("El AOI no contiene geometria poligonal valida.")
        provider.addFeatures(features)
        memory.updateExtents()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = layer_name
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile

        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            memory,
            output_path,
            QgsProject.instance().transformContext(),
            options,
        )
        error = result[0]
        message = result[1] if len(result) > 1 else ""
        if error != QgsVectorFileWriter.NoError:
            raise ValueError("No se pudo exportar el AOI: {0}".format(message))
        return output_path

    def _resolve_aoi_paths(self, options):
        aoi_dir = os.path.join(options["output_dir"], "_aoi_temp")
        os.makedirs(aoi_dir, exist_ok=True)
        exact_path = os.path.join(aoi_dir, "aoi_soilgrids_exacto.gpkg")
        buffer_path = os.path.join(aoi_dir, "aoi_soilgrids_buffer.gpkg")

        file_path = options.get("aoi_file", "")
        if file_path:
            if not os.path.isfile(file_path):
                raise ValueError("El archivo AOI no existe: {0}".format(file_path))
            layer = QgsVectorLayer(file_path, "aoi_archivo", "ogr")
        else:
            layer_id = options.get("layer_id")
            if not layer_id:
                raise ValueError("Seleccione una capa AOI o indique un archivo vectorial.")
            layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None or not layer.isValid():
            raise ValueError("No se pudo leer el AOI.")

        self._write_aoi_copy(layer, exact_path, options["epsg"], buffer_m=0, layer_name="aoi_exacto")
        buffer_m = float(options.get("buffer_m") or 0)
        if buffer_m > 0:
            self._write_aoi_copy(layer, buffer_path, options["epsg"], buffer_m=buffer_m, layer_name="aoi_buffer")
        else:
            buffer_path = exact_path
        return exact_path, buffer_path

    def start_download(self):
        if self.current_task is not None:
            return
        try:
            options = self.dock.options()
            if not options["variables"]:
                raise ValueError("Seleccione al menos una variable SoilGrids.")
            if options["depth_from"] >= options["depth_to"]:
                raise ValueError("La profundidad inicial debe ser menor que la final.")
            if not options["download_layers"] and not options["aggregate"]:
                raise ValueError("Active capas por profundidad o agregado ponderado.")
            output_dir = os.path.abspath(os.path.expandvars(options["output_dir"]))
            self._validate_output_directory(output_dir)
            options["output_dir"] = output_dir
            options["aoi_path"], options["aoi_buffer_path"] = self._resolve_aoi_paths(options)
        except (ValueError, OSError) as exc:
            self.dock.warn("Revise la configuracion", str(exc))
            return

        task = SoilGridsDownloadTask(options)
        self.current_task = task
        self.dock.set_busy(True)
        self.dock.set_status("Descargando SoilGrids en segundo plano...")
        task.progressChanged.connect(self._set_progress)
        task.taskCompleted.connect(lambda task=task: self._download_completed(task))
        task.taskTerminated.connect(lambda task=task: self._download_terminated(task))
        QgsApplication.taskManager().addTask(task)

    def cancel_current_task(self):
        if self.current_task is not None:
            self.current_task.cancel()
            if self.dock is not None:
                self.dock.cancel_button.setEnabled(False)
                self.dock.set_status("Cancelando...")

    def _load_result_layers(self, task):
        if not self.dock.load_results_check.isChecked():
            return 0
        loaded = 0
        paths = list(task.aggregate_paths)
        if task.stack_path:
            paths.append(task.stack_path)
        if not paths:
            paths = list(task.output_paths)
        for path in paths:
            if not os.path.isfile(path):
                continue
            layer = QgsRasterLayer(path, os.path.splitext(os.path.basename(path))[0])
            if layer.isValid():
                QgsProject.instance().addMapLayer(layer)
                loaded += 1
        return loaded

    def _download_completed(self, task):
        if self.current_task is task:
            self.current_task = None
        if self._unloaded or self.dock is None:
            return
        self.dock.set_busy(False)
        loaded = self._load_result_layers(task)
        message = "Descarga terminada. Carpeta: {0}. Capas cargadas: {1}.".format(
            task.job_directory, loaded
        )
        if task.warning_message:
            message += " " + task.warning_message
            self._message(task.warning_message, Qgis.Warning, 12)
        else:
            self._message("Descarga SoilGrids terminada", Qgis.Success)
        self.dock.set_status(message)
        self.dock.info("Descarga terminada", message)

    def _download_terminated(self, task):
        if self.current_task is task:
            self.current_task = None
        if self._unloaded or self.dock is None:
            return
        self.dock.set_busy(False)
        if task.cancelled_by_user:
            self.dock.set_status("Descarga cancelada.")
            self._message("Descarga cancelada", Qgis.Warning)
            return
        message = task.error_message or "La descarga termino con un error"
        self.dock.set_status(message)
        self.dock.warn("Error SoilGrids", message)
