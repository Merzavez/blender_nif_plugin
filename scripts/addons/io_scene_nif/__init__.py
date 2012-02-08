"""Nif import and export scripts."""

# ***** BEGIN LICENSE BLOCK *****
# 
# Copyright © 2005-2011, NIF File Format Library and Tools contributors.
# All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
# 
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
# 
#    * Neither the name of the NIF File Format Library and Tools
#      project nor the names of its contributors may be used to endorse
#      or promote products derived from this software without specific
#      prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# ***** END LICENSE BLOCK *****

#: Blender addon info.
bl_info = {
    "name": "NetImmerse/Gamebryo nif format",
    "description":
    "Import and export files in the NetImmerse/Gamebryo nif format (.nif)",
    "author": "Amorilia",
    "version": (2, 6, 0),
    "blender:": (2, 5, 9),
    "api": 39257,
    "location": "File > Import-Export",
    "warning": "not functional, port from 2.49 series still in progress",
    "wiki_url": (
        "http://wiki.blender.org/index.php/Extensions:2.5/Py/Scripts/"\
        "Import-Export/Nif"),
    "tracker_url": (
        "http://sourceforge.net/tracker/?group_id=149157&atid=776343"),
    "support": "COMMUNITY",
    "category": "Import-Export"}

import logging
import sys
import os
import os.path

import bpy
import bpy.props
from bpy_extras.io_utils import ImportHelper, ExportHelper

# blender doesn't look in site-packages; easiest solution for this
# seems to be toimport site.py manually, so we find pyffi if it is
# installed there
import site

import pyffi
from pyffi.formats.nif import NifFormat
from pyffi.formats.egm import EgmFormat

def _init_loggers():
    """Set up loggers."""
    niftoolslogger = logging.getLogger("niftools")
    niftoolslogger.setLevel(logging.WARNING)
    pyffilogger = logging.getLogger("pyffi")
    pyffilogger.setLevel(logging.WARNING)
    loghandler = logging.StreamHandler()
    loghandler.setLevel(logging.DEBUG)
    logformatter = logging.Formatter("%(name)s:%(levelname)s:%(message)s")
    loghandler.setFormatter(logformatter)
    niftoolslogger.addHandler(loghandler)
    pyffilogger.addHandler(loghandler)

# set up the loggers: call it as a function to avoid polluting namespace
_init_loggers()

class NifImportExportUI:
    """Abstract base class for import and export user interface."""

    # filepath is created by ImportHelper/ExportHelper

    #: Default file name extension.
    filename_ext = ".nif"

    #: File name filter for file select dialog.
    filter_glob = bpy.props.StringProperty(
        default="*.nif;*.item;*.nifcache;*.jmi", options={'HIDDEN'})

    #: Level of verbosity on the console.
    log_level = bpy.props.EnumProperty(
        items=(
            ("DEBUG", "Debug",
             "Show all messages (only useful for debugging)."),
            ("INFO", "Info",
             "Show some informative messages, warnings, and errors."),
            ("WARNING", "Warning",
             "Only show warnings and errors."),
            ("ERROR", "Error",
             "Only show errors."),
            ("CRITICAL", "Critical",
             "Only show extremely critical errors."),
            ),
        name="Log Level",
        description="Level of verbosity on the console.",
        default="WARNING")

    #: Name of file where Python profiler dumps the profile.
    profile_path = bpy.props.StringProperty(
        name="Profile Path",
        description=
        "Name of file where Python profiler dumps the profile."
        " Set to empty string to turn off profiling.",
        maxlen=1024,
        default="",
        subtype="FILE_PATH",
        options={'HIDDEN'})

    #: Number of nif units per blender unit.
    scale_correction = bpy.props.FloatProperty(
        name="Scale Correction",
        description="Number of nif units per blender unit.",
        default=10.0,
        min=0.01, max=100.0, precision=2)

    #: Used for checking equality between floats.
    epsilon = bpy.props.FloatProperty(
        name="Epsilon",
        description="Used for checking equality between floats.",
        default=0.005,
        min=0.0, max=1.0, precision=5,
        options={'HIDDEN'})

class NifImportUI(bpy.types.Operator, ImportHelper, NifImportExportUI):
    """Operator for loading a nif file."""

    #: Name of function for calling the nif export operator.
    bl_idname = "import_scene.nif"

    #: How the nif import operator is labelled in the user interface.
    bl_label = "Import NIF"

    #: Keyframe file for animations.
    keyframe_file = bpy.props.StringProperty(
        name="Keyframe File",
        description="Keyframe file for animations.",
        maxlen=1024,
        default="",
        subtype="FILE_PATH")

    #: FaceGen EGM file for morphs.
    egm_file = bpy.props.StringProperty(
        name="FaceGen EGM File",
        description="FaceGen EGM file for morphs.",
        maxlen=1024,
        default="",
        subtype="FILE_PATH")

    #: Import animation.
    animation = bpy.props.BoolProperty(
        name="Animation",
        description="Import animation.",
        default=True)

    #: Merge skeleton roots.
    merge_skeleton_roots = bpy.props.BoolProperty(
        name="Merge Skeleton Roots",
        description="Merge skeleton roots.",
        default=True)

    #: Send all geometries to their bind position.
    send_geoms_to_bind_pos = bpy.props.BoolProperty(
        name="Send Geometries To Bind Position",
        description="Send all geometries to their bind position.",
        default=True)

    #: Send all detached geometries to the position of their parent node.
    send_detached_geoms_to_node_pos = bpy.props.BoolProperty(
        name="Send Detached Geometries To Node Position",
        description=
        "Send all detached geometries to the position of their parent node.",
        default=True)

    #: Send all bones to their bind position.
    send_bones_to_bind_position = bpy.props.BoolProperty(
        name="Send Bones To Bind Position",
        description="Send all bones to their bind position.",
        default=True)

    #: Apply skin deformation to all skinned geometries.
    apply_skin_deformation =  bpy.props.BoolProperty(
        name="Apply Skin Deformation",
        description="Apply skin deformation to all skinned geometries.",
        default=False)

    #: What should be imported.
    skeleton = bpy.props.EnumProperty(
        items=(
            ("EVERYTHING", "Everything",
             "Import everything."),
            ("SKELETON_ONLY", "Skeleton Only",
             "Import skeleton only and make it parent of selected geometry."),
            ("GEOMETRY_ONLY", "Geometry Only",
             "Import geometry only and parent them to selected skeleton."),
            ),
        name="What",
        description="What should be imported.",
        default="EVERYTHING")

    #: Import multi-material shapes as a single mesh.
    combine_shapes = bpy.props.BoolProperty(
        name="Combine Shapes",
        description="Import multi-material shapes as a single mesh.",
        default=True)

    def execute(self, context):
        """Execute the import operator: first constructs a
        :class:`~io_scene_nif.import_nif.NifImport` instance and then
        calls its :meth:`~io_scene_nif.import_nif.NifImport.execute`
        method.
        """
        from . import import_nif
        return import_nif.NifImport(self, context).execute()

def _game_to_enum(game):
    symbols = ":,'\" +-*!?;./="
    table = str.maketrans(symbols, "_" * len(symbols))
    enum = game.upper().translate(table).replace("__", "_")
    return enum

