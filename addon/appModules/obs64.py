"""OBS Studio accessibility app module for NVDA.

Loaded automatically when obs64.exe is the foreground process.
"""

from collections import deque

import api
import appModuleHandler
import controlTypes
import eventHandler
import speech
import ui
import winUser
from logHandler import log
from NVDAObjects import NVDAObject
from scriptHandler import script

ADDON_VERSION = "0.8.1"
SCRIPT_CATEGORY = "OBS Accessibility"


class _NamedOverlay(NVDAObject):
    """Base for overlays that supply a static name (and optionally a static
    description) to an unnamed or jargon-labeled control."""

    _overrideName = ""
    _overrideDescription = ""

    def _get_name(self):
        return self._overrideName

    def _get_description(self):
        return self._overrideDescription


class _DescriptionOnly(NVDAObject):
    """Overlay that adds a static description to a control but leaves OBS's
    natural name in place. Use when OBS already labels the control adequately
    and we just want to teach the user what the control does."""

    _overrideDescription = ""

    def _get_description(self):
        return self._overrideDescription


class _PreviewScalingMode(_NamedOverlay):
    _overrideName = "Preview scaling"
    _overrideDescription = (
        "How the preview window is sized. "
        "Affects only what you see locally — does not change the broadcast."
    )


class _HotkeyFilterSearch(_NamedOverlay):
    _overrideName = "Filter hotkeys by name"
    _overrideDescription = (
        "Type to narrow the hotkey list to actions whose name matches."
    )


class _HotkeyFilterInput(_NamedOverlay):
    _overrideName = "Filter hotkeys by key binding"
    _overrideDescription = (
        "Press a key combination to find which hotkey, if any, is bound to it."
    )


class _HotkeyFilterReset(_NamedOverlay):
    _overrideName = "Clear hotkey filter"
    _overrideDescription = "Show all hotkeys again."


class _AdvOutEncoder(_NamedOverlay):
    _overrideName = "Video encoder"
    _overrideDescription = (
        "Hardware encoders (NVENC, AMF) free up your CPU. "
        "Software encoder (x264) is most compatible."
    )


class _AdvOutAEncoder(_NamedOverlay):
    _overrideName = "Audio encoder"
    _overrideDescription = (
        "Sets the audio codec. FFmpeg AAC works everywhere."
    )


class _AdvOutRescaleFilter(_NamedOverlay):
    _overrideName = "Output rescale filter"
    _overrideDescription = (
        "Resize the streamed output. Disabled keeps the canvas size. "
        "Bilinear is fastest, Lanczos sharpest."
    )


class _AdvOutRescale(_NamedOverlay):
    _overrideName = "Output rescale resolution"
    _overrideDescription = (
        "Target size, like 1280 by 720. "
        "Used when rescale filter is on."
    )


class _AdvOutRecPath(_NamedOverlay):
    _overrideName = "Recording path"
    _overrideDescription = "Folder where recordings are saved."


class _AdvOutRecFormat(_NamedOverlay):
    _overrideName = "Recording format"
    _overrideDescription = (
        "Hybrid MP4 is widely compatible. "
        "MKV survives crashes — remux to MP4 afterward if needed."
    )


class _AdvOutRecEncoder(_NamedOverlay):
    _overrideName = "Video encoder"
    _overrideDescription = (
        "Hardware encoders (NVENC, AMF) free up your CPU. "
        "Software encoder (x264) is most compatible."
    )


class _AdvOutRecAEncoder(_NamedOverlay):
    _overrideName = "Audio encoder"
    _overrideDescription = (
        "Sets the audio codec. FFmpeg AAC works everywhere."
    )


class _AdvOutRecRescaleFilter(_NamedOverlay):
    _overrideName = "Output rescale filter"
    _overrideDescription = (
        "Resize the recorded output. Disabled keeps the canvas size. "
        "Bilinear is fastest, Lanczos sharpest."
    )


class _AdvOutRecRescale(_NamedOverlay):
    _overrideName = "Output rescale resolution"
    _overrideDescription = (
        "Target size, like 1280 by 720. "
        "Used when rescale filter is on."
    )


class _AdvOutMuxCustom(_NamedOverlay):
    _overrideName = "Custom muxer settings"
    _overrideDescription = (
        "Advanced muxer flags. Leave blank unless you know you need them."
    )


class _AdvOutRecType(_DescriptionOnly):
    _overrideDescription = (
        "Output mode. Standard records to a file using the format below. "
        "Custom Output FFmpeg is for advanced multi-output workflows."
    )


class _AdvOutRecTrack(_DescriptionOnly):
    _overrideDescription = (
        "Include this audio track in the recording. "
        "Multiple tracks can be enabled — useful for separating game audio, "
        "mic, and music for editing later."
    )


class _AdvOutSplitFile(_DescriptionOnly):
    _overrideDescription = (
        "Start a new file on a schedule or size limit "
        "so a long session doesn't produce one giant file."
    )


class _AdvOutTrackBitrate(_DescriptionOnly):
    _overrideDescription = (
        "Bits per second for this audio track. "
        "128 to 192 is good for voice and most music; "
        "320 for high-quality music streams."
    )


class _AdvOutTrackName(_DescriptionOnly):
    _overrideDescription = (
        "Display name for this audio track. "
        "Used by streaming destinations that accept multi-track audio "
        "(such as Twitch's multitrack feature)."
    )


