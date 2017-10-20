from __future__ import absolute_import

import time
import threading
from functools import partial

import re
import os
import string

import sublime
import sublime_plugin

# TODO: import ColorHighlighter.colors for ST3
from .colors import names_to_hex, xterm_to_hex

version = "3.1"

# Constants
hex_digits = string.digits + "ABCDEF"


def log(s):
    # print("[ColorHighlighter]", s)
    pass


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
# \033[38;15m


def regexp_factory(names, xterm):
    _COLORS = r'(?<![-.\w])%s(?![-.\w])' % r'(?![-.\w])|(?<![-.\w])'.join(names.keys())
    if xterm:
        _COLORS += r'|(?<=[;])%s(?=[;m])' % r'(?=[;m])|(?<=[;])'.join(xterm.keys())

    _ALL_HEX_COLORS = r'%s|%s' % (_COLORS, r'(?:#|0x)[0-9a-fA-F]{8}\b|(?:#|0x)[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b')
    _ALL_HEX_COLORS = r'%s|%s|%s' % (
        r'rgba\((?:([0-9]+),\s*([0-9]+),\s*([0-9]+)|(%s)),\s*((?:[0-9]*\.\d+|[0-9]+)?%%?)\)' % _ALL_HEX_COLORS,
        r'rgb\(([0-9]+),\s*([0-9]+),\s*([0-9]+)\)',
        r'(%s)' % _ALL_HEX_COLORS,
    )
    _ALL_HEX_COLORS_CAPTURE = r'\1\4\6\9,\2\7,\3\8,\5'

    _XHEX_COLORS = r'%s|%s' % (_COLORS, r'0x[0-9a-fA-F]{8}\b|0x[0-9a-fA-F]{6}\b')
    _XHEX_COLORS = r'%s|%s|%s' % (
        r'rgba\((?:([0-9]+),\s*([0-9]+),\s*([0-9]+)|(%s)),\s*((?:[0-9]*\.\d+|[0-9]+)?%%?)\)' % _XHEX_COLORS,
        r'rgb\(([0-9]+),\s*([0-9]+),\s*([0-9]+)\)',
        r'(%s)' % _XHEX_COLORS,
    )
    _XHEX_COLORS_CAPTURE = r'\1\4\6\9,\2\7,\3\8,\5'

    _HEX_COLORS = r'%s|%s' % (_COLORS, r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b')
    _HEX_COLORS = r'%s|%s|%s' % (
        r'rgba\((?:([0-9]+),\s*([0-9]+),\s*([0-9]+)|(%s)),\s*((?:[0-9]*\.\d+|[0-9]+)?%%?)\)' % _HEX_COLORS,
        r'rgb\(([0-9]+),\s*([0-9]+),\s*([0-9]+)\)',
        r'(%s)' % _HEX_COLORS,
    )
    _HEX_COLORS_CAPTURE = r'\1\4\6\9,\2\7,\3\8,\5'

    _NO_HEX_COLORS = r'%s' % (_COLORS,)
    _NO_HEX_COLORS = r'%s|%s|%s' % (
        r'rgba\((?:([0-9]+),\s*([0-9]+),\s*([0-9]+)|(%s)),\s*((?:[0-9]*\.\d+|[0-9]+)?%%?)\)' % _NO_HEX_COLORS,
        r'rgb\(([0-9]+),\s*([0-9]+),\s*([0-9]+)\)',
        r'(%s)' % _NO_HEX_COLORS,
    )
    _NO_HEX_COLORS_CAPTURE = r'\1\4\6\9,\2\7,\3\8,\5'

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

all_names_to_hex = dict(names_to_hex, **xterm_to_hex)
_NO_HEX_COLORS, _NO_HEX_COLORS_CAPTURE, _XHEX_COLORS, _XHEX_COLORS_CAPTURE, _HEX_COLORS, _HEX_COLORS_CAPTURE, _ALL_HEX_COLORS, _ALL_HEX_COLORS_CAPTURE = regexp_factory(names_to_hex, None)
__NO_HEX_COLORS, __NO_HEX_COLORS_CAPTURE, __XHEX_COLORS, __XHEX_COLORS_CAPTURE, __HEX_COLORS, __HEX_COLORS_CAPTURE, __ALL_HEX_COLORS, __ALL_HEX_COLORS_CAPTURE = regexp_factory(names_to_hex, xterm_to_hex)
COLORS_REGEX = {
    (False, False, False): (_NO_HEX_COLORS, _NO_HEX_COLORS_CAPTURE,),
    (False, True, False): (_XHEX_COLORS, _XHEX_COLORS_CAPTURE),
    (True, False, False): (_HEX_COLORS, _HEX_COLORS_CAPTURE),
    (True, True, False): (_ALL_HEX_COLORS, _ALL_HEX_COLORS_CAPTURE),
    (False, False, True): (__NO_HEX_COLORS, __NO_HEX_COLORS_CAPTURE,),
    (False, True, True): (__XHEX_COLORS, __XHEX_COLORS_CAPTURE),
    (True, False, True): (__HEX_COLORS, __HEX_COLORS_CAPTURE),
    (True, True, True): (__ALL_HEX_COLORS, __ALL_HEX_COLORS_CAPTURE),
}

_R_RE = re.compile(r'\\([0-9])')
COLORS_RE = dict((k, (re.compile(v[0]), _R_RE.sub(lambda m: chr(int(m.group(1))), v[1]))) for k, v in COLORS_REGEX.items())


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
    sa = '%X' % int(a * 255)
    if len(sa) == 1:
        sa = '0' + sa
    return '#%s%s%s%s' % (sr, sg, sb, sa)


class HtmlGen:
    name = "Color"
    prefix = "col_"
    backup_ext = ".chback"

    colors = {}
    color_scheme = None
    need_upd = False
    need_restore = False
    need_backup = False
    gen_string = """
        <dict>
            <key>name</key>
            <string>{name}</string>
            <key>scope</key>
            <string>{scope}</string>
            <key>settings</key>
            <dict>
                <key>background</key>
                <string>{background}</string>
                <key>foreground</key>
                <string>{foreground}</string>
            </dict>
        </dict>
"""

    def normalize(self, col):
        if col:
            col = all_names_to_hex.get(col.lower(), col.upper())
            if col.startswith('0X'):
                col = '#' + col[2:]
            try:
                if col[0] != '#':
                    raise ValueError
                if len(col) == 4:
                    col = '#' + col[1] * 2 + col[2] * 2 + col[3] * 2 + 'FF'
                elif len(col) == 5:
                    col = '#' + col[1] * 2 + col[2] * 2 + col[3] * 2 + col[4] * 2
                elif len(col) == 7:
                    col += 'FF'
                return '#%02X%02X%02X%02X' % (int(col[1:3], 16), int(col[3:5], 16), int(col[5:7], 16), int(col[7:9], 16))
            except Exception:
                print("Invalid color: %r" % col)

    def write_file(self, pp, fl, s):
        rf = pp + fl
        dn = os.path.dirname(rf)
        if not os.path.exists(dn):
            os.makedirs(dn)
        f = open(rf, 'w')
        f.write(s)
        f.close()

    def read_file(self, pp, fl):
        rf = pp + fl
        if os.path.exists(rf):
            f = open(rf, 'r')
            res = f.read()
            f.close()
        else:
            rf = 'Packages' + fl
            res = sublime.load_resource(rf)
        return res

    def get_inv_col(self, col):
        # [https://stackoverflow.com/a/3943023]
        r = int(col[1:3], 16) / 255.0
        g = int(col[3:5], 16) / 255.0
        b = int(col[5:7], 16) / 255.0
        # a = int(col[7:9], 16) / 255.0
        l = 0.2126 * r + 0.7152 * g + 0.0722 * b

        if l < 0.060:
            return '#66666FF'

        if l < 0.089:
            return '#888888FF'

        if l < 0.179:
            return '#BBBBBBFF'

        if l < 0.358:
            return '#EEEEEEFF'

        if l < 0.537:
            return '#222222FF'

        if l < 0.716:
            return '#222222FF'

        return '#222222FF'

    def region_name(self, s):
        return self.prefix + s[1:]

    def add_color(self, col):
        col = self.normalize(col)
        if not col:
            return
        if col not in self.colors:
            self.colors[col] = self.region_name(col)
            self.need_upd = True
        return self.colors[col]

    def need_update(self):
        return self.need_upd

    def color_scheme_path(self, view):
        packages_path = sublime.packages_path()
        cs = self.color_scheme
        if cs is None:
            self.color_scheme = view.settings().get('color_scheme')
            cs = self.color_scheme
        # do not support empty color scheme
        if not cs:
            log("Empty scheme")
            return
        # extract name
        cs = cs[cs.find('/'):]
        return packages_path, cs

    def get_color_scheme(self, packages_path, cs):
        cont = self.read_file(packages_path, cs)
        if os.path.exists(packages_path + cs + self.backup_ext):
            log("Already backuped")
        else:
            self.write_file(packages_path, cs + self.backup_ext, cont)  # backup
            log("Backup done")
        return cont

    def update(self, view):
        if not self.need_upd:
            return
        self.need_upd = False

        color_scheme_path = self.color_scheme_path(view)
        if not color_scheme_path:
            return
        packages_path, cs = color_scheme_path
        cont = self.get_color_scheme(packages_path, cs)

        current_colors = set("#%s" % c for c in re.findall(r'<string>%s(.*?)</string>' % self.prefix, cont, re.DOTALL))

        string = ""
        for col, name in self.colors.items():
            if col not in current_colors:
                fg_col = self.get_inv_col(col)
                string += self.gen_string.format(
                    name=self.name,
                    scope=name,
                    background=col,
                    foreground=fg_col,
                )

        if string:
            # edit cont
            n = cont.find("<array>") + len("<array>")
            try:
                cont = cont[:n] + string + cont[n:]
            except UnicodeDecodeError:
                cont = cont[:n] + string.encode("utf-8") + cont[n:]

            self.write_file(packages_path, cs, cont)
            self.need_restore = True
            log("Updated")

    def restore_color_scheme(self):
        if not self.need_restore:
            return
        self.need_restore = False
        cs = self.color_scheme
        # do not support empty color scheme
        if not cs:
            log("Empty scheme, can't restore")
            return
        # extract name
        cs = cs[cs.find('/'):]
        packages_path = sublime.packages_path()
        if os.path.exists(packages_path + cs + self.backup_ext):
            log("Starting restore scheme: " + cs)
            # TODO: move to other thread
            self.write_file(packages_path, cs, self.read_file(packages_path, cs + self.backup_ext))
            self.colors = {}
            log("Restore done.")
        else:
            log("No backup :(")

    def set_color_scheme(self, view):
        settings = view.settings()
        cs = settings.get('color_scheme')
        if cs != self.color_scheme:
            color_scheme_path = self.color_scheme_path(view)
            if color_scheme_path:
                packages_path, cs = color_scheme_path
                cont = self.get_color_scheme(packages_path, cs)
                self.colors = dict(("#%s" % c, "%s%s" % (self.prefix, c)) for c in re.findall(r'<string>%s(.*?)</string>' % self.prefix, cont, re.DOTALL))
            self.color_scheme = settings.get('color_scheme')
            self.need_backup = True

    def change_color_scheme(self, view):
        cs = view.settings().get('color_scheme')
        if cs and cs != self.color_scheme:
            log("Color scheme changed %s -> %s" % (self.color_scheme, cs))
            self.restore_color_scheme()
            self.set_color_scheme(view)
            self.update(view)

htmlGen = HtmlGen()


ALL_SETTINGS = [
    'colorhighlighter',
    'colorhighlighter_0x_hex_values',
    'colorhighlighter_hex_values',
    'colorhighlighter_xterm_color_values',
    'colorhighlighter_delay',
]


def settings_changed():
    for window in sublime.windows():
        for view in window.views():
            reload_settings(view.settings())


def reload_settings(settings):
    '''Restores user settings.'''
    settings_name = 'ColorHighlighter'
    global_settings = sublime.load_settings(settings_name + '.sublime-settings')
    global_settings.clear_on_change(settings_name)
    global_settings.add_on_change(settings_name, settings_changed)

    for setting in ALL_SETTINGS:
        if global_settings.has(setting):
            settings.set(setting, global_settings.get(setting))

    if not settings.has('colorhighlighter'):
        settings.set('colorhighlighter', True)

    if not settings.has('colorhighlighter_0x_hex_values'):
        settings.set('colorhighlighter_0x_hex_values', True)

    if not settings.has('colorhighlighter_hex_values'):
        settings.set('colorhighlighter_hex_values', True)

    if not settings.has('colorhighlighter_xterm_color_values'):
        settings.set('colorhighlighter_xterm_color_values', False)

    if not settings.has('colorhighlighter_delay'):
        settings.set('colorhighlighter_delay', 0)


def get_setting(settings, name):
    if not settings.has(name):
        reload_settings(settings)
    return settings.get(name)


# Commands


# treat hex vals as colors
class ColorHighlighterCommand(sublime_plugin.WindowCommand):
    def run_(self, edit_token, args={}):
        view = self.window.active_view()
        action = args.get('action', '')
        if view and action:
            view.run_command('highlight', action)

    def is_enabled(self):
        view = self.window.active_view()
        if view:
            settings = view.settings()
            return bool(get_setting(settings, 'colorhighlighter'))
        return False


class ColorHighlighterHighlightCommand(ColorHighlighterCommand):
    def is_enabled(self):
        return True


class ColorHighlighterEnableLoadSaveCommand(ColorHighlighterCommand):
    def is_enabled(self):
        enabled = super(ColorHighlighterEnableLoadSaveCommand, self).is_enabled()

        if enabled:
            view = self.window.active_view()
            if view:
                settings = view.settings()
                if get_setting(settings, 'colorhighlighter') == 'load-save':
                    return False

        return enabled


class ColorHighlighterEnableSaveOnlyCommand(ColorHighlighterCommand):
    def is_enabled(self):
        enabled = super(ColorHighlighterEnableSaveOnlyCommand, self).is_enabled()

        if enabled:
            view = self.window.active_view()
            if view:
                settings = view.settings()
                if get_setting(settings, 'colorhighlighter') == 'save-only':
                    return False

        return enabled


class ColorHighlighterDisableCommand(ColorHighlighterCommand):
    def is_enabled(self):
        enabled = super(ColorHighlighterDisableCommand, self).is_enabled()

        if enabled:
            view = self.window.active_view()
            if view:
                settings = view.settings()
                if get_setting(settings, 'colorhighlighter') is False:
                    return False

        return enabled


class ColorHighlighterEnableCommand(ColorHighlighterCommand):
    def is_enabled(self):
        view = self.window.active_view()

        if view:
            settings = view.settings()
            if get_setting(settings, 'colorhighlighter') is not False:
                return False

        return True


# treat hex vals as colors
class ColorHighlighterHexValsAsColorsCommand(ColorHighlighterCommand):
    def is_enabled(self):
        enabled = super(ColorHighlighterHexValsAsColorsCommand, self).is_enabled()

        if enabled:
            view = self.window.active_view()
            if view:
                settings = view.settings()
                if get_setting(settings, 'colorhighlighter_hex_values') is False:
                    return False

        return enabled
    is_checked = is_enabled


# treat hex vals as colors
class ColorHighlighterXHexValsAsColorsCommand(ColorHighlighterCommand):
    def is_enabled(self):
        enabled = super(ColorHighlighterXHexValsAsColorsCommand, self).is_enabled()

        if enabled:
            view = self.window.active_view()
            if view:
                settings = view.settings()
                if get_setting(settings, 'colorhighlighter_0x_hex_values') is False:
                    return False

        return enabled
    is_checked = is_enabled


# command to restore color scheme
class RestoreColorSchemeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        htmlGen.restore_color_scheme()

all_regs = []
inited = 0


class HighlightCommand(sublime_plugin.TextCommand):
    '''command to interact with linters'''

    def __init__(self, view):
        self.view = view
        self.help_called = False

    def run_(self, edit_token, action):
        '''method called by default via view.run_command;
           used to dispatch to appropriate method'''
        if not action:
            return

        try:
            lc_action = action.lower()
        except AttributeError:
            return

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
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        settings = self.view.settings()
        ch_settings.set('colorhighlighter_hex_values', not get_setting(settings, 'colorhighlighter_hex_values'))
        sublime.save_settings(__name__ + '.sublime-settings')
        queue_highlight_colors(self.view, preemptive=True)

    def toggle_xhex_values(self):
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        settings = self.view.settings()
        ch_settings.set('colorhighlighter_0x_hex_values', not get_setting(settings, 'colorhighlighter_0x_hex_values'))
        sublime.save_settings(__name__ + '.sublime-settings')
        queue_highlight_colors(self.view, preemptive=True)

    def reset(self):
        '''Removes existing lint marks and restores user settings.'''
        view = self.view
        erase_highlight_colors(view)
        reload_settings(view.settings())
        queue_highlight_colors(self.view, preemptive=True)

    def on(self):
        '''Turns background linting on.'''
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        ch_settings.set('colorhighlighter', True)
        sublime.save_settings(__name__ + '.sublime-settings')
        queue_highlight_colors(self.view, preemptive=True)

    def enable_load_save(self):
        '''Turns load-save linting on.'''
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        ch_settings.set('colorhighlighter', 'load-save')
        sublime.save_settings(__name__ + '.sublime-settings')
        erase_highlight_colors(self.view)

    def enable_save_only(self):
        '''Turns save-only linting on.'''
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        ch_settings.set('colorhighlighter', 'save-only')
        sublime.save_settings(__name__ + '.sublime-settings')
        erase_highlight_colors(self.view)

    def off(self):
        '''Turns background linting off.'''
        ch_settings = sublime.load_settings(__name__ + '.sublime-settings')
        ch_settings.set('colorhighlighter', False)
        sublime.save_settings(__name__ + '.sublime-settings')
        erase_highlight_colors(self.view)


class BackgroundColorHighlighter(sublime_plugin.EventListener):
    def on_new(self, view):
        global inited
        reload_settings(view.settings())
        if not inited:
            htmlGen.set_color_scheme(view)
        inited += 1
        view.settings().add_on_change('color_scheme', lambda self=self, view=view: htmlGen.change_color_scheme(view))

    def on_clone(self, view):
        self.on_new(view)

    def on_modified(self, view):
        settings = view.settings()
        if get_setting(settings, 'colorhighlighter') is not True:
            erase_highlight_colors(view)
            return

        selection = view.command_history(0, True)[0] != 'paste'
        queue_highlight_colors(view, selection=selection)

    def on_close(self, view):
        global inited
        vid = view.id()
        if vid in TIMES:
            del TIMES[vid]
        if vid in COLOR_HIGHLIGHTS:
            del COLOR_HIGHLIGHTS[vid]
        inited -= 1
        # if inited <= 0:
        #     htmlGen.restore_color_scheme()

    def on_activated(self, view):
        if view.file_name() is None:
            return
        vid = view.id()
        if vid in TIMES:
            return
        TIMES[vid] = 100

        settings = view.settings()

        reload_settings(settings)

        if get_setting(settings, 'colorhighlighter') in (False, 'save-only'):
            return

        queue_highlight_colors(view, preemptive=True, event='on_load')

    def on_post_save(self, view):
        settings = view.settings()

        if get_setting(settings, 'colorhighlighter') is False:
            return

        queue_highlight_colors(view, preemptive=True, event='on_post_save')

    def on_selection_modified(self, view):
        delay_queue(1000)  # on movement, delay queue (to make movement responsive)


TIMES = {}       # collects how long it took the color highlighter to complete
COLOR_HIGHLIGHTS = {}  # Highlighted regions


def erase_highlight_colors(view):
    vid = view.id()
    if vid in COLOR_HIGHLIGHTS:
        for name in COLOR_HIGHLIGHTS[vid]:
            view.erase_regions(name)
    COLOR_HIGHLIGHTS[vid] = set()


def highlight_colors(view, selection=False, **kwargs):
    vid = view.id()
    start = time.time()

    if len(view.sel()) > 100:
        selection = False

    settings = view.settings()

    words = {}
    found = []
    _hex_values = bool(get_setting(settings, 'colorhighlighter_hex_values'))
    _xhex_values = bool(get_setting(settings, 'colorhighlighter_0x_hex_values'))
    _xterm_color_values = bool(get_setting(settings, 'colorhighlighter_xterm_color_values'))
    if selection:
        colors_re, colors_re_capture = COLORS_RE[(_hex_values, _xhex_values, _xterm_color_values)]
        selected_lines = list(ln for r in view.sel() for ln in view.lines(r))
        matches = [colors_re.finditer(view.substr(l)) for l in selected_lines]
        matches = [(sublime.Region(selected_lines[i].begin() + m.start(), selected_lines[i].begin() + m.end()), m.groups()) if m else (None, None) for i, am in enumerate(matches) for m in am]
        matches = [(rg, ''.join(gr[ord(g) - 1] or '' if ord(g) < 10 else g for g in colors_re_capture)) for rg, gr in matches if rg]
        if matches:
            ranges, found = zip(*[q for q in matches if q])
        else:
            ranges = []
    else:
        selected_lines = None
        colors_re, colors_re_capture = COLORS_REGEX[(_hex_values, _xhex_values, _xterm_color_values)]
        ranges = view.find_all(colors_re, 0, colors_re_capture, found)

    for i, col in enumerate(found):
        col = col.rstrip(',')
        col = col.split(',')
        if len(col) == 1:
            # In the form of color name black or #FFFFFFFF or 0xFFFFFF:
            col0 = col[0]
            col0 = all_names_to_hex.get(col0.lower(), col0.upper())
            if col0.startswith('0X'):
                col0 = '#' + col0[2:]
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
            if r >= 256 or g >= 256 or b >= 256:
                continue
            if len(col) == 4:
                if col[3].endswith('%'):
                    a = float(col[3][:-1]) / 100.0
                else:
                    a = float(col[3])
                if a > 1.0:
                    continue
            else:
                a = 1.0
            col = tohex(r, g, b, a)
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
                    a = float(col3[:-1]) / 100.0
                else:
                    a = float(col3)
                if a > 1.0:
                    continue
            else:
                a = 1.0
            col = tohex(col0, None, None, a)
        name = htmlGen.add_color(col)
        if name not in words:
            words[name] = [ranges[i]]
        else:
            words[name].append(ranges[i])

    if htmlGen.need_update():
        htmlGen.update(view)

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
        view.add_regions(name, w, name, '', sublime.PERSISTENT)
        all_regs.add(name)

    TIMES[vid] = (time.time() - start) * 1000  # Keep how long it took to color highlight
    # print('highlight took %s' % TIMES[vid])


################################################################################
# Queue connection

QUEUE = {}       # views waiting to be processed by color highlighter

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

    settings = view.settings()

    # If the user specifies a delay greater than the built in delay,
    # figure they only want to see marks when idle.
    minDelay = int(get_setting(settings, 'colorhighlighter_delay') * 1000)

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
    '''Put the current view in a queue to be examined by a color highlighter'''

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


def background_color_highlighter():
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

queue_dispatcher = background_color_highlighter
queue_thread_name = 'background color highlighter'
MAX_DELAY = 10


def queue_loop():
    '''An infinite loop running the color highlighter in a background thread meant to
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
__active_color_highlighter_thread = threading.Thread(target=queue_loop, name=queue_thread_name)
__active_color_highlighter_thread.__semaphore_ = __semaphore_
__active_color_highlighter_thread.start()

################################################################################