class NifExportUI(bpy.types.Operator, ExportHelper, NifImportExportUI):
    """Operator for saving a nif file."""

    #: Name of function for calling the nif export operator.
    bl_idname = "export_scene.nif"

    #: How the nif export operator is labelled in the user interface.
    bl_label = "Export NIF"

    #: For which game to export.
    game = bpy.props.EnumProperty(
        items=[
            (_game_to_enum(game), game, "Export for " + game)
            # implementation note: reversed makes it show alphabetically
            # (at least with the current blender)
            for game in reversed(sorted(
                [x for x in NifFormat.games.keys() if x != '?']))
            ],
        name="Game",
        description="For which game to export.",
        default='OBLIVION')

    #: How to export animation.
    animation = bpy.props.EnumProperty(
        items=[
            ('ALL_NIF', "All (nif)", "Geometry and animation to a single nif."),
            ('ALL_NIF_XNIF_XKF', "All (nif, xnif, xkf)", "Geometry and animation to a nif, xnif, and xkf (for Morrowind)."),
            ('GEOM_NIF', "Geometry only (nif)", "Only geometry to a single nif."),
            ('ANIM_KF', "Animation only (kf)", "Only animation to a single kf."),
            ],
        name="Animation",
        description="How to export animation.",
        default='ALL_NIF')

    #: Smoothen inter-object seams.
    smooth_object_seams = bpy.props.BoolProperty(
        name="Smoothen Inter-Object Seams",
        description="Smoothen inter-object seams.",
        default=True)

    #: Use BSAnimationNode (for Morrowind).
    bs_animation_node = bpy.props.BoolProperty(
        name="Use NiBSAnimationNode",
        description="Use NiBSAnimationNode (for Morrowind).",
        default=False)

    #: Stripify geometries. Deprecate? (Strips are slower than triangle shapes.)
    stripify = bpy.props.BoolProperty(
        name="Stripify Geometries",
        description="Stripify geometries.",
        default=False,
        options={'HIDDEN'})

    #: Stitch strips. Deprecate? (Strips are slower than triangle shapes.)
    stitch_strips = bpy.props.BoolProperty(
        name="Stitch Strips",
        description="Stitch strips.",
        default=True,
        options={'HIDDEN'})

    #: Flatten skin.
    flatten_skin = bpy.props.BoolProperty(
        name="Flatten Skin",
        description="Flatten skin.",
        default=False)

    #: Export skin partition.
    skin_partition = bpy.props.BoolProperty(
        name="Skin Partition",
        description="Export skin partition.",
        default=True)

    #: Pad and sort bones.
    pad_bones = bpy.props.BoolProperty(
        name="Pad & Sort Bones",
        description="Pad and sort bones.",
        default=False)

    #: Maximum number of bones per skin partition.
    max_bones_per_partition = bpy.props.IntProperty(
        name = "Max Bones Per Partition",
        description="Maximum number of bones per skin partition.",
        default=18, min=4, max=18)

    #: Maximum number of bones per vertex in skin partitions.
    max_bones_per_vertex = bpy.props.IntProperty(
        name = "Max Bones Per Vertex",
        description="Maximum number of bones per vertex in skin partitions.",
        default=4, min=1,
        options={'HIDDEN'})

    #: Pad and sort bones.
    force_dds = bpy.props.BoolProperty(
        name="Force DDS",
        description="Force texture .dds extension.",
        default=True)

    #: Map game enum to nif version.
    version = {
        _game_to_enum(game): versions[-1]
        for game, versions in NifFormat.games.items() if game != '?'
        }

    def execute(self, context):
        """Execute the export operator: first constructs a
        :class:`~io_scene_nif.export_nif.NifExport` instance and then
        calls its :meth:`~io_scene_nif.export_nif.NifExport.execute`
        method.
        """
        from . import export_nif
        return export_nif.NifExport(self, context).execute()