class _AdvReplayBuf(_DescriptionOnly):
    _overrideDescription = (
        "Keep the last few seconds of video buffered in memory "
        "so you can save instant replays. "
        "Press your Save Replay hotkey to write the buffer to disk."
    )


class _AdvRBSecMax(_NamedOverlay):
    _overrideName = "Maximum replay time"
    _overrideDescription = (
        "How many seconds of video to keep buffered. "
        "When you press Save Replay, the most recent stretch up to this length "
        "is written to a file. Higher values use more memory."
    )


class _OBSPropertyField(NVDAObject):
    """Overlay for inputs inside an OBSPropertiesView (encoder property rows,
    source property rows, etc.).

    OBS lays these out as label-then-input pairs of UIA siblings inside a
    PropertiesContainer. Every input shares the same automation-ID suffix
    (e.g. ``.PropertiesContainer.QComboBox``), so we can't disambiguate
    statically — we have to walk back to the preceding sibling QLabel and
    use its text as the name.

    Descriptions are keyed off the resolved label text. The dictionary is
    encoder-agnostic — labels that mean the same thing across NVENC, x264,
    AMF and QuickSync share an entry. If we don't have a custom description,
    we fall back to OBS's native UIA description (some property widgets
    carry useful tooltip text, e.g. the "Custom Encoder Settings" line edit).
    """

    _UIA_LabelClassNames = ("QLabel", "OBSLabel")
    _UIA_FullDescriptionPropertyId = 30159
    _UIA_HelpTextPropertyId = 30013

    _LABEL_DESCRIPTIONS = {
        "rate control": (
            "How the encoder picks bitrate. "
            "CBR is most predictable for streaming. "
            "CQP and CRF aim at a quality level instead — better for recording."
        ),
        "bitrate": (
            "Target bits per second. "
            "Higher means better quality and bigger files. "
            "For streaming, must fit comfortably inside your upload speed."
        ),
        "max bitrate": (
            "Upper limit for variable-bitrate modes. "
            "Spikes above this are clipped."
        ),
        "buffer size": (
            "How many seconds of output the encoder may go over budget for. "
            "Larger smooths bitrate but increases latency."
        ),
        "use custom buffer size": (
            "Override the encoder's automatic buffer-size choice. "
            "Most users should leave this off."
        ),
        "crf": (
            "Quality target — lower is higher quality. "
            "Roughly: 18 near-lossless, 23 default, 28 small file."
        ),
        "cq level": (
            "Quality target for NVENC — lower is higher quality. "
            "20 to 23 is a good range for recording."
        ),
        "cqp": (
            "Quality target — lower is higher quality. "
            "Use when you want consistent visual quality regardless of motion."
        ),
        "keyframe interval": (
            "How often a full reference frame is inserted, in seconds. "
            "Streaming services usually want 2. "
            "Zero lets the encoder choose."
        ),
        "preset": (
            "Trades encoding speed for compression efficiency. "
            "Slower presets give smaller files "
            "or better quality at the same bitrate."
        ),
        "cpu usage preset": (
            "x264 speed-versus-quality tradeoff. "
            "Faster reduces CPU load; "
            "slower improves quality at the same bitrate."
        ),
        "tune": (
            "Optimizes the encoder for a specific kind of content. "
            "Leave default unless you have a reason."
        ),
        "tuning": (
            "Optimizes the encoder for a goal. "
            "High Quality is the safe default; "
            "Low Latency reduces delay for streaming."
        ),
        "multipass mode": (
            "Two-pass analysis improves bitrate distribution "
            "at a small extra cost. "
            "Quarter Resolution is a good balance of quality and speed."
        ),
        "profile": (
            "Codec profile. "
            "Use main or high for modern devices; "
            "baseline only if targeting very old hardware."
        ),
        "look-ahead": (
            "Lets the encoder peek at upcoming frames to budget bitrate better. "
            "Costs some CPU. "
            "Off is fine for most streaming."
        ),
        "psycho visual tuning": (
            "Spends extra bits on detail the eye notices most. "
            "Generally improves perceived quality."
        ),
        "gpu": (
            "Which GPU to encode on if you have multiple. "
            "Leave at 0 if unsure."
        ),
        "max b-frames": (
            "Bidirectional frames improve compression "
            "by referencing past and future frames. "
            "Two is a safe default; some old players don't support more."
        ),
        "b-frames": (
            "Bidirectional frames improve compression "
            "by referencing past and future frames. "
            "Two is a safe default."
        ),
        "custom encoder settings": (
            "Advanced encoder flags. "
            "Leave blank unless you have a specific recipe."
        ),
    }

    @classmethod
    def _normalizeLabelKey(cls, label):
        # Drop parenthetical hints like "Keyframe Interval (seconds, 0=auto)"
        # and normalize for case-insensitive lookup.
        import re
        cleaned = re.sub(r"\s*\([^)]*\)", "", label or "")
        return cleaned.strip().rstrip(":").strip().lower()

    def _readPrecedingLabel(self):
        try:
            import UIAHandler
            walker = UIAHandler.handler.clientObject.RawViewWalker
            cur = self.UIAElement
        except Exception:
            return ""
        # Walk a few previous siblings — the immediate previous sibling is
        # almost always the label, but allow a small budget in case Qt's
        # UIA bridge inserts spacers between rows.
        for _ in range(4):
            try:
                prev = walker.GetPreviousSiblingElement(cur)
            except Exception:
                return ""
            if prev is None:
                return ""
            try:
                cls = prev.CurrentClassName or ""
                text = prev.CurrentName or ""
            except Exception:
                return ""
            if cls in self._UIA_LabelClassNames and text:
                return text.rstrip(":").strip()
            cur = prev
        return ""

    def _readNativeDescription(self):
        """Read OBS's UIA description directly. Used as fallback when no
        custom description is mapped — preserves OBS's own tooltip text."""
        try:
            elem = self.UIAElement
        except Exception:
            return ""
        for propId in (
            self._UIA_FullDescriptionPropertyId,
            self._UIA_HelpTextPropertyId,
        ):
            try:
                v = elem.GetCurrentPropertyValue(propId)
            except Exception:
                continue
            if v:
                return str(v)
        return ""

    def _get_name(self):
        return self._readPrecedingLabel()

    def _get_description(self):
        key = self._normalizeLabelKey(self.name)
        if key and key in self._LABEL_DESCRIPTIONS:
            return self._LABEL_DESCRIPTIONS[key]
        return self._readNativeDescription()


