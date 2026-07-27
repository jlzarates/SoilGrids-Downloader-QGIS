"""Ventana del complemento SoilGrids AOI Downloader."""

from __future__ import absolute_import

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .core.soilgrids import PROPERTIES


class SoilGridsDockWidget(QDialog):
    """Ventana principal del complemento."""

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle("SoilGrids AOI Downloader")
        self.setObjectName("SoilGridsAoiDownloaderDialog")
        self.setMinimumWidth(540)
        self.resize(720, 760)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout()

        aoi_group = QGroupBox("1. Delimitacion")
        aoi_layout = QVBoxLayout(aoi_group)
        form = QFormLayout()
        self.layer_combo = QComboBox()
        self.refresh_layers_button = QPushButton("Actualizar capas")
        layer_row = QHBoxLayout()
        layer_row.addWidget(self.layer_combo, 1)
        layer_row.addWidget(self.refresh_layers_button)
        form.addRow("Capa de poligono:", layer_row)

        file_row = QHBoxLayout()
        self.aoi_file_edit = QLineEdit()
        self.aoi_file_edit.setPlaceholderText("Opcional: ruta SHP/GPKG/GeoJSON")
        self.browse_aoi_button = QPushButton("Examinar...")
        file_row.addWidget(self.aoi_file_edit, 1)
        file_row.addWidget(self.browse_aoi_button)
        form.addRow("Archivo AOI:", file_row)
        aoi_layout.addLayout(form)
        aoi_layout.addWidget(QLabel("Si se indica archivo AOI, tiene prioridad sobre la capa del proyecto."))
        root.addWidget(aoi_group)

        variables_group = QGroupBox("2. Variables SoilGrids")
        variables_layout = QVBoxLayout(variables_group)
        self.variable_list = QListWidget()
        self.variable_list.setSelectionMode(QAbstractItemView.NoSelection)
        for code, label in PROPERTIES.items():
            item = QListWidgetItem("{0} - {1}".format(code, label))
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if code in ("clay", "sand", "silt", "phh2o", "soc", "bdod") else Qt.Unchecked)
            self.variable_list.addItem(item)
        variables_layout.addWidget(self.variable_list)
        var_buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Todas")
        self.clear_vars_button = QPushButton("Limpiar")
        var_buttons.addWidget(self.select_all_button)
        var_buttons.addWidget(self.clear_vars_button)
        var_buttons.addStretch(1)
        variables_layout.addLayout(var_buttons)
        root.addWidget(variables_group, 1)

        depth_group = QGroupBox("3. Profundidad y salida")
        depth_layout = QFormLayout(depth_group)
        self.depth_from_spin = QSpinBox()
        self.depth_from_spin.setRange(0, 59)
        self.depth_from_spin.setSuffix(" cm")
        self.depth_from_spin.setValue(0)
        self.depth_to_spin = QSpinBox()
        self.depth_to_spin.setRange(1, 60)
        self.depth_to_spin.setSuffix(" cm")
        self.depth_to_spin.setValue(30)
        self.epsg_spin = QSpinBox()
        self.epsg_spin.setRange(1000, 999999)
        self.epsg_spin.setValue(25830)
        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(0, 10000)
        self.buffer_spin.setValue(750)
        self.buffer_spin.setSuffix(" m")
        self.resolution_spin = QSpinBox()
        self.resolution_spin.setRange(0, 10000)
        self.resolution_spin.setValue(0)
        self.resolution_spin.setSuffix(" m")
        self.stat_combo = QComboBox()
        self.stat_combo.addItem("mean")
        self.stat_combo.setEnabled(False)
        depth_layout.addRow("Desde:", self.depth_from_spin)
        depth_layout.addRow("Hasta:", self.depth_to_spin)
        depth_layout.addRow("Estadistico:", self.stat_combo)
        depth_layout.addRow("EPSG destino:", self.epsg_spin)
        depth_layout.addRow("Buffer anti-borde:", self.buffer_spin)
        depth_layout.addRow("Resolucion 0=nativa:", self.resolution_spin)
        root.addWidget(depth_group)

        output_group = QGroupBox("4. Opciones")
        output_layout = QVBoxLayout(output_group)
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.browse_output_button = QPushButton("Examinar...")
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.browse_output_button)
        output_layout.addLayout(output_row)
        self.download_layers_check = QCheckBox("Guardar capas por profundidad usadas")
        self.aggregate_check = QCheckBox("Generar raster ponderado del intervalo")
        self.stack_check = QCheckBox("Crear stack final")
        self.load_results_check = QCheckBox("Cargar resultados en QGIS")
        self.download_layers_check.setChecked(True)
        self.aggregate_check.setChecked(True)
        self.stack_check.setChecked(True)
        self.load_results_check.setChecked(True)
        output_layout.addWidget(self.download_layers_check)
        output_layout.addWidget(self.aggregate_check)
        output_layout.addWidget(self.stack_check)
        output_layout.addWidget(self.load_results_check)
        root.addWidget(output_group)

        action_row = QHBoxLayout()
        self.download_button = QPushButton("Descargar SoilGrids")
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        action_row.addWidget(self.download_button)
        action_row.addWidget(self.cancel_button)
        root.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        root.addWidget(self.progress_bar)
        self.status_label = QLabel("Preparado")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        root.addStretch(1)
        self.setLayout(root)

        self.browse_aoi_button.clicked.connect(self._browse_aoi)
        self.browse_output_button.clicked.connect(self._browse_output)
        self.select_all_button.clicked.connect(lambda: self._set_all_variables(Qt.Checked))
        self.clear_vars_button.clicked.connect(lambda: self._set_all_variables(Qt.Unchecked))

    def _browse_aoi(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar AOI",
            self.aoi_file_edit.text().strip() or os.path.expanduser("~"),
            "Vectores (*.shp *.gpkg *.geojson *.json);;Todos los archivos (*.*)",
        )
        if path:
            self.aoi_file_edit.setText(path)

    def _browse_output(self):
        directory = QFileDialog.getExistingDirectory(
            self, "Carpeta de salida", self.output_edit.text().strip()
        )
        if directory:
            self.output_edit.setText(directory)

    def _set_all_variables(self, state):
        for row in range(self.variable_list.count()):
            self.variable_list.item(row).setCheckState(state)

    def set_default_output(self, directory):
        if not self.output_edit.text().strip():
            self.output_edit.setText(directory)

    def set_layers(self, layers):
        current = self.layer_combo.currentData()
        self.layer_combo.clear()
        self.layer_combo.addItem("Seleccione capa del proyecto", None)
        for layer in layers:
            self.layer_combo.addItem(layer.name(), layer.id())
        if current:
            index = self.layer_combo.findData(current)
            if index >= 0:
                self.layer_combo.setCurrentIndex(index)

    def selected_variables(self):
        values = []
        for row in range(self.variable_list.count()):
            item = self.variable_list.item(row)
            if item.checkState() == Qt.Checked:
                values.append(item.data(Qt.UserRole))
        return values

    def options(self):
        return {
            "aoi_file": self.aoi_file_edit.text().strip(),
            "layer_id": self.layer_combo.currentData(),
            "variables": self.selected_variables(),
            "depth_from": self.depth_from_spin.value(),
            "depth_to": self.depth_to_spin.value(),
            "statistic": self.stat_combo.currentText(),
            "epsg": self.epsg_spin.value(),
            "buffer_m": self.buffer_spin.value(),
            "resolution": self.resolution_spin.value() or None,
            "output_dir": self.output_edit.text().strip(),
            "download_layers": self.download_layers_check.isChecked(),
            "aggregate": self.aggregate_check.isChecked(),
            "stack": self.stack_check.isChecked(),
            "load_results": self.load_results_check.isChecked(),
        }

    def set_busy(self, busy):
        self.download_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.refresh_layers_button.setEnabled(not busy)

    def set_status(self, message):
        self.status_label.setText(str(message))

    def warn(self, title, message):
        QMessageBox.warning(self, title, message)

    def info(self, title, message):
        QMessageBox.information(self, title, message)
