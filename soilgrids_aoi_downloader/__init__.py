"""Punto de entrada del complemento SoilGrids AOI Downloader."""


def classFactory(iface):
    """Devuelve la instancia del complemento para QGIS."""
    from .plugin import SoilGridsAoiDownloaderPlugin

    return SoilGridsAoiDownloaderPlugin(iface)