class _OBSVolumeSlider(NVDAObject):
    """Overlay for OBS volume sliders.

    Polls the slider's UIA ValuePattern while it has focus and announces the
    value when it changes. NVDA's natural value-change handling is unreliable
    for these sliders because Qt's UIA bridge fires events inconsistently.

    Note: OBS's volume slider has an internal step finer than its 0.1 dB
    display precision, so adjacent presses sometimes leave the displayed
    value unchanged. Those presses are intentionally not announced — there
    is nothing new to say. Two presses per displayed dB step is expected.
    """

    _lastSpokenValue = None
    _polling = False

    def _readUIAValue(self):
        val = ""
        try:
            from comInterfaces import UIAutomationClient as UIA
            raw = self.UIAElement.GetCurrentPattern(10002)  # UIA_ValuePatternId
            if raw is not None:
                pattern = raw.QueryInterface(UIA.IUIAutomationValuePattern)
                v = pattern.CurrentValue
                if v not in (None, ""):
                    val = str(v)
        except Exception:
            pass
        if not val:
            try:
                v = self.UIAElement.GetCurrentPropertyValue(30045)
                if v not in (None, ""):
                    val = str(v)
            except Exception:
                pass
        # -0.0 dB and 0.0 dB sound identical when spoken; collapse to avoid
        # an inaudible-feeling extra announcement when the slider crosses zero.
        if val == "-0.0 dB":
            val = "0.0 dB"
        return val

    def event_gainFocus(self):
        super().event_gainFocus()
        self._lastSpokenValue = self._readUIAValue()
        if not self._polling:
            self._polling = True
            self._scheduleNextPoll()

    def event_valueChange(self):
        # Suppress NVDA's natural announce; our poll is the single source.
        pass

    def _scheduleNextPoll(self):
        try:
            import wx
            wx.CallLater(30, self._poll)
        except Exception:
            self._polling = False

    def _poll(self):
        try:
            stillFocused = api.getFocusObject() is self
        except Exception:
            stillFocused = False
        if not stillFocused:
            self._polling = False
            return
        cur = self._readUIAValue()
        if cur and cur != self._lastSpokenValue:
            ui.message(cur)
            self._lastSpokenValue = cur
        self._scheduleNextPoll()




def _findAncestorHotkeyWidget(obj):
    """Walk up obj's ancestor chain; return the first OBSHotkeyWidget, or None."""
    cur = obj
    for _ in range(10):
        if cur is None:
            return None
        try:
            if cur.UIAElement.cachedClassName == "OBSHotkeyWidget":
                return cur
        except Exception:
            pass
        try:
            cur = cur.parent
        except Exception:
            return None
    return None


class _OBSHotkeyRowEdit(NVDAObject):
    """Overlay for the binding-input edit inside an OBSHotkeyWidget row.

    Without overlay, NVDA hears these as just "edit" because OBS leaves the
    name blank (it relies on the visible label sitting beside the row).
    We compose a name from the parent OBSHotkeyWidget's action name, so users
    hear something like "Start Recording hotkey binding, edit" when they
    land on the row.
    """

    def _get_name(self):
        widget = _findAncestorHotkeyWidget(self)
        if widget is not None and widget.name:
            return f"{widget.name} hotkey binding"
        return ""


class _OBSHotkeyRowButton(NVDAObject):
    """Overlay for the four QPushButton siblings inside an OBSHotkeyWidget row.

    OBS sets the description to the button's purpose (Revert / Clear / Add /
    Remove) but leaves name blank. We pull the description into the name and
    prefix it with the row's action so users hear e.g. "Revert Start Recording
    binding" — and clear the description to avoid double-announcement.
    """

    # UIA property IDs (stable Microsoft constants).
    _UIA_FullDescriptionPropertyId = 30159
    _UIA_HelpTextPropertyId = 30013

    def _readUnderlyingDescription(self):
        """Read the underlying UIA description directly, bypassing our own
        _get_description override (which is set to suppress duplicate
        announcement). Tries FullDescription first, then HelpText."""
        try:
            elem = self.UIAElement
        except Exception:
            return ""
        for propId in (
            self._UIA_FullDescriptionPropertyId,
            self._UIA_HelpTextPropertyId,
        ):
            try:
                val = elem.GetCurrentPropertyValue(propId)
            except Exception:
                continue
            if val:
                return str(val)
        return ""

    def _get_name(self):
        desc = self._readUnderlyingDescription()
        widget = _findAncestorHotkeyWidget(self)
        action = widget.name if widget is not None else ""
        if desc and action:
            return f"{desc} {action} binding"
        return desc or action or ""

    def _get_description(self):
        return ""


