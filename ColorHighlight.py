from __future__ import absolute_import

import re
import os
import time
import zlib
import math
import struct
import threading
import colorsys
from functools import partial

import sublime
import sublime_plugin

from .settings import Settings, SettingTogglerCommandMixin
from .colorizer import SchemaColorizer, all_names_to_hex, names_to_hex, xterm_to_hex, xterm8_to_hex, xterm8b_to_hex, xterm8f_to_hex

NAME = "ColorHighlight"
VERSION = "1.0.7"


# Color formats:
# #000000FF
# #FFFFFF
# #FFF7
# #FFF
# rgb(255,255,255)
# rgba(255, 255, 255, 1)
# rgba(255, 255, 255, .2)
# rgba(255, 255, 255, 0.5)
# black
# rgba(white, 20%)
# 0xFFFFFF
# hsl(360, 0%, 50%)
# hsla(360, 0%, 50%, 0.5)
# hwb(360, 50%, 50%)
# lab(100, 100, 100) <-> #ff9331
# lch(100, 100, 100) <-> #ffff00
# hsv(40, 70%, 100%) <-> #ffc34d
# \033[31m
# \033[38;5;22m
# \033[38;2;0;0;255m

def regexp_factory(names):
    _COLORS = r'(?<![-.\w])%s(?![-.\w])' % r'(?![-.\w])|(?<![-.\w])'.join(names.keys())

    _ALL_HEX_COLORS = r'%s|%s' % (_COLORS, r'(?:#|0x)[0-9a-fA-F]{8}\b|(?:#|0x)[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b|(?:\x1b|\\033|\\x1b)\[(?:\d{1,3}(?:;\d{1,3})*m)')
    _ALL_HEX_COLORS = r'%s|%s' % (
        r'(rgba|rgb|hsva|hsv|hsla|hsl|hwb|lab|lch)\((?:([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?)|(%s))(?:,\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?))?\)' % _ALL_HEX_COLORS,
        r'(%s)' % _ALL_HEX_COLORS,
    )
    _ALL_HEX_COLORS_CAPTURE = r'\1|\2\5\7,\3,\4,\6'

    _XHEX_COLORS = r'%s|%s' % (_COLORS, r'0x[0-9a-fA-F]{8}\b|0x[0-9a-fA-F]{6}\b')
    _XHEX_COLORS = r'%s|%s' % (
        r'(rgba|rgb|hsva|hsv|hsla|hsl|hwb|lab|lch)\((?:([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?)|(%s))(?:,\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?))?\)' % _XHEX_COLORS,
        r'(%s)' % _XHEX_COLORS,
    )
    _XHEX_COLORS_CAPTURE = r'\1|\2\5\7,\3,\4,\6'

    _HEX_COLORS = r'%s|%s' % (_COLORS, r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b')
    _HEX_COLORS = r'%s|%s' % (
        r'(rgba|rgb|hsva|hsv|hsla|hsl|hwb|lab|lch)\((?:([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?)|(%s))(?:,\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?))?\)' % _HEX_COLORS,
        r'(%s)' % _HEX_COLORS,
    )
    _HEX_COLORS_CAPTURE = r'\1|\2\5\7,\3,\4,\6'

    _NO_HEX_COLORS = r'%s' % (_COLORS,)
    _NO_HEX_COLORS = r'%s|%s' % (
        r'(rgba|rgb|hsva|hsv|hsla|hsl|hwb|lab|lch)\((?:([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?),\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?)|(%s))(?:,\s*([-+]?(?:[0-9]*\.\d+|[0-9]+)(?:%%|deg)?))?\)' % _NO_HEX_COLORS,
        r'(%s)' % _NO_HEX_COLORS,
    )
    _NO_HEX_COLORS_CAPTURE = r'\1|\2\5\7,\3,\4,\6'

    return (
        _NO_HEX_COLORS,
        _NO_HEX_COLORS_CAPTURE,
        _XHEX_COLORS,
        _XHEX_COLORS_CAPTURE,
        _HEX_COLORS,
        _HEX_COLORS_CAPTURE,
        _ALL_HEX_COLORS,
        _ALL_HEX_COLORS_CAPTURE,
    )


_NO_HEX_COLORS, _NO_HEX_COLORS_CAPTURE, _XHEX_COLORS, _XHEX_COLORS_CAPTURE, _HEX_COLORS, _HEX_COLORS_CAPTURE, _ALL_HEX_COLORS, _ALL_HEX_COLORS_CAPTURE = regexp_factory(names_to_hex)
COLORS_REGEX = {
    (False, False): (_NO_HEX_COLORS, _NO_HEX_COLORS_CAPTURE,),
    (False, True): (_XHEX_COLORS, _XHEX_COLORS_CAPTURE),
    (True, False): (_HEX_COLORS, _HEX_COLORS_CAPTURE),
    (True, True): (_ALL_HEX_COLORS, _ALL_HEX_COLORS_CAPTURE),
}

_R_RE = re.compile(r'\\([0-9])')
COLORS_RE = dict((k, (re.compile(v[0]), _R_RE.sub(lambda m: chr(int(m.group(1))), v[1]))) for k, v in COLORS_REGEX.items())


def hsv_to_rgb(h, s, v):
    # h -> [0, 360)
    # s -> [0, 100]
    # l -> [0, 100]

    H = h / 360.0
    S = s / 100.0
    V = v / 100.0

    RR, GG, BB = colorsys.hsv_to_rgb(H, S, V)
    return int(RR * 255), int(GG * 255), int(BB * 255)


def hsl_to_rgb(h, s, l):
    # h -> [0, 360)
    # s -> [0, 100]
    # l -> [0, 100]

    H = h / 360.0
    S = s / 100.0
    L = l / 100.0

    RR, GG, BB = colorsys.hls_to_rgb(H, L, S)
    return int(RR * 255), int(GG * 255), int(BB * 255)


def hwb_to_rgb(h, w, b):
    # h -> [0, 360)
    # w -> [0, 100]
    # b -> [0, 100]
    H = h / 360.0
    W = w / 100.0
    B = b / 100.0

    RR, GG, BB = colorsys.hls_to_rgb(H, 0.5, 1)
    RR = RR * (1 - W - B) + W
    GG = GG * (1 - W - B) + W
    BB = BB * (1 - W - B) + W

    r, g, b = int(RR * 255), int(GG * 255), int(BB * 255)
    r = 0 if r < 0 else 255 if r > 255 else r
    g = 0 if g < 0 else 255 if g > 255 else g
    b = 0 if b < 0 else 255 if b > 255 else b
    return r, g, b


def lab_to_rgb(L, a, b):
    # L -> [0, 100]
    # a -> [-160, 160]
    # b -> [-160, 160]

    Y = (L + 16.0) / 116.0
    X = a / 500.0 + Y
    Z = Y - b / 200.0

    Y3 = Y ** 3.0
    Y = Y3 if Y3 > 0.008856 else (Y - 16.0 / 116.0) / 7.787

    X3 = X ** 3.0
    X = X3 if X3 > 0.008856 else (X - 16.0 / 116.0) / 7.787

    Z3 = Z ** 3.0
    Z = Z3 if Z3 > 0.008856 else (Z - 16.0 / 116.0) / 7.787

    # Normalize white point for Observer=2°, Illuminant=D65
    X *= 0.95047
    Y *= 1.0
    Z *= 1.08883

    # XYZ to RGB
    RR = X * 3.240479 + Y * -1.537150 + Z * - 0.498535
    GG = X * -0.969256 + Y * 1.875992 + Z * 0.041556
    BB = X * 0.055648 + Y * -0.204043 + Z * 1.057311

    RR = 1.055 * RR ** (1 / 2.4) - 0.055 if RR > 0.0031308 else 12.92 * RR
    GG = 1.055 * GG ** (1 / 2.4) - 0.055 if GG > 0.0031308 else 12.92 * GG
    BB = 1.055 * BB ** (1 / 2.4) - 0.055 if BB > 0.0031308 else 12.92 * BB

    r, g, b = int(RR * 255), int(GG * 255), int(BB * 255)
    r = 0 if r < 0 else 255 if r > 255 else r
    g = 0 if g < 0 else 255 if g > 255 else g
    b = 0 if b < 0 else 255 if b > 255 else b
    return r, g, b


def lch_to_lab(L, c, h):
    # L -> [0, 100]
    # c -> [0, 230]
    # h -> [0, 360)
    a = c * math.cos(math.radians(h))
    b = c * math.sin(math.radians(h))
    return L, a, b


def lch_to_rgb(L, c, h):
    L, a, b = lch_to_lab(L, c, h)
    return lab_to_rgb(L, a, b)


def tohex(r, g, b, a):
    if g is not None and b is not None:
        sr = '%X' % r
        if len(sr) == 1:
            sr = '0' + sr
        sg = '%X' % g
        if len(sg) == 1:
            sg = '0' + sg
        sb = '%X' % b
        if len(sb) == 1:
            sb = '0' + sb
    else:
        sr = r[1:3]
        sg = r[3:5]
        sb = r[5:7]
    sa = '%X' % int(a / 100.0 * 255)
    if len(sa) == 1:
        sa = '0' + sa
    return '#%s%s%s%s' % (sr, sg, sb, sa)


PNG_RE = re.compile(rb'\x1f\x2f\x3f|\x4f\x5f\x6f')  # noqa: E999
PNG_HEAD = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00 \x00\x00\x00 \x08\x06\x00\x00\x00szz\xf4'
PNG_DATA = zlib.decompress(b'x\x9c\xed\xd6\xc1\r\xc3 \x0c@QX!g\xa4\x8c\xd0\x11:BF\xe8\x01q\xee\x1c\xdd\x82e2\x00\xb30\x00\xb5U#U\x11\x85`\xac\xe6\xc2\xe1_\xc3K\x93\xd8U)%ue\x97\x1e>\x01\x13P\x05\xac\xb7{)\x03Y\xc8C\x01\x8a\xdb\xe3\x89\x05\xc8C\x162\x90:6\n\xd0\x90\x83v(}\x07\x17?\xb6C\x0e\xd2R\x80\x05z\x1d\x0f\xae\x00r/h\x19\x05\xe8\xda\xe1\r@F\xe8\x11\x80\xab\x1d~\x02\x90\xe8q\xb0\x00\xa6\xf4\xcc\x19\x00|\'\x0c\x07`[\x87\x9f\x04`\x96\x03\xf0\x82\x00\xcf\x01\x04A@\xe0\x00\xa2  v\x03h\xc25/~\x06\x897\xc3\x01\x04A@\xff#\xa0\xd9.\x05\xe8\x7f\ti\xb1H\x01\xfa?\xc3\xed\xb3\xd5v\x01\x00\x0e\xb3\xfeADK\xc4\t\x00p\x9c\xf7\x8fb\x02hZ(\\\x00.2=\x02\xc0\x96\x1a\xa2q8\xaer5\n\xc8\xbf\x84+\xbd\x13?\x9e\xb9\xcbw.\x05\xc8\x19\xfa:<\xcd\x89H\x133\xd0\xee\xc0\x05f\xd6\xc2\xdf\xb9n\xc0\xbf\x9a\x80\t\xb8\x1c\xf0\x06-\x9f\xcd\xf4')
PNG_END = b'\x00\x00\x00\x00IEND\xaeB`\x82'


def toicon(name, light=True):
    base_path = os.path.join(sublime.packages_path(), 'User', '%s.cache' % NAME)
    if not os.path.exists(base_path):
        os.mkdir(base_path)
    icon_path = os.path.join(base_path, name + '.png')
    if not os.path.exists(icon_path):
        r = int(name[4:6], 16)
        g = int(name[6:8], 16)
        b = int(name[8:10], 16)
        a = int(name[10:12] or 'ff', 16) / 255.0
        # print("r={} g={} b={} a={}".format(r, g, b, a))
        if light:
            x = 0xff * (1 - a)
            y = 0xcc * (1 - a)
        else:
            x = 0x99 * (1 - a)
            y = 0x66 * (1 - a)
        r *= a
        g *= a
        b *= a
        # print("x(r={} g={} b={}), y(r={} g={} b={})".format(int(r + x), int(g + x), int(b + x), int(r + y), int(g + y), int(b + y)))
        I1 = lambda v: struct.pack("!B", v & (2**8 - 1))
        I4 = lambda v: struct.pack("!I", v & (2**32 - 1))
        png = PNG_HEAD
        col_map = {
            b'\x1f\x2f\x3f': I1(int(r + x)) + I1(int(g + x)) + I1(int(b + x)),
            b'\x4f\x5f\x6f': I1(int(r + y)) + I1(int(g + y)) + I1(int(b + y)),
        }
        data = PNG_RE.sub(lambda m: col_map[m.group(0)], PNG_DATA)
        compressed = zlib.compress(data)
        idat = b'IDAT' + compressed
        png += I4(len(compressed)) + idat + I4(zlib.crc32(idat))
        png += PNG_END
        with open(icon_path, 'wb') as fp:
            fp.write(png)
    relative_icon_path = os.path.relpath(icon_path, os.path.dirname(sublime.packages_path()))
    return relative_icon_path


# Commands

# treat hex vals as colors
class ColorHighlightCommand(sublime_plugin.WindowCommand):
    def run_(self, edit_token, args={}):
        view = self.window.active_view()
        view.run_command('color_highlight', args)

    def is_enabled(self):
        return True


class ColorHighlightEnableLoadSaveCommand(ColorHighlightCommand):
    def is_enabled(self):
        enabled = super(ColorHighlightEnableLoadSaveCommand, self).is_enabled()

        if enabled:
            if settings.get('highlight') == 'load-save':
                return False

        return enabled


class ColorHighlightEnableSaveOnlyCommand(ColorHighlightCommand):
    def is_enabled(self):
        enabled = super(ColorHighlightEnableSaveOnlyCommand, self).is_enabled()

        if enabled:
            if settings.get('highlight') == 'save-only':
                return False

        return enabled


class ColorHighlightDisableCommand(ColorHighlightCommand):
    def is_enabled(self):
        enabled = super(ColorHighlightDisableCommand, self).is_enabled()

        if enabled:
            if settings.get('highlight') is False:
                return False

        return enabled


class ColorHighlightEnableCommand(ColorHighlightCommand):
    def is_enabled(self):
        view = self.window.active_view()

        if view:
            if settings.get('highlight') is not False:
                return False

        return True


# treat hex vals as colors
class ColorHighlightHexValsAsColorsCommand(ColorHighlightCommand):
    def is_enabled(self):
        enabled = super(ColorHighlightHexValsAsColorsCommand, self).is_enabled()

        if enabled:
            if settings.get('hex_values') is False:
                return False

        return enabled
    is_checked = is_enabled


# treat hex vals as colors
class ColorHighlightXHexValsAsColorsCommand(ColorHighlightCommand):
    def is_enabled(self):
        enabled = super(ColorHighlightXHexValsAsColorsCommand, self).is_enabled()

        if enabled:
            if settings.get('0x_hex_values') is False:
                return False

        return enabled
    is_checked = is_enabled


# command to restore color scheme
class ColorHighlightRestoreCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        erase_highlight_colors()
        colorizer.restore_color_scheme()


all_regs = []


class ColorHighlightCommand(sublime_plugin.TextCommand):
    '''command to interact with linters'''

    def __init__(self, view):
        self.view = view
        self.help_called = False

    def run_(self, edit_token, args={}):
        '''method called by default via view.run_command;
           used to dispatch to appropriate method'''

        action = args.get('action', '')
        if not action:
            return

        lc_action = action.lower()

        if lc_action == 'reset':
            self.reset()
        elif lc_action == 'off':
            self.off()
        elif lc_action == 'on':
            self.on()
        elif lc_action == 'load-save':
            self.enable_load_save()
        elif lc_action == 'save-only':
            self.enable_save_only()
        elif lc_action == 'hex':
            self.toggle_hex_values()
        elif lc_action == 'xhex':
            self.toggle_xhex_values()
        else:
            highlight_colors(self.view)

    def toggle_hex_values(self):
        settings.set('hex_values', not settings.get('hex_values'), changed=True)
        settings.save()
        queue_highlight_colors(self.view, preemptive=True)

    def toggle_xhex_values(self):
        settings.set('0x_hex_values', not settings.get('0x_hex_values'), changed=True)
        settings.save()
        queue_highlight_colors(self.view, preemptive=True)

    def reset(self):
        '''Removes existing lint marks and restores user settings.'''
        erase_highlight_colors()
        colorizer.setup_color_scheme(self.view.settings())
        queue_highlight_colors(self.view, preemptive=True)

    def on(self):
        '''Turns background linting on.'''
        settings.set('highlight', True)
        settings.save()
        queue_highlight_colors(self.view, preemptive=True)

    def enable_load_save(self):
        '''Turns load-save linting on.'''
        settings.set('highlight', 'load-save')
        settings.save()
        erase_highlight_colors()

    def enable_save_only(self):
        '''Turns save-only linting on.'''
        settings.set('highlight', 'save-only')
        settings.save()
        erase_highlight_colors()

    def off(self):
        '''Turns background linting off.'''
        settings.set('highlight', False)
        settings.save()
        erase_highlight_colors()


class ColorHighlightViewEventListener(sublime_plugin.ViewEventListener):
    def on_modified(self):
        if settings.get('highlight') is not True:
            return

        action = self.view.command_history(0, True)[0]
        if action == 'revert':
            erase_highlight_colors()
            queue_highlight_colors(self.view, preemptive=True)
        else:
            selection = action != 'paste'
            queue_highlight_colors(self.view, selection=selection)

    def on_close(self):
        vid = self.view.id()
        if vid in TIMES:
            del TIMES[vid]
        if vid in COLOR_HIGHLIGHTS:
            del COLOR_HIGHLIGHTS[vid]

    def on_activated(self):
        if self.view.file_name() is None:
            return
        vid = self.view.id()
        if vid in TIMES:
            return
        TIMES[vid] = 100

        if settings.get('highlight') in (False, 'save-only'):
            return

        queue_highlight_colors(self.view, preemptive=True, event='on_activated')

    def on_post_save(self):
        if settings.get('highlight') is False:
            return

        queue_highlight_colors(self.view, preemptive=True, event='on_post_save')

    def on_selection_modified(self):
        delay_queue(1000)  # on movement, delay queue (to make movement responsive)


TIMES = {}       # collects how long it took the color highlight to complete
COLOR_HIGHLIGHTS = {}  # Highlighted regions


def erase_highlight_colors(view=None):
    if view:
        vid = view.id()
        if vid in COLOR_HIGHLIGHTS:
            for name in COLOR_HIGHLIGHTS[vid]:
                view.erase_regions(name)
                view.erase_regions(name + '_icon')
        COLOR_HIGHLIGHTS[vid] = set()
    else:
        for window in sublime.windows():
            for view in window.views():
                erase_highlight_colors(view)


def highlight_colors(view, selection=False, **kwargs):
    view_settings = view.settings()
    colorizer.setup_color_scheme(view_settings)

    vid = view.id()
    start = time.time()

    if len(view.sel()) > 100:
        selection = False

    words = {}
    found = []
    _hex_values = bool(settings.get('hex_values'))
    _xhex_values = bool(settings.get('0x_hex_values'))
    _xterm_color_values = bool(settings.get('xterm_color_values'))
    if selection:
        colors_re, colors_re_capture = COLORS_RE[
            (_hex_values, _xhex_values)
        ]
        selected_lines = list(ln for r in view.sel() for ln in view.lines(r))
        matches = [colors_re.finditer(view.substr(l)) for l in selected_lines]
        matches = [
            (
                sublime.Region(
                    selected_lines[i].begin() + m.start(),
                    selected_lines[i].begin() + m.end()
                ),
                m.groups()
            ) if m else (None, None)
            for i, am in enumerate(matches) for m in am
        ]
        matches = [
            (
                rg,
                ''.join(
                    gr[ord(g) - 1] or '' if ord(g) < 10 else g for g in colors_re_capture
                )
            )
            for rg, gr in matches if rg
        ]
        if matches:
            ranges, found = zip(*[q for q in matches if q])
        else:
            ranges = []
    else:
        selected_lines = None
        colors_re, colors_re_capture = COLORS_REGEX[(_hex_values, _xhex_values)]
        ranges = view.find_all(colors_re, 0, colors_re_capture, found)

    for i, col in enumerate(found):
        mode, _, col = col.partition('|')
        col = col.rstrip(',')
        col = col.split(',')
        try:
            if mode in ('hsl', 'hsla', 'hsv', 'hsva', 'hwb'):
                if len(col) > 2 and col[0] and col[1] and col[2]:
                    # In the form of hsl(360, 100%, 100%) or hsla(360, 100%, 100%, 1.0) or hwb(360, 50%, 50%):
                    if col[0].endswith('deg'):
                        col[0] = col[0][:-3]
                    h = float(col[0]) % 360
                    if col[1].endswith('%'):
                        sb = float(col[1][:-1])
                    else:
                        sb = float(col[1]) * 100.0
                    if sb < 0 or sb > 100:
                        raise ValueError("sb out of range")
                    if col[2].endswith('%'):
                        lwv = float(col[2][:-1])
                    else:
                        lwv = float(col[2]) * 100.0
                    if lwv < 0 or lwv > 100:
                        raise ValueError("lwv out of range")
                    if mode == 'hwb':
                        if sb + lwv > 100:
                            raise ValueError("sb + lwv > 100")
                    if len(col) == 4:
                        if mode in ('hsl', 'hsv'):
                            raise ValueError("hsl/hsv should not have alpha")
                        if col[3].endswith('%'):
                            alpha = float(col[3][:-1])
                        else:
                            alpha = float(col[3]) * 100.0
                        if alpha < 0 or alpha > 100:
                            raise ValueError("alpha out of range")
                    elif mode in ('hsla', 'hsva'):
                        continue
                    else:
                        alpha = 100.0
                    if mode in ('hsl', 'hsla'):
                        r, g, b = hsl_to_rgb(h, sb, lwv)
                    elif mode in ('hsv', 'hsva'):
                        r, g, b = hsv_to_rgb(h, sb, lwv)
                    else:
                        r, g, b = hwb_to_rgb(h, sb, lwv)
                    col = tohex(r, g, b, alpha)
                else:
                    raise ValueError("invalid hsl/hsla/hwb")
            elif mode == 'lab':
                # The first argument specifies the CIE Lightness, the second
                # argument is a and the third is b. L is constrained to the
                # range [0, 100] while a and b are signed values and
                # theoretically unbounded (but in practice do not exceed ±160).
                # There is an optional fourth alpha value separated by a comma.
                if len(col) > 2 and col[0] and col[1] and col[2]:
                    # In the form of lab(100, 0, 0) or lab(100, 0, 0, 1.0):
                    # lab(100, 0, 127) <-> rgb(255, 250, 0)
                    L = float(col[0])
                    if L < 0 or L > 100:
                        raise ValueError("L out of range")
                    a = float(col[1])
                    b = float(col[2])
                    if len(col) == 4:
                        if col[3].endswith('%'):
                            alpha = float(col[3][:-1])
                        else:
                            alpha = float(col[3]) * 100.0
                        if alpha < 0 or alpha > 100:
                            raise ValueError("alpha out of range")
                    else:
                        alpha = 100.0
                    r, g, b = lab_to_rgb(L, a, b)
                    col = tohex(r, g, b, alpha)
                else:
                    raise ValueError("invalid lab")
            elif mode == 'lch':
                # The first argument specifies the CIE Lightness, the second
                # argument is C and the third is H. L is constrained to the
                # range [0, 100]. C is an unsigned number, theoretically
                # unbounded (but in practice does not exceed 230). H is
                # constrained to the range [0, 360). There is an optional
                # fourth alpha value separated by a comma.
                if len(col) > 2 and col[0] and col[1] and col[2]:
                    # In the form of lch(0, 250, 360) or lch(100, 100, 360, 1.0):
                    L = float(col[0])
                    if L < 0 or L > 100:
                        raise ValueError("L out of range")
                    c = float(col[1])
                    if c < 0:
                        raise ValueError("c out of range")
                    if col[2].endswith('deg'):
                        col[2] = col[2][:-3]
                    h = float(col[2]) % 360
                    if len(col) == 4:
                        if col[3].endswith('%'):
                            alpha = float(col[3][:-1])
                        else:
                            alpha = float(col[3]) * 100.0
                        if alpha < 0 or alpha > 100:
                            raise ValueError("alpha out of range")
                    else:
                        alpha = 100.0
                    r, g, b = lch_to_rgb(L, c, h)
                    col = tohex(r, g, b, alpha)
                else:
                    raise ValueError("invalid lch")
            elif len(col) == 1:
                # In the form of: black, #FFFFFFFF, 0xFFFFFF, \033[1;37m, \033[38;5;255m, \033[38;2;255;255;255m:
                col0 = col[0]
                if col0.endswith('m') and '[' in col0:
                    _, _, col0 = col0[:-1].partition('[')
                    col0 = ';' + col0 + ';'
                    col0 = re.sub(r';0*(?=\d)', r';', col0)
                    xterm_true = col0.find(';38;2;')
                    xterm = col0.find(';38;5;')
                    if xterm_true != -1:
                        col = col0[xterm_true + 6:-1].split(';')
                        r = int(col[0])
                        g = int(col[1])
                        b = int(col[2])
                        if (r < 0 or r > 255) or (g < 0 or g > 255) or (b < 0 or b > 255):
                            raise ValueError("rgb out of range")
                        col = tohex(r, g, b, 100.0)
                    elif xterm != -1:
                        col = col0[xterm + 6:-1].split(';')[0]
                        col = xterm_to_hex.get(col)
                        if not col:
                            continue
                    else:
                        mode = xterm8_to_hex
                        modes = (xterm8_to_hex, xterm8b_to_hex, xterm8f_to_hex)
                        q = -1
                        for m in (0, 1, 2):
                            p = col0.find(';%s;' % m)
                            if p != -1 and p > q:
                                mode = modes[m]
                        xterm8 = col0[1:-1].split(';')
                        col = None
                        for x in xterm8:
                            if x in mode:
                                col = mode[x]
                        if not col:
                            continue
                else:
                    if col0.startswith('0x'):
                        col0 = '#' + col0[2:]
                    else:
                        col0 = all_names_to_hex.get(col0.lower(), col0.upper())
                    if len(col0) == 4:
                        col0 = '#' + col0[1] * 2 + col0[2] * 2 + col0[3] * 2 + 'FF'
                    elif len(col0) == 7:
                        col0 += 'FF'
                    col = col0
            elif col[1] and col[2]:
                # In the form of rgb(255, 255, 255) or rgba(255, 255, 255, 1.0):
                r = int(col[0])
                g = int(col[1])
                b = int(col[2])
                if (r < 0 or r > 255) or (g < 0 or g > 255) or (b < 0 or b > 255):
                    raise ValueError("rgb out of range")
                if len(col) == 4:
                    if col[3].endswith('%'):
                        alpha = float(col[3][:-1])
                    else:
                        alpha = float(col[3]) * 100.0
                    if alpha < 0 or alpha > 100:
                        raise ValueError("alpha out of range")
                else:
                    alpha = 100.0
                col = tohex(r, g, b, alpha)
            else:
                # In the form of rgba(white, 20%) or rgba(#FFFFFF, 0.4):
                col0 = col[0]
                col0 = all_names_to_hex.get(col0.lower(), col0.upper())
                if col0.startswith('0X'):
                    col0 = '#' + col0[2:]
                if len(col0) == 4:
                    col0 = '#' + col0[1] * 2 + col0[2] * 2 + col0[3] * 2 + 'FF'
                elif len(col0) == 7:
                    col0 += 'FF'
                if len(col) == 4:
                    col3 = col[3]
                    if col3.endswith('%'):
                        alpha = float(col3[:-1])
                    else:
                        alpha = float(col3) * 100.0
                    if alpha < 0 or alpha > 100:
                        raise ValueError("alpha out of range")
                else:
                    alpha = 100.0
                col = tohex(col0, None, None, alpha)
        except (ValueError, IndexError, KeyError) as e:
            # print(e)
            continue

        # Fix case when color it's the same as background color:
        if hasattr(view, 'style'):
            bg_col = (view.style()['background'] + 'FF')[:9].upper()
            if col == bg_col:
                br = int(bg_col[1:3], 16)
                bg = int(bg_col[3:5], 16)
                bb = int(bg_col[5:7], 16)
                ba = int(bg_col[7:9], 16)
                br += -1 if br > 1 else 1
                bg += -1 if bg > 1 else 1
                bb += -1 if bb > 1 else 1
                col = '#%02X%02X%02X%02X' % (br, bg, bb, ba)

        name = colorizer.add_color(col)
        if name not in words:
            words[name] = [ranges[i]]
        else:
            words[name].append(ranges[i])

    colorizer.update(view)

    if selection:
        if vid not in COLOR_HIGHLIGHTS:
            COLOR_HIGHLIGHTS[vid] = set()
        for name in COLOR_HIGHLIGHTS[vid]:
            ranges = []
            affected_line = False
            for _range in view.get_regions(name):
                _line_range = False
                for _line in selected_lines:
                    if _line.contains(_range):
                        _line_range = True
                        break
                if _line_range:
                    affected_line = True
                else:
                    ranges.append(_range)
            if affected_line or name in words:
                if name not in words:
                    words[name] = ranges
                else:
                    words[name].extend(ranges)
    else:
        erase_highlight_colors(view)
    all_regs = COLOR_HIGHLIGHTS[vid]

    for name, w in words.items():
        view.add_regions(name, w, name, flags=sublime.PERSISTENT)
        wi = [sublime.Region(i, i) for i in set(view.line(r).a for r in w)]
        view.add_regions(name + '_icon', wi, '%sgutter' % colorizer.prefix, icon=toicon(name), flags=sublime.PERSISTENT)
        all_regs.add(name)

    TIMES[vid] = (time.time() - start) * 1000  # Keep how long it took to color highlight
    # print('highlight took %s' % TIMES[vid])


################################################################################
# Queue connection

QUEUE = {}       # views waiting to be processed by ColorHighlight

# For snappier color highlighting, different delays are used for different color highlighting times:
# (color highlighting time, delays)
DELAYS = (
    (50, (50, 100)),
    (100, (100, 300)),
    (200, (200, 500)),
    (400, (400, 1000)),
    (800, (800, 2000)),
    (1600, (1600, 3000)),
)


def get_delay(t, view):
    delay = 0

    for _t, d in DELAYS:
        if _t <= t:
            delay = d
        else:
            break

    delay = delay or DELAYS[0][1]

    # If the user specifies a delay greater than the built in delay,
    # figure they only want to see marks when idle.
    minDelay = int(settings.get('delay', 0) * 1000)

    return (minDelay, minDelay) if minDelay > delay[1] else delay


def _update_view(view, filename, **kwargs):
    # It is possible that by the time the queue is run,
    # the original file is no longer being displayed in the view,
    # or the view may be gone. This happens especially when
    # viewing files temporarily by single-clicking on a filename
    # in the sidebar or when selecting a file through the choose file palette.
    valid_view = False
    view_id = view.id()

    for window in sublime.windows():
        for v in window.views():
            if v.id() == view_id:
                valid_view = True
                break

    if not valid_view or view.is_loading() or (view.file_name() or '').encode('utf-8') != filename:
        return

    highlight_colors(view, **kwargs)


def queue_highlight_colors(view, timeout=-1, preemptive=False, event=None, **kwargs):
    '''Put the current view in a queue to be examined by a ColorHighlight'''

    if preemptive:
        timeout = busy_timeout = 0
    elif timeout == -1:
        timeout, busy_timeout = get_delay(TIMES.get(view.id(), 100), view)
    else:
        busy_timeout = timeout

    kwargs.update({'timeout': timeout, 'busy_timeout': busy_timeout, 'preemptive': preemptive, 'event': event})
    queue(view, partial(_update_view, view, (view.file_name() or '').encode('utf-8'), **kwargs), kwargs)


def _callback(view, filename, kwargs):
    kwargs['callback'](view, filename, **kwargs)


def background_color_highlight():
    __lock_.acquire()

    try:
        callbacks = list(QUEUE.values())
        QUEUE.clear()
    finally:
        __lock_.release()

    for callback in callbacks:
        sublime.set_timeout(callback, 0)


################################################################################
# Queue dispatcher system:

queue_dispatcher = background_color_highlight
queue_thread_name = 'background color highlight'
MAX_DELAY = 10


def queue_loop():
    '''An infinite loop running the color highlight in a background thread meant to
       update the view after user modifies it and then does no further
       modifications for some time as to not slow down the UI with color highlighting.'''
    global __signaled_, __signaled_first_

    while __loop_:
        # print('acquire...')
        __semaphore_.acquire()
        __signaled_first_ = 0
        __signaled_ = 0
        # print('DISPATCHING!', len(QUEUE))
        queue_dispatcher()


def queue(view, callback, kwargs):
    global __signaled_, __signaled_first_
    now = time.time()
    __lock_.acquire()

    try:
        QUEUE[view.id()] = callback
        timeout = kwargs['timeout']
        busy_timeout = kwargs['busy_timeout']

        if now < __signaled_ + timeout * 4:
            timeout = busy_timeout or timeout

        __signaled_ = now
        _delay_queue(timeout, kwargs['preemptive'])

        # print('%s queued in %s' % ('' if __signaled_first_ else 'first ', __signaled_ - now))
        if not __signaled_first_:
            __signaled_first_ = __signaled_
    finally:
        __lock_.release()


def _delay_queue(timeout, preemptive):
    global __signaled_, __queued_
    now = time.time()

    if not preemptive and now <= __queued_ + 0.01:
        return  # never delay queues too fast (except preemptively)

    __queued_ = now
    _timeout = float(timeout) / 1000

    if __signaled_first_:
        if MAX_DELAY > 0 and now - __signaled_first_ + _timeout > MAX_DELAY:
            _timeout -= now - __signaled_first_
            if _timeout < 0:
                _timeout = 0
            timeout = int(round(_timeout * 1000, 0))

    new__signaled_ = now + _timeout - 0.01

    if __signaled_ >= now - 0.01 and (preemptive or new__signaled_ >= __signaled_ - 0.01):
        __signaled_ = new__signaled_
        # print('delayed to %s' % (preemptive, __signaled_ - now))

        def _signal():
            if time.time() < __signaled_:
                return
            __semaphore_.release()

        sublime.set_timeout(_signal, timeout)


def delay_queue(timeout):
    __lock_.acquire()
    try:
        _delay_queue(timeout, False)
    finally:
        __lock_.release()


# only start the thread once - otherwise the plugin will get laggy
# when saving it often.
__semaphore_ = threading.Semaphore(0)
__lock_ = threading.Lock()
__queued_ = 0
__signaled_ = 0
__signaled_first_ = 0

# First finalize old standing threads:
__loop_ = False
__pre_initialized_ = False


def queue_finalize(timeout=None):
    global __pre_initialized_

    for thread in threading.enumerate():
        if thread.isAlive() and thread.name == queue_thread_name:
            __pre_initialized_ = True
            thread.__semaphore_.release()
            thread.join(timeout)


queue_finalize()

# Initialize background thread:
__loop_ = True
__active_color_highlight_thread = threading.Thread(target=queue_loop, name=queue_thread_name)
__active_color_highlight_thread.__semaphore_ = __semaphore_
__active_color_highlight_thread.start()


################################################################################
# Initialize settings and main objects only once
class ColorHighlightSettings(Settings):
    pass


settings = ColorHighlightSettings(NAME)


class ColorHighlightSettingCommand(SettingTogglerCommandMixin, sublime_plugin.WindowCommand):
    settings = settings


if 'colorizer' not in globals():
    colorizer = SchemaColorizer()


################################################################################

def plugin_loaded():
    settings.load()


# ST3 features a plugin_loaded hook which is called when ST's API is ready.
#
# We must therefore call our init callback manually on ST2. It must be the last
# thing in this plugin (thanks, beloved contributors!).
if int(sublime.version()) < 3000:
    plugin_loaded()
