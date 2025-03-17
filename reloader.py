# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Reloader
                                 A QGIS plugin
 Reload selected layer(s)
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2023-02-09
        git sha              : $Format:%H$
        copyright            : (C) 2023 by Maarten Pronk
        email                : git@evetion.nl
        version              : 0.3
 ***************************************************************************/

/***************************************************************************
 Updated 2025-03-16:

 o Show status icons in layers tree for each watched layer.

 Updated 2025-02-13:

 o Watching multiple files/layers is now working properly
   https://github.com/evetion/Reloader/issues/2

 o Support added for file names that are URL-encoded (including those with
   options appended)
   https://github.com/evetion/Reloader/issues/2

 o Files changed with non-in-place updates (write to temporary file + move)
   are now persistently watched
   https://github.com/evetion/Reloader/issues/4

 Updated 2025-02-19:

 o Support added for all file path encoding used by QGIS on all platforms
   https://github.com/evetion/Reloader/issues/7
   https://github.com/evetion/Reloader/issues/8

 o Added warn_and_log(...) method to both notify user and log a message

 o All valid selected layers will be watched even if selection includes
   unwatchable ones

 © 2025 Alexander Hajnal

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os.path
from os.path import isfile

from qgis.core import Qgis
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QFileSystemWatcher,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox

# Initialize Qt resources from file resources.py
from .resources import *

# Import the code for the dialog
# from .reloader_diaslog import ReloaderDialog

# Used for extracting and decoding layers' data file names
from qgis.core import QgsProviderRegistry

# Used for callback
from qgis.core import QgsProject

# Used for logging
from qgis.core import QgsMessageLog

# Used for accessing layers from layer tree items
from qgis.core import QgsLayerTree

# Used for layer status icons
from qgis.gui import QgsLayerTreeViewIndicator

class Reloader:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr("&Reloader")

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None
        self.watchers = {}

        # Layer status indicator (common for all watched layers)
        self.indicator = None


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate("Reloader", message)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None,
    ):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ":/plugins/reloader/layer-reload.png"
        self.add_action(
            icon_path,
            text=self.tr("Reload selected layer(s)"),
            callback=self.reload,
            parent=self.iface.mainWindow(),
        )

        icon_path = ":/plugins/reloader/layer-reopen.png"
        self.add_action(
            icon_path,
            text=self.tr("Reopen selected layer(s)"),
            callback=self.reopen,
            parent=self.iface.mainWindow(),
        )

        icon_path = ":/plugins/reloader/layer-watch.png"
        self.add_action(
            icon_path,
            text=self.tr("Start watching layer(s) for changes"),
            callback=self.watch,
            parent=self.iface.mainWindow(),
        )

        icon_path = ":/plugins/reloader/layer-unwatch.png"
        self.add_action(
            icon_path,
            text=self.tr("Stop watching layer(s) for changes"),
            callback=self.unwatch,
            parent=self.iface.mainWindow(),
        )

        # Create status indicator for watched layers
        # All such layers share a single indicator object
        self.indicator = QgsLayerTreeViewIndicator()
        cur_path = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(cur_path, "layer-watched-large.png")
        icon = QIcon(icon_path)
        self.indicator.setIcon(icon)

    # Both notify the user and log a message
    def warn_and_log(self, message):
        self.iface.messageBar().pushMessage(
            "Warning",
            message,
            level=Qgis.Warning,
            duration=5,
        )
        QgsMessageLog.logMessage(
            message,
            tag="Reloader",
            level=Qgis.Warning,
            notifyUser=False,
        )

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(self.tr("&Reloader"), action)
            self.iface.removeToolBarIcon(action)

    def reload(self):
        """Reload selected layer(s)."""
        layers = self.iface.layerTreeView().selectedLayers()

        if len(layers) == 0:
            mw = self.iface.mainWindow()
            QMessageBox.warning(mw, "Reloader", "No selected layer(s).")
            return 1
        else:
            for layer in layers:
                layer.reload()
                layer.triggerRepaint()

    def reopen(self):
        """Reopen selected layer(s), which also updates the extent in contrast to `reload`."""
        layers = self.iface.layerTreeView().selectedLayers()

        if len(layers) == 0:
            mw = self.iface.mainWindow()
            QMessageBox.warning(mw, "Reloader", "No selected layer(s).")
            return 1
        else:
            for layer in layers:
                layer.setDataSource(layer.source(), layer.name(), layer.providerType())
                layer.triggerRepaint()

    def watch(self):
        """Start watching selected layer(s) for changes."""
        layers = self.iface.layerTreeView().selectedLayers()
        print(self.watchers)
        if len(layers) == 0:
            mw = self.iface.mainWindow()
            QMessageBox.warning(mw, "Reloader", "No selected layer(s).")
            return 1
        else:
            for layer in layers:
                layer.reload()

                QgsMessageLog.logMessage(
                    f'Attempting to add watch for "{layer.name()}"',
                    tag="Reloader",
                    level=Qgis.Info,
                    notifyUser=False,
                )

                # Get layer's provider type (the provider is the I/O handler)
                provider_type = layer.providerType()

                # Get layer's provider (the provider is the I/O handler)
                provider = layer.dataProvider()

                if provider is None:
                    # No provider (not sure when this could occur)

                    # Notify the user and log the error
                    self.warn_and_log( f"Can't watch {layer.name()} for updates because it has no provider." )

                    # Don't attempt to watch the layer (but keep trying to add any other selected layers)
                    continue

                # Get the URI containing the layer's data
                uri=provider.dataSourceUri()

                # Split the URI into its component parts (e.g. "path", "layerName", "url")
                components=QgsProviderRegistry.instance().decodeUri(providerKey=provider_type, uri=uri)

                # Get the data file's path
                # Not all layers will have this (e.g. ArcGIS REST layers don't; they have a "uri" component instead)
                if not 'path' in components:
                    # Layer's data source does not appear to be a local file

                    # Notify the user and log the error
                    self.warn_and_log( f"Can't watch {layer.name()} for updates because it is not a local file." )

                    # Don't attempt to watch the layer (but keep trying to add any other selected layers)
                    continue

                # A "path" value is present, get its value
                # (This is the name of the local data file containing the layer's data)
                path = components['path']

                QgsMessageLog.logMessage(
                    f'Path: {path}',
                    tag="Reloader",
                    level=Qgis.Info,
                    notifyUser=False,
                )

                # Verify that the file containing the layer's data actually exists
                if not isfile(path):
                    # Path doesn't specify an extant local file

                    # Notify the user and log the error
                    self.warn_and_log( f"Can't watch {layer.name()} for updates because it is not a local path." )

                else:
                    # The file containing the layer's data exists

                    QgsMessageLog.logMessage(
                        f"Creating callback",
                        tag="Reloader",
                        level=Qgis.Info,
                        notifyUser=False,
                    )

                    # Callback to perform the refresh of the appropriate layer
                    # This is called by watcher when a watched file changes.
                    #
                    # path:     The file being watched
                    #           This is set by the watcher to the path of the
                    #           file whose change triggered the callback,
                    #           irrespective of what value was specified when
                    #           the callback was connected to the watcher.
                    # layer_id: The ID of the layer to be reloaded
                    #
                    # Note: The "layer_id=layer.id()" syntax used in the call-
                    # back definition explicitly sets the layer_id argument's
                    # value to the current layer's ID at the time the callback
                    # is created.  If one were to omit "layer_id=layer.id()" 
                    # and instead set layer_id in the watch() function's loop 
                    # then the layer_id passed to the callback would be the 
                    # layer_id value of the final iteration of the loop.  In 
                    # other words, parameters to the callback function must be 
                    # explicitly set in the callback's definition (this does 
                    # not apply to the path parameter since its value is set by 
                    # the watcher at the time the callback is called).  For 
                    # further discussion of this see:
                    # http://jceipek.com/Olin-Coding-Tutorials/
                    def reload_callback(path, layer_id=layer.id()):

                        # Get the layer object for the relevant layer's ID
                        # Returns None if no layer with the given ID exists
                        layer = QgsProject.instance().mapLayer(layer_id)

                        if layer is None:
                            # Layer for given ID does not exist
                            
                            # Layer was being watched but the layer was deleted
                            # and subsequently the layer's watched file changed
                            
                            QgsMessageLog.logMessage(
                                "Reloading layer\n" +
                                "The layer for the watched file was deleted, removing its watcher\n" +
                                f"Layer ID: {layer_id}\n" +
                                f"Path:     {path}",
                                tag="Reloader",
                                level=Qgis.Info,
                                notifyUser=False,
                            )
                            
                            # Get the watcher for this [removed] layer
                            watcher = self.watchers.pop(layer_id, None)
                            # Sanity check
                            if watcher is None:
                                # Shouldn't happen
                                QgsMessageLog.logMessage(
                                    "Can't stop watching the removed layer because we never started watching it!",
                                    tag="Reloader",
                                    level=Qgis.Warning,
                                    notifyUser=False,
                                )
                            else:
                                # Delete the removed layer's watcher
                                del watcher
                            # No further actions
                            return;

                        # Layer still exists

                        QgsMessageLog.logMessage(
                            "Reloading layer\n"
                            + f"ID:    {layer.id()}\n"
                            + f"Name:  {layer.name()}\n"
                            + f"Path:  {path}",
                            tag="Reloader",
                            level=Qgis.Info,
                            notifyUser=False,
                        )

                        # Update the layer
                        layer.reload()
                        layer.triggerRepaint()

                        # Re-add the watch if change was not in-place
                        # See https://doc.qt.io/qt-6/qfilesystemwatcher.html#fileChanged
                        if path not in self.watchers[layer.id()].files():
                            if isfile(path):
                                QgsMessageLog.logMessage(
                                    "Non-in-place file update, reinstalling watch",
                                    tag="Reloader",
                                    level=Qgis.Info,
                                    notifyUser=False,
                                )
                                self.watchers[layer.id()].addPath(path)

                    # Install watcher for this path
                    # Callback's arguments are set via its definition, above
                    watcher = QFileSystemWatcher()
                    watcher.addPath(path)
                    watcher.fileChanged.connect(reload_callback)
                    self.watchers[layer.id()] = watcher

                    # Note that layer is being watched
                    layer.setCustomProperty("reloader/watchLayer", True)

                    self.updateStatusIcons()


    def unwatch(self):
        """Stop watching selected layer(s) for changes."""
        layers = self.iface.layerTreeView().selectedLayers()

        if len(layers) == 0:
            mw = self.iface.mainWindow()
            QMessageBox.warning(mw, "Reloader", "No selected layer(s).")
            return 1
        else:
            # Iterate through selected layers
            for layer in layers:
                # Get watcher for the current layer (or None if none is present)
                watcher = self.watchers.pop(layer.id(), None)
                if watcher is None:
                    # No watcher for layer

                    # Notify the user and log the error
                    self.warn_and_log( f"Can't stop watching {layer.name()} because we never started watching it." )

                else:
                    # Layer has a watcher

                    QgsMessageLog.logMessage(
                        f"No longer watching {layer.name()}\n" +
                        f"Path: {watcher.files()[0]}",
                        tag="Reloader",
                        level=Qgis.Info,
                        notifyUser=False,
                    )

                    # Remove the layer's watcher
                    del watcher

                    # Note that layer is no longer being watched
                    layer.removeCustomProperty("reloader/watchLayer")

                    self.updateStatusIcons()

    def updateStatusIcons(self):
        def update_node_status_icons(node):
            if QgsLayerTree.isLayer(node):
                layer = node.layer()
                if hasattr(node, "customProperty"):
                    watchActive = layer.customProperty("reloader/watchLayer")
                    if watchActive == True:
                        self.iface.layerTreeView().addIndicator(node, self.indicator)
                    else:
                        self.iface.layerTreeView().removeIndicator(node, self.indicator)

            for child in node.children():
                update_node_status_icons(child)

        root = self.iface.layerTreeView().layerTreeModel().rootGroup()
        update_node_status_icons(root)