_OVERLAY_BY_AUTOMATION_ID_SUFFIX = (
    (".previewScalingMode", _PreviewScalingMode),
    (".hotkeyFilterSearch", _HotkeyFilterSearch),
    (".hotkeyFilterInput", _HotkeyFilterInput),
    (".hotkeyFilterReset", _HotkeyFilterReset),
    (".OBSHotkeyWidget.OBSHotkeyEdit", _OBSHotkeyRowEdit),
    (".OBSHotkeyWidget.QPushButton", _OBSHotkeyRowButton),
    (".volMeterFrame.VolumeSlider", _OBSVolumeSlider),
    # Streaming tab (advOutputStreamTab)
    (".advOutEncoder", _AdvOutEncoder),
    (".advOutAEncoder", _AdvOutAEncoder),
    (".advOutRescaleFilter", _AdvOutRescaleFilter),
    (".advOutRescale.QLineEdit", _AdvOutRescale),
    # Recording tab (advOutputRecordTab)
    (".advOutRecType", _AdvOutRecType),
    (".advOutRecPath", _AdvOutRecPath),
    (".advOutRecFormat", _AdvOutRecFormat),
    (".advOutRecEncoder", _AdvOutRecEncoder),
    (".advOutRecAEncoder", _AdvOutRecAEncoder),
    (".advOutRecRescaleFilter", _AdvOutRecRescaleFilter),
    (".advOutRecRescale.QLineEdit", _AdvOutRecRescale),
    (".advOutMuxCustom", _AdvOutMuxCustom),
    (".advOutSplitFile", _AdvOutSplitFile),
    (".advOutRecTrack1", _AdvOutRecTrack),
    (".advOutRecTrack2", _AdvOutRecTrack),
    (".advOutRecTrack3", _AdvOutRecTrack),
    (".advOutRecTrack4", _AdvOutRecTrack),
    (".advOutRecTrack5", _AdvOutRecTrack),
    (".advOutRecTrack6", _AdvOutRecTrack),
    # Audio tab (advOutputAudioTracksTab) — six tracks, two fields each
    (".advOutTrack1Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack2Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack3Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack4Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack5Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack6Bitrate", _AdvOutTrackBitrate),
    (".advOutTrack1Name", _AdvOutTrackName),
    (".advOutTrack2Name", _AdvOutTrackName),
    (".advOutTrack3Name", _AdvOutTrackName),
    (".advOutTrack4Name", _AdvOutTrackName),
    (".advOutTrack5Name", _AdvOutTrackName),
    (".advOutTrack6Name", _AdvOutTrackName),
    # Replay Buffer tab (advOutputReplayTab)
    (".advReplayBuf", _AdvReplayBuf),
    (".advRBSecMax", _AdvRBSecMax),
    # Generic — any input inside an OBSPropertiesView. Keep these LAST so
    # the more specific suffixes above always win first.
    (".PropertiesContainer.QComboBox", _OBSPropertyField),
    (".PropertiesContainer.SpinBoxIgnoreScroll", _OBSPropertyField),
    (".PropertiesContainer.QLineEdit", _OBSPropertyField),
    (".PropertiesContainer.QCheckBox", _OBSPropertyField),
    (".PropertiesContainer.QSpinBox", _OBSPropertyField),
    (".PropertiesContainer.QDoubleSpinBox", _OBSPropertyField),
)


def _walk(root, max_depth=15):
    seen = set()
    queue = deque([(root, 0)])
    while queue:
        obj, depth = queue.popleft()
        if depth > max_depth:
            continue
        key = id(obj)
        if key in seen:
            continue
        seen.add(key)
        yield obj
        try:
            children = list(obj.children)
        except Exception:
            continue
        for child in children:
            queue.append((child, depth + 1))


def _findFocusable(root, idSubstring, preferredRole=None):
    """Find a focusable descendant whose UIAAutomationId contains idSubstring.

    Considers only descendants in the FOCUSABLE state. Preference order:
      1. FOCUSED + role match (already there — early return)
      2. SELECTED + role match (the active item in a list)
      3. FOCUSED (any role)
      4. role match
      5. any focusable descendant
    """
    selectedRoleMatch = None
    focused = None
    roleMatch = None
    fallback = None
    for obj in _walk(root):
        try:
            aid = obj.UIAAutomationId or ""
        except Exception:
            continue
        if idSubstring not in aid:
            continue
        try:
            states = obj.states
            if controlTypes.State.FOCUSABLE not in states:
                continue
        except Exception:
            continue
        try:
            roleMatches = preferredRole is None or obj.role == preferredRole
        except Exception:
            roleMatches = False
        if controlTypes.State.FOCUSED in states and roleMatches:
            return obj
        if controlTypes.State.SELECTED in states and roleMatches and selectedRoleMatch is None:
            selectedRoleMatch = obj
        if controlTypes.State.FOCUSED in states and focused is None:
            focused = obj
        if roleMatches and roleMatch is None:
            roleMatch = obj
        if fallback is None:
            fallback = obj
    return selectedRoleMatch or focused or roleMatch or fallback