# TODO: integrate with NifImportExport class
# we're removing stuff from this class as we integrate
class NifConfig:
    """Class which handles configuration of nif import and export in Blender.
    """
    # the DEFAULTS dict defines the valid config variables, default values,
    # and their type
    # IMPORTANT: don't start dictionary keys with an underscore
    # the Registry module doesn't like that, apparently
    DEFAULTS = dict(
        IMPORT_REALIGN_BONES = 1, # 0 = no, 1 = tail, 2 = tail+rotation
        IMPORT_ANIMATION = True,
        EXPORT_FLATTENSKIN = False,
        IMPORT_EGMANIM = True, # create FaceGen EGM animation curves
        IMPORT_EGMANIMSCALE = 1.0, # scale of FaceGen EGM animation curves
        EXPORT_ANIMSEQUENCENAME = '', # sequence name of the kf file
        IMPORT_EXTRANODES = True,
        EXPORT_BHKLISTSHAPE = False,
        EXPORT_OB_BSXFLAGS = 2,
        EXPORT_OB_MASS = 10.0,
        EXPORT_OB_SOLID = True,
        EXPORT_OB_MOTIONSYSTEM = 7, # MO_SYS_FIXED
        EXPORT_OB_UNKNOWNBYTE1 = 1,
        EXPORT_OB_UNKNOWNBYTE2 = 1,
        EXPORT_OB_QUALITYTYPE = 1, # MO_QUAL_FIXED
        EXPORT_OB_WIND = 0,
        EXPORT_OB_LAYER = 1, # static
        EXPORT_OB_MATERIAL = 9, # wood
        EXPORT_OB_MALLEABLECONSTRAINT = False, # use malleable constraint for ragdoll and hinge
        EXPORT_OB_PRN = "NONE", # determines bone where to attach weapon
        EXPORT_FO3_SF_ZBUF = True, # use these shader flags?
        EXPORT_FO3_SF_SMAP = False,
        EXPORT_FO3_SF_SFRU = False,
        EXPORT_FO3_SF_WINDOW_ENVMAP = False,
        EXPORT_FO3_SF_EMPT = True,
        EXPORT_FO3_SF_UN31 = True,
        EXPORT_FO3_FADENODE = False,
        EXPORT_FO3_SHADER_TYPE = 1, # shader_default
        EXPORT_FO3_BODYPARTS = True,
        EXPORT_ANIMTARGETNAME = '',
        EXPORT_ANIMPRIORITY = 0,
        EXPORT_ANIM_DO_NOT_USE_BLENDER_PROPERTIES = False,
        PROFILE = '', # name of file where Python profiler dumps the profile; set to empty string to turn off profiling
        IMPORT_EXPORTEMBEDDEDTEXTURES = False,
        EXPORT_OPTIMIZE_MATERIALS = True,
        EXPORT_OB_COLLISION_DO_NOT_USE_BLENDER_PROPERTIES = False,
        EXPORT_MW_BS_ANIMATION_NODE = False,
        )

    def __init__(self):
        """Initialize and load configuration."""
        # initialize all instance variables
        self.guiElements = {} # dictionary of gui elements (buttons, strings, sliders, ...)
        self.gui_events = []   # list of events
        self.gui_event_ids = {} # dictionary of event ids
        self.config = {}      # configuration dictionary
        self.target = None    # import or export
        self.callback = None  # function to call when config gui is done
        self.texpathIndex = 0
        self.texpathCurrent = ''

        # reset GUI coordinates
        self.xPos = self.XORIGIN
        self.yPos = self.YORIGIN + Blender.Window.GetAreaSize()[1]

        # load configuration
        self.load()

    def run(self, target, filename, callback):
        """Run the config gui."""
        self.target = target     # import or export
        self.callback = callback # function to call when config gui is done

        # save file name
        # (the key where to store the file name depends
        # on the target)
        if self.target == self.TARGET_IMPORT:
            self.config["IMPORT_FILE"] = filename
        elif self.target == self.TARGET_EXPORT:
            self.config["EXPORT_FILE"] = filename
        self.save()

        # prepare and run gui
        self.texpathIndex = 0
        self.update_texpath_current()
        Draw.Register(self.gui_draw, self.gui_event, self.gui_button_event)

    def save(self):
        """Save and validate configuration to Blender registry."""
        Registry.SetKey(self.CONFIG_NAME, self.config, True)
        self.load() # for validation

    def load(self):
        """Load the configuration stored in the Blender registry and checks
        configuration for incompatible values.
        """
        # copy defaults
        self.config = dict(**self.DEFAULTS)
        # read configuration
        savedconfig = Blender.Registry.GetKey(self.CONFIG_NAME, True)
        # port config keys from old versions to current version
        try:
            self.config["IMPORT_TEXTURE_PATH"] = savedconfig["TEXTURE_SEARCH_PATH"]
        except:
            pass
        try:
            self.config["IMPORT_FILE"] = os.path.join(
                savedconfig["NIF_IMPORT_PATH"], savedconfig["NIF_IMPORT_FILE"])
        except:
            pass
        try:
            self.config["EXPORT_FILE"] = savedconfig["NIF_EXPORT_FILE"]
        except:
            pass
        try:
            self.config["IMPORT_REALIGN_BONES"] = savedconfig["REALIGN_BONES"]
        except:
            pass
        try:
            if self.config["IMPORT_REALIGN_BONES"] == True:
                self.config["IMPORT_REALIGN_BONES"] = 1
            elif self.config["IMPORT_REALIGN_BONES"] == False:
                self.config["IMPORT_REALIGN_BONES"] = 0
        except:
            pass
        try:
            if savedconfig["IMPORT_SKELETON"] == True:
                self.config["IMPORT_SKELETON"] = 1
            elif savedconfig["IMPORT_SKELETON"] == False:
                self.config["IMPORT_SKELETON"] = 0
        except:
            pass
        # merge configuration with defaults
        if savedconfig:
            for key, val in self.DEFAULTS.items():
                try:
                    savedval = savedconfig[key]
                except KeyError:
                    pass
                else:
                    if isinstance(savedval, val.__class__):
                        self.config[key] = savedval
        # store configuration
        Blender.Registry.SetKey(self.CONFIG_NAME, self.config, True)
        # special case: set log level here
        self.update_log_level("LOG_LEVEL", self.config["LOG_LEVEL"])

    def event_id(self, event_name):
        """Return event id from event name, and register event if it is new."""
        try:
            event_id = self.gui_event_ids[event_name]
        except KeyError:
            event_id = len(self.gui_events)
            self.gui_event_ids[event_name] = event_id
            self.gui_events.append(event_name)
        if  event_id >= 16383:
            raise RuntimeError("Maximum number of events exceeded")
        return event_id

    def draw_y_sep(self):
        """Vertical skip."""
        self.yPos -= self.YLINESEP

    def draw_next_column(self):
        """Start a new column."""
        self.xPos += self.XCOLUMNSKIP + self.XCOLUMNSEP
        self.yPos = self.YORIGIN + Blender.Window.GetAreaSize()[1]

    def draw_slider(
        self, text, event_name, min_val, max_val, callback, val = None,
        num_items = 1, item = 0):
        """Draw a slider."""
        if val is None:
            val = self.config[event_name]
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.Slider(
            text,
            self.event_id(event_name),
            self.xPos + item*width, self.yPos, width, self.YLINESKIP,
            val, min_val, max_val,
            0, # realtime
            "", # tooltip,
            callback)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def draw_label(self, text, event_name, num_items = 1, item = 0):
        """Draw a line of text."""
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.Label(
            text,
            self.xPos + item*width, self.yPos, width, self.YLINESKIP)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def draw_list(self, text, event_name_prefix, val):
        """Create elements to select a list of things.

        Registers events PREFIX_ITEM, PREFIX_PREV, PREFIX_NEXT, PREFIX_REMOVE
        and PREFIX_ADD."""
        self.guiElements["%s_ITEM"%event_name_prefix]   = Draw.String(
            text,
            self.event_id("%s_ITEM"%event_name_prefix),
            self.xPos, self.yPos, self.XCOLUMNSKIP-90, self.YLINESKIP,
            val, 255)
        self.guiElements["%s_PREV"%event_name_prefix]   = Draw.PushButton(
            '<',
            self.event_id("%s_PREV"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-90, self.yPos, 20, self.YLINESKIP)
        self.guiElements["%s_NEXT"%event_name_prefix]   = Draw.PushButton(
            '>',
            self.event_id("%s_NEXT"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-70, self.yPos, 20, self.YLINESKIP)
        self.guiElements["%s_REMOVE"%event_name_prefix] = Draw.PushButton(
            'X',
            self.event_id("%s_REMOVE"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-50, self.yPos, 20, self.YLINESKIP)
        self.guiElements["%s_ADD"%event_name_prefix]    = Draw.PushButton(
            '...',
            self.event_id("%s_ADD"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-30, self.yPos, 30, self.YLINESKIP)
        self.yPos -= self.YLINESKIP

    def draw_toggle(self, text, event_name, val = None, num_items = 1, item = 0):
        """Draw a toggle button."""
        if val == None:
            val = self.config[event_name]
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.Toggle(
            text,
            self.event_id(event_name),
            self.xPos + item*width, self.yPos, width, self.YLINESKIP,
            val)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def draw_push_button(self, text, event_name, num_items = 1, item = 0):
        """Draw a push button."""
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.PushButton(
            text,
            self.event_id(event_name),
            self.xPos + item*width, self.yPos, width, self.YLINESKIP)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def draw_number(
        self, text, event_name, min_val, max_val, callback, val = None,
        num_items = 1, item = 0):
        """Draw an input widget for numbers."""
        if val is None:
            val = self.config[event_name]
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.Number(
            text,
            self.event_id(event_name),
            self.xPos + item*width, self.yPos, width, self.YLINESKIP,
            val,
            min_val, max_val,
            "", # tooltip
            callback)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def draw_file_browse(self, text, event_name_prefix, val = None):
        """Create elements to select a file.

        Registers events PREFIX_ITEM, PREFIX_REMOVE, PREFIX_ADD."""
        if val is None:
            val = self.config[event_name_prefix]
        self.guiElements["%s_ITEM"%event_name_prefix]   = Draw.String(
            text,
            self.event_id("%s_ITEM"%event_name_prefix),
            self.xPos, self.yPos, self.XCOLUMNSKIP-50, self.YLINESKIP,
            val, 255)
        self.guiElements["%s_REMOVE"%event_name_prefix] = Draw.PushButton(
            'X',
            self.event_id("%s_REMOVE"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-50, self.yPos, 20, self.YLINESKIP)
        self.guiElements["%s_ADD"%event_name_prefix]    = Draw.PushButton(
            '...',
            self.event_id("%s_ADD"%event_name_prefix),
            self.xPos+self.XCOLUMNSKIP-30, self.yPos, 30, self.YLINESKIP)
        self.yPos -= self.YLINESKIP

    def draw_string(self, text, event_name, max_length, callback, val = None,
                   num_items = 1, item = 0):
        """Create elements to input a string."""
        if val is None:
            val = self.config[event_name]
        width = self.XCOLUMNSKIP//num_items
        self.guiElements[event_name] = Draw.String(
            text,
            self.event_id(event_name),
            self.xPos + item*width, self.yPos, width, self.YLINESKIP,
            val,
            max_length,
            "", # tooltip
            callback)
        if item + 1 == num_items:
            self.yPos -= self.YLINESKIP

    def gui_draw(self):
        """Draw config GUI."""
        # reset position
        self.xPos = self.XORIGIN
        self.yPos = self.YORIGIN + Blender.Window.GetAreaSize()[1]

        # common options
        self.draw_label(
            text = self.WELCOME_MESSAGE,
            event_name = "LABEL_WELCOME_MESSAGE")
        self.draw_y_sep()

        self.draw_number(
            text = "Log Level",
            event_name = "LOG_LEVEL",
            min_val = 0, max_val = 99,
            callback = self.update_log_level,
            num_items = 4, item = 0)
        self.draw_push_button(
            text = "Warn",
            event_name = "LOG_LEVEL_WARN",
            num_items = 4, item = 1)
        self.draw_push_button(
            text = "Info",
            event_name = "LOG_LEVEL_INFO",
            num_items = 4, item = 2)
        self.draw_push_button(
            text = "Debug",
            event_name = "LOG_LEVEL_DEBUG",
            num_items = 4, item = 3)
        self.draw_y_sep()

        self.draw_slider(
            text = "Scale Correction:  ",
            event_name = "SCALE_CORRECTION",
            val = self.config["EXPORT_SCALE_CORRECTION"],
            min_val = 0.01, max_val = 100.0,
            callback = self.update_scale)
        self.draw_y_sep()

        # import-only options
        if self.target == self.TARGET_IMPORT:
            self.draw_label(
                text = "Texture Search Paths:",
                event_name = "TEXPATH_TEXT")
            self.draw_list(
                text = "",
                event_name_prefix = "TEXPATH",
                val = self.texpathCurrent)
            self.draw_y_sep()

            self.draw_toggle(
                text = "Import Animation",
                event_name = "IMPORT_ANIMATION")
            self.draw_y_sep()

            self.draw_toggle(
                text = "Import Extra Nodes",
                event_name = "IMPORT_EXTRANODES")
            self.draw_y_sep()
            
            self.draw_toggle(
                text = "Import Skeleton Only + Parent Selected",
                event_name = "IMPORT_SKELETON_1",
                val = (self.config["IMPORT_SKELETON"] == 1))
            self.draw_toggle(
                text = "Import Geometry Only + Parent To Selected Armature",
                event_name = "IMPORT_SKELETON_2",
                val = (self.config["IMPORT_SKELETON"] == 2))
            self.draw_y_sep()

            self.draw_toggle(
                text = "Save Embedded Textures As DDS",
                event_name = "IMPORT_EXPORTEMBEDDEDTEXTURES")
            self.draw_y_sep()

            self.draw_toggle(
                text = "Combine NiNode + Shapes Into Single Mesh",
                event_name = "IMPORT_COMBINESHAPES")
            self.draw_y_sep()

            self.draw_label(
                text = "Keyframe File:",
                event_name = "IMPORT_KEYFRAMEFILE_TEXT")
            self.draw_file_browse(
                text = "",
                event_name_prefix = "IMPORT_KEYFRAMEFILE")
            self.draw_y_sep()

            self.draw_label(
                text = "FaceGen EGM File:",
                event_name = "IMPORT_EGMFILE_TEXT")
            self.draw_file_browse(
                text = "",
                event_name_prefix = "IMPORT_EGMFILE")
            self.draw_toggle(
                text="Animate",
                event_name="IMPORT_EGMANIM",
                num_items=2, item=0)
            self.draw_slider(
                text="Scale:  ",
                event_name="IMPORT_EGMANIMSCALE",
                val=self.config["IMPORT_EGMANIMSCALE"],
                min_val=0.01, max_val=100.0,
                callback=self.update_egm_anim_scale,
                num_items=2, item=1)
            self.draw_y_sep()

            self.draw_push_button(
                text = "Restore Default Settings",
                event_name = "IMPORT_SETTINGS_DEFAULT")
            self.draw_y_sep()

            self.draw_label(
                text = "... and if skinning fails with default settings:",
                event_name = "IMPORT_SETTINGS_SKINNING_TEXT")
            self.draw_push_button(
                text = "Use The Force Luke",
                event_name = "IMPORT_SETTINGS_SKINNING")
            self.draw_y_sep()

        # export-only options
        if self.target == self.TARGET_EXPORT:

            self.draw_string(
                text = "Anim Seq Name: ",
                event_name = "EXPORT_ANIMSEQUENCENAME",
                max_length = 128,
                callback = self.update_anim_sequence_name)
            self.draw_string(
                text = "Anim Target Name: ",
                event_name = "EXPORT_ANIMTARGETNAME",
                max_length = 128,
                callback = self.update_anim_target_name)
            self.draw_number(
                text = "Bone Priority: ",
                event_name = "EXPORT_ANIMPRIORITY",
                min_val = 0, max_val = 100,
                callback = self.update_anim_priority,
                num_items = 2, item = 0)
            self.draw_toggle(
                text = "Ignore Blender Anim Props",
                event_name = "EXPORT_ANIM_DO_NOT_USE_BLENDER_PROPERTIES",
                num_items = 2, item = 1)  
            self.draw_y_sep()

            self.draw_toggle(
                text = "Combine Materials to Increase Performance",
                event_name = "EXPORT_OPTIMIZE_MATERIALS")
            self.draw_y_sep()

        self.draw_push_button(
            text = "Ok",
            event_name = "OK",
            num_items = 3, item = 0)
        # (item 1 is whitespace)
        self.draw_push_button(
            text = "Cancel",
            event_name = "CANCEL",
            num_items = 3, item = 2)

        # advanced import settings
        if self.target == self.TARGET_IMPORT:
            self.draw_next_column()

            self.draw_toggle(
                text = "Realign Bone Tail Only",
                event_name = "IMPORT_REALIGN_BONES_1",
                val = (self.config["IMPORT_REALIGN_BONES"] == 1),
                num_items = 2, item = 0)
            self.draw_toggle(
                text = "Realign Bone Tail + Roll",
                event_name = "IMPORT_REALIGN_BONES_2",
                val = (self.config["IMPORT_REALIGN_BONES"] == 2),
                num_items = 2, item = 1)
            self.draw_toggle(
                text="Merge Skeleton Roots",
                event_name="IMPORT_MERGESKELETONROOTS")
            self.draw_toggle(
                text="Send Geometries To Bind Position",
                event_name="IMPORT_SENDGEOMETRIESTOBINDPOS")
            self.draw_toggle(
                text="Send Detached Geometries To Node Position",
                event_name="IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS")
            self.draw_toggle(
                text="Send Bones To Bind Position",
                event_name="IMPORT_SENDBONESTOBINDPOS")
            self.draw_toggle(
                text = "Apply Skin Deformation",
                event_name = "IMPORT_APPLYSKINDEFORM")
            self.draw_y_sep()

        # export-only options for oblivion/fallout 3

        if (self.target == self.TARGET_EXPORT
            and self.config["game"] in ('OBLIVION', 'FALLOUT_3')):
            self.draw_next_column()
            
            self.draw_label(
                text = "Collision Options",
                event_name = "EXPORT_OB_COLLISIONHTML")
            self.draw_push_button(
                text = "Static",
                event_name = "EXPORT_OB_RIGIDBODY_STATIC",
                num_items = 5, item = 0)
            self.draw_push_button(
                text = "Anim Static",
                event_name = "EXPORT_OB_RIGIDBODY_ANIMATED",
                num_items = 5, item = 1)
            self.draw_push_button(
                text = "Clutter",
                event_name = "EXPORT_OB_RIGIDBODY_CLUTTER",
                num_items = 5, item = 2)
            self.draw_push_button(
                text = "Weapon",
                event_name = "EXPORT_OB_RIGIDBODY_WEAPON",
                num_items = 5, item = 3)
            self.draw_push_button(
                text = "Creature",
                event_name = "EXPORT_OB_RIGIDBODY_CREATURE",
                num_items = 5, item = 4)
            self.draw_toggle(
                text = "Stone",
                event_name = "EXPORT_OB_MATERIAL_STONE",
                val = self.config["EXPORT_OB_MATERIAL"] == 0,
                num_items = 6, item = 0)
            self.draw_toggle(
                text = "Cloth",
                event_name = "EXPORT_OB_MATERIAL_CLOTH",
                val = self.config["EXPORT_OB_MATERIAL"] == 1,
                num_items = 6, item = 1)
            self.draw_toggle(
                text = "Glass",
                event_name = "EXPORT_OB_MATERIAL_GLASS",
                val = self.config["EXPORT_OB_MATERIAL"] == 3,
                num_items = 6, item = 2)
            self.draw_toggle(
                text = "Metal",
                event_name = "EXPORT_OB_MATERIAL_METAL",
                val = self.config["EXPORT_OB_MATERIAL"] == 5,
                num_items = 6, item = 3)
            self.draw_toggle(
                text = "Skin",
                event_name = "EXPORT_OB_MATERIAL_SKIN",
                val = self.config["EXPORT_OB_MATERIAL"] == 7,
                num_items = 6, item = 4)
            self.draw_toggle(
                text = "Wood",
                event_name = "EXPORT_OB_MATERIAL_WOOD",
                val = self.config["EXPORT_OB_MATERIAL"] == 9,
                num_items = 6, item = 5)
            self.draw_number(
                text = "Material:  ",
                event_name = "EXPORT_OB_MATERIAL",
                min_val = 0, max_val = 30,
                callback = self.update_ob_material)
            self.draw_number(
                text = "BSX Flags:  ",
                event_name = "EXPORT_OB_BSXFLAGS",
                min_val = 0, max_val = 63,
                callback = self.update_ob_bsx_flags,
                num_items = 2, item = 0)
            self.draw_slider(
                text = "Mass:  ",
                event_name = "EXPORT_OB_MASS",
                min_val = 0.1, max_val = 1500.0,
                callback = self.update_ob_mass,
                num_items = 2, item = 1)
            self.draw_number(
                text = "Layer:  ",
                event_name = "EXPORT_OB_LAYER",
                min_val = 0, max_val = 57,
                callback = self.update_ob_layer,
                num_items = 3, item = 0)
            self.draw_number(
                text = "Motion System:  ",
                event_name = "EXPORT_OB_MOTIONSYSTEM",
                min_val = 0, max_val = 9,
                callback = self.update_ob_motion_system,
                num_items = 3, item = 1)
            self.draw_number(
                text = "Quality Type:  ",
                event_name = "EXPORT_OB_QUALITYTYPE",
                min_val = 0, max_val = 8,
                callback = self.update_ob_quality_type,
                num_items = 3, item = 2)
            self.draw_number(
                text = "Unk Byte 1:  ",
                event_name = "EXPORT_OB_UNKNOWNBYTE1",
                min_val = 1, max_val = 2,
                callback = self.update_ob_unknown_byte_1,
                num_items = 3, item = 0)
            self.draw_number(
                text = "Unk Byte 2:  ",
                event_name = "EXPORT_OB_UNKNOWNBYTE2",
                min_val = 1, max_val = 2,
                callback = self.update_ob_unknown_byte_2,
                num_items = 3, item = 1)
            self.draw_number(
                text = "Wind:  ",
                event_name = "EXPORT_OB_WIND",
                min_val = 0, max_val = 1,
                callback = self.update_ob_wind,
                num_items = 3, item = 2)
            self.draw_toggle(
                text = "Solid",
                event_name = "EXPORT_OB_SOLID",
                num_items = 2, item = 0)
            self.draw_toggle(
                text = "Hollow",
                event_name = "EXPORT_OB_HOLLOW",
                val = not self.config["EXPORT_OB_SOLID"],
                num_items = 2, item = 1)
            self.draw_y_sep()

            self.draw_toggle(
                text = "Use bhkListShape",
                event_name = "EXPORT_BHKLISTSHAPE",
                num_items = 2, item = 0)
            self.draw_toggle(
                text = "Use bhkMalleableConstraint",
                event_name = "EXPORT_OB_MALLEABLECONSTRAINT",
                num_items = 2, item = 1)
            self.draw_toggle(
                text = "Do Not Use Blender Collision Properties",
                event_name = "EXPORT_OB_COLLISION_DO_NOT_USE_BLENDER_PROPERTIES")   
            self.draw_y_sep()

            self.draw_label(
                text = "Weapon Body Location",
                event_name = "LABEL_WEAPON_LOCATION")
            self.draw_toggle(
                text = "None",
                val = self.config["EXPORT_OB_PRN"] == "NONE",
                event_name = "EXPORT_OB_PRN_NONE",
                num_items = 7, item = 0)
            self.draw_toggle(
                text = "Back",
                val = self.config["EXPORT_OB_PRN"] == "BACK",
                event_name = "EXPORT_OB_PRN_BACK",
                num_items = 7, item = 1)
            self.draw_toggle(
                text = "Side",
                val = self.config["EXPORT_OB_PRN"] == "SIDE",
                event_name = "EXPORT_OB_PRN_SIDE",
                num_items = 7, item = 2)
            self.draw_toggle(
                text = "Quiver",
                val = self.config["EXPORT_OB_PRN"] == "QUIVER",
                event_name = "EXPORT_OB_PRN_QUIVER",
                num_items = 7, item = 3)
            self.draw_toggle(
                text = "Shield",
                val = self.config["EXPORT_OB_PRN"] == "SHIELD",
                event_name = "EXPORT_OB_PRN_SHIELD",
                num_items = 7, item = 4)
            self.draw_toggle(
                text = "Helm",
                val = self.config["EXPORT_OB_PRN"] == "HELM",
                event_name = "EXPORT_OB_PRN_HELM",
                num_items = 7, item = 5)
            self.draw_toggle(
                text = "Ring",
                val = self.config["EXPORT_OB_PRN"] == "RING",
                event_name = "EXPORT_OB_PRN_RING",
                num_items = 7, item = 6)
            self.draw_y_sep()

        # export-only options for fallout 3
        if (self.target == self.TARGET_EXPORT
            and self.config["game"] == 'FALLOUT_3'):
            self.draw_next_column()

            self.draw_label(
                text = "Shader Options",
                event_name = "LABEL_FO3_SHADER_OPTIONS")
            self.draw_push_button(
                text = "Default",
                event_name = "EXPORT_FO3_SHADER_OPTION_DEFAULT",
                num_items = 3, item = 0)
            self.draw_push_button(
                text = "Skin",
                event_name = "EXPORT_FO3_SHADER_OPTION_SKIN",
                num_items = 3, item = 1)
            self.draw_push_button(
                text = "Cloth",
                event_name = "EXPORT_FO3_SHADER_OPTION_CLOTH",
                num_items = 3, item = 2)
            self.draw_toggle(
                text = "Default Type",
                val = self.config["EXPORT_FO3_SHADER_TYPE"] == 1,
                event_name = "EXPORT_FO3_SHADER_TYPE_DEFAULT",
                num_items = 2, item = 0)
            self.draw_toggle(
                text = "Skin Type",
                val = self.config["EXPORT_FO3_SHADER_TYPE"] == 14,
                event_name = "EXPORT_FO3_SHADER_TYPE_SKIN",
                num_items = 2, item = 1)
            self.draw_toggle(
                text = "Z Buffer",
                event_name = "EXPORT_FO3_SF_ZBUF",
                num_items = 3, item = 0)
            self.draw_toggle(
                text = "Shadow Map",
                event_name = "EXPORT_FO3_SF_SMAP",
                num_items = 3, item = 1)
            self.draw_toggle(
                text = "Shadow Frustum",
                event_name = "EXPORT_FO3_SF_SFRU",
                num_items = 3, item = 2)
            self.draw_toggle(
                text = "Window Envmap",
                event_name = "EXPORT_FO3_SF_WINDOW_ENVMAP",
                num_items = 3, item = 0)
            self.draw_toggle(
                text = "Empty",
                event_name = "EXPORT_FO3_SF_EMPT",
                num_items = 3, item = 1)
            self.draw_toggle(
                text = "Unknown 31",
                event_name = "EXPORT_FO3_SF_UN31",
                num_items = 3, item = 2)
            self.draw_y_sep()

            self.draw_toggle(
                text = "Use BSFadeNode Root",
                event_name = "EXPORT_FO3_FADENODE")
            self.draw_y_sep()

            self.draw_toggle(
                text = "Export Dismember Body Parts",
                event_name = "EXPORT_FO3_BODYPARTS")
            self.draw_y_sep()

        # is this needed?
        #Draw.Redraw(1)

    def gui_button_event(self, evt):
        """Event handler for buttons."""
        try:
            evName = self.gui_events[evt]
        except IndexError:
            evName = None

        if evName == "OK":
            self.save()
            self.gui_exit()
        elif evName == "CANCEL":
            self.callback = None
            self.gui_exit()
        elif evName == "TEXPATH_ADD":
            # browse and add texture search path
            Blender.Window.FileSelector(self.add_texture_path, "Add Texture Search Path")
        elif evName == "TEXPATH_NEXT":
            if self.texpathIndex < (len(self.config["IMPORT_TEXTURE_PATH"])-1):
                self.texpathIndex += 1
            self.update_texpath_current()
        elif evName == "TEXPATH_PREV":
            if self.texpathIndex > 0:
                self.texpathIndex -= 1
            self.update_texpath_current()
        elif evName == "TEXPATH_REMOVE":
            if self.texpathIndex < len(self.config["IMPORT_TEXTURE_PATH"]):
                del self.config["IMPORT_TEXTURE_PATH"][self.texpathIndex]
            if self.texpathIndex > 0:
                self.texpathIndex -= 1
            self.update_texpath_current()

        elif evName == "IMPORT_KEYFRAMEFILE_ADD":
            kffile = self.config["IMPORT_KEYFRAMEFILE"]
            if not kffile:
                kffile = os.path.dirname(self.config["IMPORT_FILE"])
            # browse and add keyframe file
            Blender.Window.FileSelector(
                self.select_keyframe_file, "Select Keyframe File", kffile)
            self.config["IMPORT_ANIMATION"] = True
        elif evName == "IMPORT_KEYFRAMEFILE_REMOVE":
            self.config["IMPORT_KEYFRAMEFILE"] = ''
            self.config["IMPORT_ANIMATION"] = False

        elif evName == "IMPORT_EGMFILE_ADD":
            egmfile = self.config["IMPORT_EGMFILE"]
            if not egmfile:
                egmfile = self.config["IMPORT_FILE"][:-3] + "egm"
            # browse and add egm file
            Blender.Window.FileSelector(
                self.select_egm_file, "Select FaceGen EGM File", egmfile)
        elif evName == "IMPORT_EGMFILE_REMOVE":
            self.config["IMPORT_EGMFILE"] = ''

        elif evName == "IMPORT_REALIGN_BONES_1":
            if self.config["IMPORT_REALIGN_BONES"] == 1:
                self.config["IMPORT_REALIGN_BONES"] = 0
            else:
                self.config["IMPORT_REALIGN_BONES"] = 1
        elif evName == "IMPORT_REALIGN_BONES_2":
            if self.config["IMPORT_REALIGN_BONES"] == 2:
                self.config["IMPORT_REALIGN_BONES"] = 0
            else:
                self.config["IMPORT_REALIGN_BONES"] = 2
        elif evName == "IMPORT_ANIMATION":
            self.config["IMPORT_ANIMATION"] = not self.config["IMPORT_ANIMATION"]
        elif evName == "IMPORT_SKELETON_1":
            if self.config["IMPORT_SKELETON"] == 1:
                self.config["IMPORT_SKELETON"] = 0
            else:
                self.config["IMPORT_SKELETON"] = 1
        elif evName == "IMPORT_SKELETON_2":
            if self.config["IMPORT_SKELETON"] == 2:
                self.config["IMPORT_SKELETON"] = 0
            else:
                self.config["IMPORT_SKELETON"] = 2
        elif evName == "IMPORT_MERGESKELETONROOTS":
            self.config["IMPORT_MERGESKELETONROOTS"] = not self.config["IMPORT_MERGESKELETONROOTS"]
        elif evName == "IMPORT_SENDGEOMETRIESTOBINDPOS":
            self.config["IMPORT_SENDGEOMETRIESTOBINDPOS"] = not self.config["IMPORT_SENDGEOMETRIESTOBINDPOS"]
        elif evName == "IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS":
            self.config["IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS"] = not self.config["IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS"]
        elif evName == "IMPORT_SENDBONESTOBINDPOS":
            self.config["IMPORT_SENDBONESTOBINDPOS"] = not self.config["IMPORT_SENDBONESTOBINDPOS"]
        elif evName == "IMPORT_APPLYSKINDEFORM":
            self.config["IMPORT_APPLYSKINDEFORM"] = not self.config["IMPORT_APPLYSKINDEFORM"]
        elif evName == "IMPORT_EXTRANODES":
            self.config["IMPORT_EXTRANODES"] = not self.config["IMPORT_EXTRANODES"]
        elif evName == "IMPORT_EXPORTEMBEDDEDTEXTURES":
            self.config["IMPORT_EXPORTEMBEDDEDTEXTURES"] = not self.config["IMPORT_EXPORTEMBEDDEDTEXTURES"]
        elif evName == "IMPORT_COMBINESHAPES":
            self.config["IMPORT_COMBINESHAPES"] = not self.config["IMPORT_COMBINESHAPES"]
        elif evName == "IMPORT_EGMANIM":
            self.config["IMPORT_EGMANIM"] = not self.config["IMPORT_EGMANIM"]
        elif evName == "IMPORT_SETTINGS_DEFAULT":
            self.config["IMPORT_ANIMATION"] = True
            self.config["IMPORT_SKELETON"] = 0
            self.config["IMPORT_EXPORTEMBEDDEDTEXTURES"] = False
            self.config["IMPORT_COMBINESHAPES"] = True
            self.config["IMPORT_REALIGN_BONES"] = 1
            self.config["IMPORT_MERGESKELETONROOTS"] = True
            self.config["IMPORT_SENDGEOMETRIESTOBINDPOS"] = True
            self.config["IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS"] = True
            self.config["IMPORT_SENDBONESTOBINDPOS"] = True
            self.config["IMPORT_APPLYSKINDEFORM"] = False
            self.config["IMPORT_EXTRANODES"] = True
            self.config["IMPORT_EGMFILE"] = ''
            self.config["IMPORT_EGMANIM"] = True
            self.config["IMPORT_EGMANIMSCALE"] = 1.0
        elif evName == "IMPORT_SETTINGS_SKINNING":
            self.config["IMPORT_ANIMATION"] = True
            self.config["IMPORT_SKELETON"] = 0
            self.config["IMPORT_EXPORTEMBEDDEDTEXTURES"] = False
            self.config["IMPORT_COMBINESHAPES"] = True
            self.config["IMPORT_REALIGN_BONES"] = 1
            self.config["IMPORT_MERGESKELETONROOTS"] = True
            self.config["IMPORT_SENDGEOMETRIESTOBINDPOS"] = False
            self.config["IMPORT_SENDDETACHEDGEOMETRIESTONODEPOS"] = False
            self.config["IMPORT_SENDBONESTOBINDPOS"] = False
            self.config["IMPORT_APPLYSKINDEFORM"] = True
            self.config["IMPORT_EXTRANODES"] = True
        elif evName[:5] == "GAME_":
            self.config["game"] = evName[5:]
            # settings that usually make sense, fail-safe
            self.config["EXPORT_SMOOTHOBJECTSEAMS"] = True
            self.config["EXPORT_STRIPIFY"] = False
            self.config["EXPORT_STITCHSTRIPS"] = False
            self.config["EXPORT_ANIMATION"] = 1
            self.config["EXPORT_FLATTENSKIN"] = False
            self.config["EXPORT_SKINPARTITION"] = False
            self.config["EXPORT_BONESPERPARTITION"] = 4
            self.config["EXPORT_PADBONES"] = False
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_MW_NIFXNIFKF"] = False
            self.config["EXPORT_MW_BS_ANIMATION_NODE"] = False
            # set default settings per game
            if self.config["game"] == 'FREEDOM_FORCE_VS_THE_3RD_REICH':
                self.config["EXPORT_SKINPARTITION"] = True
                self.config["EXPORT_PADBONES"] = True
            elif self.config["game"] == "Civilization IV":
                self.config["EXPORT_STRIPIFY"] = True
                self.config["EXPORT_STITCHSTRIPS"] = True
                self.config["EXPORT_BONESPERPARTITION"] = 18
                self.config["EXPORT_SKINPARTITION"] = True
            elif self.config["game"] in ('OBLIVION', 'FALLOUT_3'):
                self.config["EXPORT_STRIPIFY"] = True
                self.config["EXPORT_STITCHSTRIPS"] = True
                self.config["EXPORT_FLATTENSKIN"] = True
                self.config["EXPORT_BONESPERPARTITION"] = 18
                self.config["EXPORT_SKINPARTITION"] = True
                # oblivion specific settings
                self.config["EXPORT_BHKLISTSHAPE"] = False
                self.config["EXPORT_OB_MATERIAL"] = 9 # wood
                self.config["EXPORT_OB_MALLEABLECONSTRAINT"] = False
                # rigid body: static
                self.config["EXPORT_OB_BSXFLAGS"] = 2
                self.config["EXPORT_OB_MASS"] = 1000.0
                self.config["EXPORT_OB_MOTIONSYSTEM"] = 7 # MO_SYS_FIXED
                self.config["EXPORT_OB_UNKNOWNBYTE1"] = 1
                self.config["EXPORT_OB_UNKNOWNBYTE2"] = 1
                self.config["EXPORT_OB_QUALITYTYPE"] = 1 # MO_QUAL_FIXED
                self.config["EXPORT_OB_WIND"] = 0
                self.config["EXPORT_OB_LAYER"] = 1 # static
                # shader options
                self.config["EXPORT_FO3_SHADER_TYPE"] = 1
                self.config["EXPORT_FO3_SF_ZBUF"] = True
                self.config["EXPORT_FO3_SF_SMAP"] = False
                self.config["EXPORT_FO3_SF_SFRU"] = False
                self.config["EXPORT_FO3_SF_WINDOW_ENVMAP"] = False
                self.config["EXPORT_FO3_SF_EMPT"] = True
                self.config["EXPORT_FO3_SF_UN31"] = True
                # body parts
                self.config["EXPORT_FO3_BODYPARTS"] = True
            elif self.config["game"] == "Empire Earth II":
                self.config["EXPORT_SKINPARTITION"] = False
            elif self.config["game"] == "Bully SE":
                self.config["EXPORT_STRIPIFY"] = False
                self.config["EXPORT_STITCHSTRIPS"] = False
                self.config["EXPORT_FLATTENSKIN"] = False
                self.config["EXPORT_SKINPARTITION"] = True
                self.config["EXPORT_PADBONES"] = True
                self.config["EXPORT_BONESPERPARTITION"] = 4
        elif evName[:8] == "VERSION_":
            self.config["game"] = evName[8:]
        elif evName == "EXPORT_FLATTENSKIN":
            self.config["EXPORT_FLATTENSKIN"] = not self.config["EXPORT_FLATTENSKIN"]
            if self.config["EXPORT_FLATTENSKIN"]: # if skin is flattened
                self.config["EXPORT_ANIMATION"] = 1 # force geometry only
        elif evName == "EXPORT_STRIPIFY":
            self.config["EXPORT_STRIPIFY"] = not self.config["EXPORT_STRIPIFY"]
        elif evName == "EXPORT_STITCHSTRIPS":
            self.config["EXPORT_STITCHSTRIPS"] = not self.config["EXPORT_STITCHSTRIPS"]
        elif evName == "EXPORT_SMOOTHOBJECTSEAMS":
            self.config["EXPORT_SMOOTHOBJECTSEAMS"] = not self.config["EXPORT_SMOOTHOBJECTSEAMS"]
        elif evName[:17] == "EXPORT_ANIMATION_":
            value = int(evName[17:])
            self.config["EXPORT_ANIMATION"] = value
            if value == 0 or value == 2: # if animation is exported
                self.config["EXPORT_FLATTENSKIN"] = False # disable flattening skin
            elif value == 1:
                # enable flattening skin for 'geometry only' exports
                # in oblivion and fallout 3
                if self.config["game"] in ('OBLIVION', 'FALLOUT_3'):
                    self.config["EXPORT_FLATTENSKIN"] = True
        elif evName == "EXPORT_SKINPARTITION":
            self.config["EXPORT_SKINPARTITION"] = not self.config["EXPORT_SKINPARTITION"]
        elif evName == "EXPORT_PADBONES":
            self.config["EXPORT_PADBONES"] = not self.config["EXPORT_PADBONES"]
            if self.config["EXPORT_PADBONES"]: # bones are padded
                self.config["EXPORT_BONESPERPARTITION"] = 4 # force 4 bones per partition
        elif evName == "EXPORT_BHKLISTSHAPE":
            self.config["EXPORT_BHKLISTSHAPE"] = not self.config["EXPORT_BHKLISTSHAPE"]
        elif evName == "EXPORT_OB_MALLEABLECONSTRAINT":
            self.config["EXPORT_OB_MALLEABLECONSTRAINT"] = not self.config["EXPORT_OB_MALLEABLECONSTRAINT"]
        elif evName == "EXPORT_OB_COLLISION_DO_NOT_USE_BLENDER_PROPERTIES":
            self.config["EXPORT_OB_COLLISION_DO_NOT_USE_BLENDER_PROPERTIES"] = not self.config["EXPORT_OB_COLLISION_DO_NOT_USE_BLENDER_PROPERTIES"]
        elif evName == "EXPORT_OB_SOLID":
            self.config["EXPORT_OB_SOLID"] = True
        elif evName == "EXPORT_OB_HOLLOW":
            self.config["EXPORT_OB_SOLID"] = False
        elif evName == "EXPORT_OB_RIGIDBODY_STATIC":
            self.config["EXPORT_OB_MATERIAL"] = 0 # stone
            self.config["EXPORT_OB_BSXFLAGS"] = 2 # havok
            self.config["EXPORT_OB_MASS"] = 10.0
            self.config["EXPORT_OB_MOTIONSYSTEM"] = 7 # MO_SYS_FIXED
            self.config["EXPORT_OB_UNKNOWNBYTE1"] = 1
            self.config["EXPORT_OB_UNKNOWNBYTE2"] = 1
            self.config["EXPORT_OB_QUALITYTYPE"] = 1 # MO_QUAL_FIXED
            self.config["EXPORT_OB_WIND"] = 0
            self.config["EXPORT_OB_LAYER"] = 1 # static
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_OB_PRN"] = "NONE"
        elif evName == "EXPORT_OB_RIGIDBODY_ANIMATED": # see fencedoor01.nif
            self.config["EXPORT_OB_MATERIAL"] = 0 # stone
            self.config["EXPORT_OB_BSXFLAGS"] = 11 # havok + anim + unknown
            self.config["EXPORT_OB_MASS"] = 10.0
            self.config["EXPORT_OB_MOTIONSYSTEM"] = 6 # MO_SYS_KEYFRAMED
            self.config["EXPORT_OB_UNKNOWNBYTE1"] = 2
            self.config["EXPORT_OB_UNKNOWNBYTE2"] = 2
            self.config["EXPORT_OB_QUALITYTYPE"] = 2 # MO_QUAL_KEYFRAMED
            self.config["EXPORT_OB_WIND"] = 0
            self.config["EXPORT_OB_LAYER"] = 2 # OL_ANIM_STATIC
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_OB_PRN"] = "NONE"
        elif evName == "EXPORT_OB_RIGIDBODY_CLUTTER":
            self.config["EXPORT_OB_BSXFLAGS"] = 3 # anim + havok
            self.config["EXPORT_OB_MASS"] = 10.0 # typical
            self.config["EXPORT_OB_MOTIONSYSTEM"] = 4 # MO_SYS_BOX
            self.config["EXPORT_OB_UNKNOWNBYTE1"] = 2
            self.config["EXPORT_OB_UNKNOWNBYTE2"] = 2
            self.config["EXPORT_OB_QUALITYTYPE"] = 3 # MO_QUAL_DEBRIS
            self.config["EXPORT_OB_WIND"] = 0
            self.config["EXPORT_OB_LAYER"] = 4 # clutter
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_OB_PRN"] = "NONE"
        elif evName == "EXPORT_OB_RIGIDBODY_WEAPON":
            self.config["EXPORT_OB_MATERIAL"] = 5 # metal
            self.config["EXPORT_OB_BSXFLAGS"] = 3 # anim + havok
            self.config["EXPORT_OB_MASS"] = 25.0 # typical
            self.config["EXPORT_OB_MOTIONSYSTEM"] = 4 # MO_SYS_BOX
            self.config["EXPORT_OB_UNKNOWNBYTE1"] = 2
            self.config["EXPORT_OB_UNKNOWNBYTE2"] = 2
            self.config["EXPORT_OB_QUALITYTYPE"] = 3 # MO_QUAL_DEBRIS
            self.config["EXPORT_OB_WIND"] = 0
            self.config["EXPORT_OB_LAYER"] = 5 # weapin
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_OB_PRN"] = "SIDE"
        elif evName == "EXPORT_OB_RIGIDBODY_CREATURE":
            self.config["EXPORT_OB_MATERIAL"] = 7 # skin
            self.config["EXPORT_OB_BSXFLAGS"] = 7 # anim + havok + skeleton
            self.config["EXPORT_OB_MASS"] = 600.0 # single person's weight in Oblivion
            self.config["EXPORT_OB_MOTIONSYSTEM"] = 6 # MO_SYS_KEYFRAMED
            self.config["EXPORT_OB_UNKNOWNBYTE1"] = 2
            self.config["EXPORT_OB_UNKNOWNBYTE2"] = 2
            self.config["EXPORT_OB_QUALITYTYPE"] = 2 # MO_QUAL_KEYFRAMED
            self.config["EXPORT_OB_WIND"] = 0
            self.config["EXPORT_OB_LAYER"] = 8 # biped
            self.config["EXPORT_OB_SOLID"] = True
            self.config["EXPORT_OB_PRN"] = "NONE"
        elif evName == "EXPORT_OB_MATERIAL_STONE":
            self.config["EXPORT_OB_MATERIAL"] = 0
        elif evName == "EXPORT_OB_MATERIAL_CLOTH":
            self.config["EXPORT_OB_MATERIAL"] = 1
        elif evName == "EXPORT_OB_MATERIAL_GLASS":
            self.config["EXPORT_OB_MATERIAL"] = 3
        elif evName == "EXPORT_OB_MATERIAL_METAL":
            self.config["EXPORT_OB_MATERIAL"] = 5
        elif evName == "EXPORT_OB_MATERIAL_SKIN":
            self.config["EXPORT_OB_MATERIAL"] = 7
        elif evName == "EXPORT_OB_MATERIAL_WOOD":
            self.config["EXPORT_OB_MATERIAL"] = 9
        elif evName[:14] == "EXPORT_OB_PRN_":
            self.config["EXPORT_OB_PRN"] = evName[14:]
        elif evName == "EXPORT_OPTIMIZE_MATERIALS":
            self.config["EXPORT_OPTIMIZE_MATERIALS"] = not self.config["EXPORT_OPTIMIZE_MATERIALS"]
        elif evName == "LOG_LEVEL_WARN":
            self.update_log_level(evName, logging.WARNING)
        elif evName == "LOG_LEVEL_INFO":
            self.update_log_level(evName, logging.INFO)
        elif evName == "LOG_LEVEL_DEBUG":
            self.update_log_level(evName, logging.DEBUG)
        elif evName == "EXPORT_FO3_FADENODE":
            self.config["EXPORT_FO3_FADENODE"] = not self.config["EXPORT_FO3_FADENODE"]
        elif evName.startswith("EXPORT_FO3_SF_"):
            self.config[evName] = not self.config[evName]
        elif evName == "EXPORT_FO3_SHADER_TYPE_DEFAULT":
            self.config["EXPORT_FO3_SHADER_TYPE"] = 1
        elif evName == "EXPORT_FO3_SHADER_TYPE_SKIN":
            self.config["EXPORT_FO3_SHADER_TYPE"] = 14
        elif evName == "EXPORT_FO3_SHADER_OPTION_DEFAULT":
            self.config["EXPORT_FO3_SHADER_TYPE"] = 1
            self.config["EXPORT_FO3_SF_ZBUF"] = True
            self.config["EXPORT_FO3_SF_SMAP"] = False
            self.config["EXPORT_FO3_SF_SFRU"] = False
            self.config["EXPORT_FO3_SF_WINDOW_ENVMAP"] = False
            self.config["EXPORT_FO3_SF_EMPT"] = True
            self.config["EXPORT_FO3_SF_UN31"] = True
        elif evName == "EXPORT_FO3_SHADER_OPTION_SKIN":
            self.config["EXPORT_FO3_SHADER_TYPE"] = 14
            self.config["EXPORT_FO3_SF_ZBUF"] = True
            self.config["EXPORT_FO3_SF_SMAP"] = True
            self.config["EXPORT_FO3_SF_SFRU"] = False
            self.config["EXPORT_FO3_SF_WINDOW_ENVMAP"] = True
            self.config["EXPORT_FO3_SF_EMPT"] = True
            self.config["EXPORT_FO3_SF_UN31"] = True
        elif evName == "EXPORT_FO3_SHADER_OPTION_CLOTH":
            self.config["EXPORT_FO3_SHADER_TYPE"] = 1
            self.config["EXPORT_FO3_SF_ZBUF"] = True
            self.config["EXPORT_FO3_SF_SMAP"] = True
            self.config["EXPORT_FO3_SF_SFRU"] = False
            self.config["EXPORT_FO3_SF_WINDOW_ENVMAP"] = False
            self.config["EXPORT_FO3_SF_EMPT"] = True
            self.config["EXPORT_FO3_SF_UN31"] = True
        elif evName == "EXPORT_FO3_BODYPARTS":
            self.config["EXPORT_FO3_BODYPARTS"] = not self.config["EXPORT_FO3_BODYPARTS"]
        elif evName == "EXPORT_MW_NIFXNIFKF":
            self.config["EXPORT_MW_NIFXNIFKF"] = not self.config["EXPORT_MW_NIFXNIFKF"]
        elif evName == "EXPORT_MW_BS_ANIMATION_NODE":
            self.config["EXPORT_MW_BS_ANIMATION_NODE"] = not self.config["EXPORT_MW_BS_ANIMATION_NODE"]
        elif evName == "EXPORT_ANIM_DO_NOT_USE_BLENDER_PROPERTIES":
            self.config["EXPORT_ANIM_DO_NOT_USE_BLENDER_PROPERTIES"] = not self.config["EXPORT_ANIM_DO_NOT_USE_BLENDER_PROPERTIES"]
        Draw.Redraw(1)

    def gui_event(self, evt, val):
        """Event handler for GUI elements."""

        if evt == Draw.ESCKEY:
            self.callback = None
            self.gui_exit()

        Draw.Redraw(1)

    def gui_exit(self):
        """Close config GUI and call callback function."""
        Draw.Exit()
        if not self.callback: return # no callback
        # pass on control to callback function
        if not self.config["PROFILE"]:
            # without profiling
            self.callback(**self.config)
        else:
            # with profiling
            import cProfile
            import pstats
            prof = cProfile.Profile()
            prof.runctx('self.callback(**self.config)', locals(), globals())
            prof.dump_stats(self.config["PROFILE"])
            stats = pstats.Stats(self.config["PROFILE"])
            stats.strip_dirs()
            stats.sort_stats('cumulative')
            stats.print_stats()

    def add_texture_path(self, texture_path):
        texture_path = os.path.dirname(texture_path)
        if texture_path == '' or not os.path.exists(texture_path):
            Draw.PupMenu('No path selected or path does not exist%t|Ok')
        else:
            if texture_path not in self.config["IMPORT_TEXTURE_PATH"]:
                self.config["IMPORT_TEXTURE_PATH"].append(texture_path)
            self.texpathIndex = self.config["IMPORT_TEXTURE_PATH"].index(texture_path)
        self.update_texpath_current()

    def update_texpath_current(self):
        """Update self.texpathCurrent string."""
        if self.config["IMPORT_TEXTURE_PATH"]:
            self.texpathCurrent = self.config["IMPORT_TEXTURE_PATH"][self.texpathIndex]
        else:
            self.texpathCurrent = ''

    def select_keyframe_file(self, keyframefile):
        if keyframefile == '' or not os.path.exists(keyframefile):
            Draw.PupMenu('No file selected or file does not exist%t|Ok')
        else:
            self.config["IMPORT_KEYFRAMEFILE"] = keyframefile

    def select_egm_file(self, egmfile):
        if egmfile == '' or not os.path.exists(egmfile):
            Draw.PupMenu('No file selected or file does not exist%t|Ok')
        else:
            self.config["IMPORT_EGMFILE"] = egmfile

    def update_scale(self, evt, val):
        self.config["EXPORT_SCALE_CORRECTION"] = val
        self.config["IMPORT_SCALE_CORRECTION"] = 1.0 / self.config["EXPORT_SCALE_CORRECTION"]

    def update_bones_per_partition(self, evt, val):
        self.config["EXPORT_BONESPERPARTITION"] = val
        self.config["EXPORT_PADBONES"] = False

    def update_ob_bsx_flags(self, evt, val):
        self.config["EXPORT_OB_BSXFLAGS"] = val

    def update_ob_material(self, evt, val):
        self.config["EXPORT_OB_MATERIAL"] = val

    def update_ob_layer(self, evt, val):
        self.config["EXPORT_OB_LAYER"] = val

    def update_ob_mass(self, evt, val):
        self.config["EXPORT_OB_MASS"] = val

    def update_ob_motion_system(self, evt, val):
        self.config["EXPORT_OB_MOTIONSYSTEM"] = val

    def update_ob_quality_type(self, evt, val):
        self.config["EXPORT_OB_QUALITYTYPE"] = val

    def update_ob_unknown_byte_1(self, evt, val):
        self.config["EXPORT_OB_UNKNOWNBYTE1"] = val

    def update_ob_unknown_byte_2(self, evt, val):
        self.config["EXPORT_OB_UNKNOWNBYTE2"] = val

    def update_ob_wind(self, evt, val):
        self.config["EXPORT_OB_WIND"] = val

    def update_anim_sequence_name(self, evt, val):
        self.config["EXPORT_ANIMSEQUENCENAME"] = val

    def update_anim_target_name(self, evt, val):
        self.config["EXPORT_ANIMTARGETNAME"] = val
        
    def update_anim_priority(self, evt, val):
        self.config["EXPORT_ANIMPRIORITY"] = val
        
    def update_egm_anim_scale(self, evt, val):
        self.config["IMPORT_EGMANIMSCALE"] = val

def menu_func_import(self, context):
    self.layout.operator(
        NifImportUI.bl_idname, text="NetImmerse/Gamebryo (.nif)")

def menu_func_export(self, context):
    self.layout.operator(
        NifExportUI.bl_idname, text="NetImmerse/Gamebryo (.nif)")

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_file_import.append(menu_func_import)
    bpy.types.INFO_MT_file_export.append(menu_func_export)

def unregister():
    bpy.utils.unregister_module(__name__)
    bpy.types.INFO_MT_file_import.remove(menu_func_import)
    bpy.types.INFO_MT_file_export.remove(menu_func_export)

if __name__ == "__main__":
    register()