def _collapseCombobox(obj):
    """Close a combobox's dropdown via UIA ExpandCollapsePattern.

    More reliable than sending an Escape key, which can race with Qt's popup
    rendering and leave the popup capturing subsequent input.
    """
    try:
        from comInterfaces import UIAutomationClient as UIA
        elem = obj.UIAElement
        raw = elem.GetCurrentPattern(UIA.UIA_ExpandCollapsePatternId)
        if raw is None:
            log.info("OBS combobox: ExpandCollapsePattern not exposed")
            return False
        pattern = raw.QueryInterface(UIA.IUIAutomationExpandCollapsePattern)
        pattern.Collapse()
        log.info("OBS combobox: Collapse OK")
        return True
    except Exception as e:
        log.info(f"OBS combobox: Collapse failed, falling back to Escape: {e}")
        try:
            winUser.keybd_event(0x1B, 0, 0, 0)
            winUser.keybd_event(0x1B, 0, winUser.KEYEVENTF_KEYUP, 0)
            return True
        except Exception as ee:
            log.warning(f"OBS combobox: Escape fallback also failed: {ee}")
            return False


def _mouseClickAt(obj):
    """Simulate a left click at the center of obj's screen location.

    Used for Qt virtual UIA elements like QListView items, where UIA SetFocus
    is a silent no-op. Restores cursor afterward so the user's cursor doesn't
    visibly move from where they left it.
    """
    try:
        loc = obj.location
    except Exception as e:
        log.warning(f"OBS click: getting location failed: {e}")
        return False
    if loc is None:
        log.warning("OBS click: object has no location")
        return False
    try:
        cx = loc.left + loc.width // 2
        cy = loc.top + loc.height // 2
    except Exception as e:
        log.warning(f"OBS click: computing center failed: {e}")
        return False
    saved = None
    try:
        saved = winUser.getCursorPos()
    except Exception:
        pass
    try:
        winUser.setCursorPos(cx, cy)
        winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        log.info(f"OBS click: clicked at ({cx},{cy}) on {obj.name!r}")
        return True
    except Exception as e:
        log.warning(f"OBS click: mouse event failed: {e}")
        return False
    finally:
        if saved is not None:
            try:
                winUser.setCursorPos(saved[0], saved[1])
            except Exception:
                pass


def _findHotkeyRows():
    """Return all OBSHotkeyWidget UIA elements on the active Hotkeys page,
    in document order.

    Uses UIA FindAll for a single fast COM round-trip; falls back to NVDA's
    BFS tree walk if the UIA path is unavailable. Returns raw UIA elements
    (not NVDA wrappers) so we don't pay the per-object construction cost
    that was making the fast path no faster than BFS.
    """
    rows = _findHotkeyRowsUIA()
    if rows is not None:
        return rows
    return _findHotkeyRowsBFS()


def _findHotkeyRowsUIA():
    """Fast path: UIA FindAll, returning raw UIA elements."""
    try:
        import UIAHandler
    except Exception as e:
        log.info(f"OBS hotkey rows: UIAHandler unavailable: {e}")
        return None
    try:
        clientObject = UIAHandler.handler.clientObject
        # UIA_ClassNamePropertyId = 30012; TreeScope_Descendants = 4
        condition = clientObject.CreatePropertyCondition(30012, "OBSHotkeyWidget")
        root = api.getForegroundObject()
        elements = root.UIAElement.FindAll(4, condition)
        rows = []
        for i in range(elements.Length):
            elem = elements.GetElement(i)
            try:
                aid = elem.CurrentAutomationId or ""
            except Exception:
                continue
            if ".hotkeyPage." in aid:
                rows.append(elem)
        return rows
    except Exception as e:
        log.warning(f"OBS hotkey rows: UIA FindAll failed: {e}")
        return None


def _findHotkeyRowsBFS():
    """BFS fallback returning raw UIA elements (not NVDA wrappers)."""
    root = api.getForegroundObject()
    rows = []
    for obj in _walk(root):
        try:
            aid = obj.UIAAutomationId or ""
            cls = obj.UIAElement.cachedClassName or ""
        except Exception:
            continue
        if cls == "OBSHotkeyWidget" and ".hotkeyPage." in aid:
            try:
                rows.append(obj.UIAElement)
            except Exception:
                continue
    return rows


def _findCurrentHotkeyWidget():
    """Walk up from the focused object's UIA element via TreeWalker to find
    the enclosing OBSHotkeyWidget. Returns a raw UIA element or None."""
    focus = api.getFocusObject()
    try:
        cur = focus.UIAElement
    except Exception:
        return None
    try:
        import UIAHandler
        treeWalker = UIAHandler.handler.clientObject.RawViewWalker
    except Exception:
        return None
    for _ in range(20):
        if cur is None:
            return None
        try:
            if (cur.CurrentClassName or "") == "OBSHotkeyWidget":
                return cur
        except Exception:
            return None
        try:
            cur = treeWalker.GetParentElement(cur)
        except Exception:
            return None
    return None


def _focusHotkeyRowEdit(widget_elem):
    """Find the OBSHotkeyEdit child of the given OBSHotkeyWidget UIA element
    and set focus on it via the UIA SetFocus method directly."""
    try:
        import UIAHandler
        clientObject = UIAHandler.handler.clientObject
        # UIA_ClassNamePropertyId = 30012; TreeScope_Children = 2
        condition = clientObject.CreatePropertyCondition(30012, "OBSHotkeyEdit")
        editElem = widget_elem.FindFirst(2, condition)
        if editElem is None:
            return False
        editElem.SetFocus()
        return True
    except Exception as e:
        log.warning(f"OBS hotkey row: setFocus on edit failed: {e}")
        return False


def _rowName(elem):
    """Get a UIA element's name string (the row's action name)."""
    try:
        return elem.CurrentName or ""
    except Exception:
        return ""


def _invokeUIAElement(elem):
    """Invoke a UIA element via its InvokePattern (programmatic click).
    Returns True on success."""
    try:
        from comInterfaces import UIAutomationClient as UIA
    except Exception as e:
        log.info(f"OBS invoke: comInterfaces unavailable: {e}")
        return False
    try:
        raw = elem.GetCurrentPattern(10000)  # UIA_InvokePatternId
        if not raw:
            return False
        pattern = raw.QueryInterface(UIA.IUIAutomationInvokePattern)
        pattern.Invoke()
        return True
    except Exception as e:
        log.warning(f"OBS invoke pattern failed: {e}")
        return False


def _findControlButton(automationIdSuffix):
    """Find a QPushButton in the OBS controls dock whose AutomationId ends
    with the given suffix (e.g. '.streamButton'). Returns a UIA element or None."""
    try:
        import UIAHandler
    except Exception:
        return None
    try:
        clientObject = UIAHandler.handler.clientObject
        condition = clientObject.CreatePropertyCondition(30012, "QPushButton")
        root = api.getForegroundObject()
        elements = root.UIAElement.FindAll(4, condition)
        for i in range(elements.Length):
            elem = elements.GetElement(i)
            try:
                aid = elem.CurrentAutomationId or ""
            except Exception:
                continue
            if aid.endswith(automationIdSuffix):
                return elem
    except Exception as e:
        log.warning(f"OBS find control button {automationIdSuffix}: {e}")
    return None


def _pastTenseAction(buttonText):
    """Convert an OBS toggle-button label into a past-tense announcement.

    Reads the label *before* invoking so we can describe what just happened
    rather than the new label, which would be the inverse action."""
    if buttonText.startswith("Start "):
        return f"Started {buttonText[6:].lower()}"
    if buttonText.startswith("Stop "):
        return f"Stopped {buttonText[5:].lower()}"
    if buttonText == "Pause Recording":
        return "Recording paused"
    if buttonText in ("Unpause Recording", "Resume Recording"):
        return "Recording resumed"
    return buttonText or "Action performed"


def _toggleControlButton(automationIdSuffix, notFoundMsg):
    elem = _findControlButton(automationIdSuffix)
    if elem is None:
        ui.message(notFoundMsg)
        return
    try:
        currentText = elem.CurrentName or ""
    except Exception:
        currentText = ""
    if not _invokeUIAElement(elem):
        ui.message(f"Could not activate {currentText or 'control button'}")
        return
    ui.message(_pastTenseAction(currentText))


def _findSettingsButton(buttonName):
    """Find the QPushButton in OBSBasicSettings.buttonBox with the given name.
    Returns a raw UIA element or None."""
    try:
        import UIAHandler
    except Exception:
        return None
    try:
        clientObject = UIAHandler.handler.clientObject
        condition = clientObject.CreatePropertyCondition(30012, "QPushButton")
        root = api.getForegroundObject()
        elements = root.UIAElement.FindAll(4, condition)
        for i in range(elements.Length):
            elem = elements.GetElement(i)
            try:
                aid = elem.CurrentAutomationId or ""
                btnName = elem.CurrentName or ""
            except Exception:
                continue
            if ".OBSBasicSettings.buttonBox." in aid and btnName == buttonName:
                return elem
    except Exception as e:
        log.warning(f"OBS settings button find: {e}")
    return None


def _dumpObject(label, obj):
    lines = [f"=== OBS {label} inspect ==="]
    lines.append(f"name: {obj.name!r}")
    lines.append(f"role: {obj.role!r}")
    lines.append(f"description: {obj.description!r}")
    lines.append(f"value: {obj.value!r}")
    lines.append(f"states: {obj.states!r}")
    lines.append(f"windowClassName: {obj.windowClassName!r}")
    lines.append(f"windowControlID: {obj.windowControlID!r}")
    lines.append(f"location: {obj.location!r}")

    for attr in ("IA2Attributes", "UIAAutomationId"):
        if hasattr(obj, attr):
            try:
                lines.append(f"{attr}: {getattr(obj, attr)!r}")
            except Exception as e:
                lines.append(f"{attr}: <error {e}>")

    if hasattr(obj, "UIAElement"):
        try:
            lines.append(f"UIA className: {obj.UIAElement.cachedClassName!r}")
        except Exception as e:
            lines.append(f"UIA className: <error {e}>")

    parent = obj.parent
    for depth in range(6):
        if not parent:
            break
        lines.append(
            f"parent[{depth}]: name={parent.name!r} "
            f"role={parent.role!r} "
            f"windowClassName={parent.windowClassName!r}"
        )
        parent = parent.parent

    try:
        children = list(obj.children)
        lines.append(f"children count: {len(children)}")
        for i, child in enumerate(children[:10]):
            child_id = ""
            if hasattr(child, "UIAAutomationId"):
                try:
                    child_id = f" automationId={child.UIAAutomationId!r}"
                except Exception:
                    pass
            lines.append(
                f"child[{i}]: name={child.name!r} "
                f"role={child.role!r}{child_id}"
            )
    except Exception as e:
        lines.append(f"children: <error {e}>")
    return lines


class AppModule(appModuleHandler.AppModule):

    # All scripts on this app module are grouped under this category in
    # NVDA's Input Gestures dialog, so users can rebind any of them by
    # opening NVDA → Preferences → Input gestures while OBS is focused.
    scriptCategory = SCRIPT_CATEGORY

    def chooseNVDAObjectOverlayClasses(self, obj, clsList):
        try:
            aid = obj.UIAAutomationId or ""
        except Exception:
            return
        if not aid:
            return
        for suffix, overlayCls in _OVERLAY_BY_AUTOMATION_ID_SUFFIX:
            if aid.endswith(suffix):
                clsList.insert(0, overlayCls)
                return

    def _jumpTo(self, idSubstring, friendlyName, role=None):
        root = api.getForegroundObject()
        target = _findFocusable(root, idSubstring, preferredRole=role)
        if target is None:
            log.info(f"OBS jump: '{friendlyName}' → no target found")
            ui.message(f"{friendlyName}: not found")
            return

        try:
            targetAid = target.UIAAutomationId or ""
        except Exception:
            targetAid = ""
        log.info(
            f"OBS jump: '{friendlyName}' → {targetAid!r} "
            f"(name={target.name!r}, role={target.role!r})"
        )

        # Detect whether target is already the system-focused object — if so,
        # setFocus is a no-op and Qt fires no focus event, so NVDA wouldn't
        # naturally announce. We force-speak in that case.
        currentFocus = api.getFocusObject()
        alreadyFocused = currentFocus is target

        if target.role == controlTypes.Role.LISTITEM:
            # Qt's QListView items aren't real focusable widgets; UIA SetFocus
            # is a silent no-op. Use a real mouse click instead — Qt processes
            # it as input, focus moves to the QListView, NVDA announces naturally.
            api.setNavigatorObject(target)
            _mouseClickAt(target)
            return

        try:
            target.setFocus()
        except Exception as e:
            log.info(f"OBS jump: setFocus error for {friendlyName}: {e}")

        if target.role == controlTypes.Role.COMBOBOX and not alreadyFocused:
            # Qt's QComboBox doesn't accept programmatic UIA SetFocus reliably
            # (silently no-ops, like LISTITEM). Mouse-click forces real focus,
            # opening the dropdown as a side effect; UIA ExpandCollapsePattern
            # collapses the dropdown reliably (sending Escape can race with
            # Qt's popup rendering and leave the popup capturing input).
            if _mouseClickAt(target):
                _collapseCombobox(target)
        elif alreadyFocused:
            # Focus didn't change, so NVDA won't fire a focus event. Speak
            # the target manually so the gesture always gives audible feedback.
            try:
                speech.speakObject(target)
            except Exception as e:
                log.info(f"OBS jump: speakObject failed: {e}")
                ui.message(target.name or "")

    @script(
        description="Announce that the OBS accessibility add-on is loaded",
        gesture="kb:NVDA+shift+o",
    )
    def script_announceAddonLoaded(self, gesture):
        ui.message(
            f"OBS accessibility add-on loaded, version {ADDON_VERSION}"
        )

    @script(
        description=(
            "Inspect the navigator (and focused) OBS object — writes detailed "
            "info to the NVDA log. Development tool."
        ),
        gesture="kb:NVDA+shift+i",
    )
    def script_inspect(self, gesture):
        focus = api.getFocusObject()
        nav = api.getNavigatorObject()
        log.info("\n".join(_dumpObject("focus", focus)))
        if nav is not focus:
            log.info("\n".join(_dumpObject("navigator", nav)))
            target = nav
        else:
            target = focus
        ui.message(
            f"Inspected: {target.name or 'unnamed'}, role {target.role}. "
            "Details written to NVDA log."
        )

    @script(
        description="Jump focus to the OBS Scenes list",
        gesture="kb:NVDA+shift+1",
    )
    def script_jumpToScenes(self, gesture):
        self._jumpTo(".scenesDock.", "Scenes", role=controlTypes.Role.LISTITEM)

    @script(
        description="Jump focus to the OBS Sources list",
        gesture="kb:NVDA+shift+2",
    )
    def script_jumpToSources(self, gesture):
        self._jumpTo(".sourcesDock.", "Sources", role=controlTypes.Role.LISTITEM)

    @script(
        description="Jump focus to the OBS Audio Mixer (volume sliders)",
        gesture="kb:NVDA+shift+3",
    )
    def script_jumpToMixer(self, gesture):
        self._jumpTo(".mixerDock.", "Audio Mixer", role=controlTypes.Role.SLIDER)

    @script(
        description=(
            "Jump focus to the OBS Controls panel "
            "(Start Streaming, Recording, Virtual Camera)"
        ),
        gesture="kb:NVDA+shift+4",
    )
    def script_jumpToControls(self, gesture):
        self._jumpTo(".controlsDock.", "Controls", role=controlTypes.Role.BUTTON)

    @script(
        description="Jump focus to the OBS Scene Transitions",
        gesture="kb:NVDA+shift+5",
    )
    def script_jumpToTransitions(self, gesture):
        self._jumpTo(
            ".transitionsDock.", "Scene Transitions",
            role=controlTypes.Role.COMBOBOX,
        )

    @script(
        description="Jump focus to the OBS preview controls (zoom, scaling)",
        gesture="kb:NVDA+shift+6",
    )
    def script_jumpToPreview(self, gesture):
        self._jumpTo(
            ".previewContainer.", "Preview controls",
            role=controlTypes.Role.BUTTON,
        )

    def _stepHotkeyRow(self, direction):
        rows = _findHotkeyRows()
        if not rows:
            ui.message("Not on the OBS Hotkeys settings page")
            return
        current = _findCurrentHotkeyWidget()
        if current is None:
            target = rows[0] if direction > 0 else rows[-1]
        else:
            curName = _rowName(current)
            idx = -1
            for i, row in enumerate(rows):
                if _rowName(row) == curName:
                    idx = i
                    break
            if idx < 0:
                target = rows[0]
            else:
                newIdx = idx + direction
                if newIdx < 0:
                    ui.message("Beginning of hotkey list")
                    return
                if newIdx >= len(rows):
                    ui.message("End of hotkey list")
                    return
                target = rows[newIdx]
        if not _focusHotkeyRowEdit(target):
            ui.message("Could not focus row's binding edit")

    @script(
        description=(
            "Move to the next hotkey row in OBS Settings, Hotkeys page, "
            "and focus its binding edit"
        ),
        gesture="kb:NVDA+alt+downArrow",
    )
    def script_nextHotkeyRow(self, gesture):
        self._stepHotkeyRow(direction=1)

    @script(
        description=(
            "Move to the previous hotkey row in OBS Settings, Hotkeys page, "
            "and focus its binding edit"
        ),
        gesture="kb:NVDA+alt+upArrow",
    )
    def script_prevHotkeyRow(self, gesture):
        self._stepHotkeyRow(direction=-1)

    @script(
        description=(
            "Jump to the first hotkey row in OBS Settings, Hotkeys page"
        ),
        gesture="kb:NVDA+alt+home",
    )
    def script_firstHotkeyRow(self, gesture):
        rows = _findHotkeyRows()
        if not rows:
            ui.message("Not on the OBS Hotkeys settings page")
            return
        if not _focusHotkeyRowEdit(rows[0]):
            ui.message("Could not focus first row")

    @script(
        description=(
            "Jump to the last hotkey row in OBS Settings, Hotkeys page"
        ),
        gesture="kb:NVDA+alt+end",
    )
    def script_lastHotkeyRow(self, gesture):
        rows = _findHotkeyRows()
        if not rows:
            ui.message("Not on the OBS Hotkeys settings page")
            return
        if not _focusHotkeyRowEdit(rows[-1]):
            ui.message("Could not focus last row")

    def _clickSettingsButton(self, buttonName, friendlyAction):
        elem = _findSettingsButton(buttonName)
        if elem is None:
            ui.message(f"{buttonName}: Settings dialog not open")
            return
        if _invokeUIAElement(elem):
            ui.message(f"Settings {friendlyAction}")
            return
        try:
            elem.SetFocus()
            ui.message(
                f"{buttonName} button focused — press Enter to {friendlyAction}"
            )
        except Exception:
            ui.message(f"Could not activate {buttonName}")

    @script(
        description="Click OK in the OBS Settings dialog (commit and close)",
        gesture="kb:NVDA+alt+o",
    )
    def script_settingsOK(self, gesture):
        self._clickSettingsButton("OK", "saved and closed")

    @script(
        description=(
            "Click Apply in the OBS Settings dialog "
            "(commit changes, leave dialog open)"
        ),
        gesture="kb:NVDA+alt+a",
    )
    def script_settingsApply(self, gesture):
        self._clickSettingsButton("Apply", "applied")

    @script(
        description="Click Cancel in the OBS Settings dialog (discard and close)",
        gesture="kb:NVDA+alt+c",
    )
    def script_settingsCancel(self, gesture):
        self._clickSettingsButton("Cancel", "cancelled")

    @script(
        description=(
            "Click Defaults in the OBS Settings dialog "
            "(restore defaults for the current page)"
        ),
        gesture="kb:NVDA+alt+d",
    )
    def script_settingsDefaults(self, gesture):
        self._clickSettingsButton("Defaults", "reset to defaults")

    @script(
        description="Open the OBS Settings dialog",
        gesture="kb:NVDA+alt+i",
    )
    def script_openSettings(self, gesture):
        elem = _findControlButton(".settingsButton")
        if elem is None:
            ui.message("Settings button not found")
            return
        if not _invokeUIAElement(elem):
            ui.message("Could not open Settings")

    @script(
        description="Toggle Start/Stop Streaming",
        gesture="kb:NVDA+alt+s",
    )
    def script_toggleStreaming(self, gesture):
        _toggleControlButton(".streamButton", "Streaming button not found")

    @script(
        description="Toggle Start/Stop Recording",
        gesture="kb:NVDA+alt+r",
    )
    def script_toggleRecording(self, gesture):
        _toggleControlButton(".recordButton", "Recording button not found")

    @script(
        description=(
            "Toggle Pause/Unpause Recording (only available while recording)"
        ),
        gesture="kb:NVDA+alt+p",
    )
    def script_togglePause(self, gesture):
        _toggleControlButton(
            ".pauseRecordButton",
            "Pause not available — start a recording first",
        )

    @script(
        description="Toggle Start/Stop Virtual Camera",
        gesture="kb:NVDA+alt+v",
    )
    def script_toggleVirtualCam(self, gesture):
        _toggleControlButton(
            ".virtualCamButton", "Virtual camera button not found"
        )
