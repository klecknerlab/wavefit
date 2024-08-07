#!/usr/bin/python3
# -*- coding: utf-8 -*-#
#
# Copyright 2023 Dustin Kleckner
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import matplotlib
matplotlib.use('Qt5Agg')

from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import traceback
import time

import numpy as np
π = np.pi
import os, sys
from scipy import optimize

try:
    import vxi11
except:
    print('Warning: VXI11 not installed; data loading through ethernet disabled.\n(to intall, run: pip install python-vxi11)')
    HAS_VXI11 = False
else:
    HAS_VXI11 = True


def cosine_fit(t, x0, A, ω, ϕ):
    return x0 + A * np.cos(ω * t + ϕ)

def find_harmonics(t, ref, signal, harmonics=5, window=np.hanning):
    d = {"num harmonics":harmonics}

    dt = t[1] - t[0]
    N = len(t)

    offset = ref.mean()
    window = window(N)
    window *= 2 / window.sum()
    ref_w = (ref - offset) * window

    # FFT of reference
    ref_f = np.fft.rfft(ref_w)[:N//2]
    f = np.fft.fftfreq(N, dt)[:N//2]

    # Find strongest frequency, including amplitude and phase
    i = np.argmax(abs(ref_f))
    A = ref_f[i]

    ωg = 2*π*f[i]
    p0 = (offset, abs(A), ωg, np.angle(A) - ωg * t[0])

    # Fit reference signal
    popt, pconv = optimize.curve_fit(cosine_fit, t, ref, p0)

    # Update data
    d['ref offset'], d['ref A'], d['ref ω'], d['ref ϕ'] = popt
    d['ref ϕ'] = d['ref ϕ'] % (2*π)
    d['ref error'] = (ref - cosine_fit(t, *popt)).std()

    ω0, ϕ0 = d['ref ω'], d['ref ϕ']

    # Windowed signal for analysis
    sig = (signal - signal.mean()) * window

    # Compute harmonics
    for n in range(1, harmonics + 1):
        ω = n * ω0
        d[f'ω{n}'] = ω
        A = (sig * np.exp(-1j * (ω*t + n*ϕ0))).sum()
        d[f'A~{n}'] = A
        d[f'A{n}'] = abs(A)
        d[f'ϕ{n}'] = np.angle(A)

    return d

def harmonic_reconstruct(t, d):
    x = 0
    ϕ0 = d['ref ϕ']
    for n in range(1, d['num harmonics'] + 1):
        ω, A, ϕ = d[f'ω{n}'], d[f'A{n}'], d[f'ϕ{n}']
        x += A * np.cos(ω*t + ϕ + n*ϕ0)
        if n == 1:
            label = 'fundamental'
        else:
            label = f'harmonic {n}'
        # print(f'{label:>20s}: A={A:.3f}, ϕ={-ϕ*180/π:.1f}°')

    return x

def load_osc_csv(fn, offset=True):
    '''Load data from the CSV's generated by the Rigol DS1054.

    Parameters
    ----------
    fn : the filename to load
    offset : if True (default), adds the time offset so that t=0
                 is the trigger point.  Otherwise the first time
                 value is 0.

    Returns
    -------
    t, V1, V2... : the first return parameter is the time, and
                    the rest are as many channels as are stored in
                    the file.
    '''

    with open(fn) as f:
        f.readline() #The first line is headers, just skip
        parts = f.readline().split(',') #The second line includes the time increment data
        data = np.loadtxt(f, delimiter=',', usecols=np.arange(len(parts)-2), unpack=True)

    start = float(parts[-2]) #Second to last entry is the time start
    inc = float(parts[-1]) #Last entry is the time increment
    data[0] *= inc #Multiply the time axis by the increment

    if offset: data[0] += start

    return data

def idn_eth(ip):
    inst = vxi11.Instrument(ip)
    inst.timeout = 0.5
    reply = inst.ask("*IDN?")
    inst.close()
    return reply

def load_eth(ip, channels=(1, 2)):
    if not HAS_VXI11:
        raise RuntimeError("VXI11 not installed; can't load data over ethernet!\n(to intall, run: pip install python-vxi11)")

    inst = vxi11.Instrument(ip)
    inst.timeout = 3

    inst.write(":STOP")

    data = []

    for channel in channels:
        inst.write(f":WAV:SOUR CHAN{channel:d}")
        inst.write(":WAV:FORM BYTE")
        inst.write(":WAV:DATA?")

        raw = inst.read_raw()
        if raw[0:1] != b'#':
            raise ValueError(f'First byte of raw data should be #, found {chr(dat[0])}')
        N_head = int(raw[1:2])
        N_points = int(raw[2:2+N_head])

        raw = np.frombuffer(raw[2+N_head:2+N_head+N_points], dtype='u1')

        preamble = list(map(float, inst.ask(':WAV:PRE?').split(',')))

        if not data:
            # If we haven't already, write a time channel to the output
            data.append((np.arange(len(raw)) - (preamble[6] + preamble[5])) * preamble[4])

        data.append((raw - (preamble[9] + preamble[8])) * preamble[7])

    inst.write(":RUN")
    inst.close()

    return tuple(data)


SI_PREFIX = {
    -18: "a", -15: "f", -12: "p", -9: "n", -6: "μ", -3: "m", 0: "", +3: "k",
    +6: "M", +9: "G", +12: "T", +15: "P", +18: "E"
}

SUPERSCRIPT = {
    '0': '\u2070', '1': '\u00B9', '2': '\u00B2', '3': '\u00B3', '4': '\u2074',
    '5': '\u2075', '6': '\u2076', '7': '\u2077', '8': '\u2078', '9': '\u2079',
    '+': '\u207A', '-': '\u207B', '=': '\u207C', '(': '\u207D', ')': '\u207E',
    'e': '\u1D49',
    '.': '\u22C5' #This is a controversial choice -- there is no good one!
}

def superscript(s):
    return ''.join(SUPERSCRIPT.get(c, c) for c in s)

def sf_format(x, sig_figs):
    return f'{x:f}'[:sig_figs+1].rstrip('.')

def scientific_format(x, sig_figs=4):
    power = int(np.floor(np.log10(abs(x))))
    num = sf_format(x / 10**power, sig_figs)
    if power:
        num += f' × 10{superscript(str(power))}'
    return num

def get_prefix(x):
    power = int(np.floor(np.log10(abs(x))//3))*3
    if power in SI_PREFIX:
        return SI_PREFIX[power], 10**power
    else:
        return None, 1

def SI_format(x, units='', sig_figs=4):
    if x == 0:
        return "0"
    else:
        prefix, div = get_prefix(x)
        if prefix is not None:
            num = sf_format(x / div, sig_figs) + f' {prefix}'
        else:
            num = scientific_format(x, sig_figs) + ' '

    if units:
        return num + units
    else:
        return num.strip()

def save_csv(fn, data, fit=[], harmonics=None):
    cols = []
    headings = []

    for i, dat in enumerate(data):
        cols.append(dat)
        if i == 0:
            headings.append('t (s)')
        elif i == 1:
            headings.append('V_ref')
        elif i == 2:
            headings.append('V_sig')
        else:
            headings.append(f'V_sig{i-1}')

        if i > 0 and i <= len(fit):
            headings.append(headings[-1] + ' fit')
            cols.append(fit[i-1])

    if harmonics:
        headings += ["", "Harmonic", "Frequency (Hz)", "Amplitude (V)", "Phase Delay (rad)"]
        cols += [[], [], [], [], []]
        for n in range(1, harmonics['num harmonics'] + 1):
            cols[-4].append(n)
            cols[-3].append(harmonics[f'ω{n}'] / (2*π))
            cols[-2].append(harmonics[f'A{n}'])
            cols[-1].append(harmonics[f'ϕ{n}'])

        cols[-4].append('ref')
        cols[-3].append(harmonics[f'ref ω'] / (2*π))
        cols[-2].append(harmonics[f'ref A'])
        cols[-1].append(harmonics[f'ref ϕ'])

    # 169.236.119.238

    with open(fn, 'wt') as f:
        f.write(','.join(headings) + '\n')

        for i in range(max(map(len, cols))):
            items = []
            lnz = 0
            for j, col in enumerate(cols):
                if i < len(col):
                    items.append(str(col[i]))
                    lnz = j
                else:
                    items.append("")

            f.write(','.join(items[:lnz+1]) + '\n')

class Tabs(QtWidgets.QTabWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.pages = []
        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.remove_tab)

    def add_tab(self, widget, title):
        self.pages.append(widget)
        self.setCurrentIndex(self.addTab(self.pages[-1], title))

    def remove_tab(self, index):
        self.removeTab(index)
        self.pages.pop(index).deleteLater()

    def current_tab(self):
        return self.pages[self.currentIndex()]

class DataDisplay(QtWidgets.QSplitter):
    def __init__(self, parent, data, harmonics=5):
        super().__init__(parent)
        self.setOrientation(QtCore.Qt.Vertical)
        self.layout = QtWidgets.QVBoxLayout(self)

        self.fig = Figure()
        self.fig_canvas = FigureCanvasQTAgg(self.fig)

        # self.splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.addWidget(self.fig_canvas)

        lw = QtWidgets.QWidget()
        lw.setLayout(self.layout)
        self.addWidget(lw)

        # self.addWidget(self.splitter)

        # self.layout.addWidget(self.fig_canvas)
        # self.setLayout(self.layout)

        self.data = data
        self.num_harmonics = harmonics

        if len(data) != 3:
            self.layout.addWidget(
                QtWidgets.QLabel(f'Data should have 3 columns, found {len(data)}!  No fitting was performed')
            )

            self.detail_plot = False

        else:
            self.detail_plot = True

            layout = QtWidgets.QHBoxLayout()

            self.button_detail = QtWidgets.QRadioButton("Detailed signal view")
            self.button_detail.setChecked(True)
            self.button_detail.pressed.connect(self.plot_detail)
            layout.addWidget(self.button_detail)

            self.button_wide = QtWidgets.QRadioButton("Show entire data range")
            self.button_wide.pressed.connect(self.plot_wide)
            layout.addWidget(self.button_wide)

            layout.addStretch(1)

            self.layout.addLayout(layout)

            self.harmonics = find_harmonics(data[0], data[1], data[2], self.num_harmonics)

            self.ref_fit = cosine_fit(data[0], *(self.harmonics[l] for l in ('ref offset', 'ref A', 'ref ω', 'ref ϕ')))
            self.ref_fit1 = cosine_fit(data[0], 0.5, 0.5, *(self.harmonics[l] for l in ('ref ω', 'ref ϕ')))
            self.sig_fit = harmonic_reconstruct(data[0], self.harmonics)

            self.table = QtWidgets.QTableWidget(self.num_harmonics+1, 5, self)
            self.layout.addWidget(self.table)
            self.table.setHorizontalHeaderLabels(
                ['Frequency', 'Amplitude', 'Phase Delay', 'Phase Delay (deg)', 'Delay']
            )
            self.table.setVerticalHeaderLabels(
                ['Reference', 'Fundamental'] +
                [f'Harmonic {n}' for n in range(2, self.num_harmonics+1)]
            )

            ω, A, ϕ = [self.harmonics[f'ref {l}'] for l in ("ω", "A", "ϕ")]
            self.period = 2*π / ω
            ϕ = (-ϕ) % (2*π)

            # FFT bin size is 1 / Δt -- assume our actual error is 10% of this
            freq_precision = 0.1 / (self.data[0][-1] - self.data[0][0])
            # print(freq_precision)
            freq_sigfigs = int(np.ceil(np.log10(ω / (2*π) / freq_precision)))

            self.table.setItem(0, 0, QtWidgets.QTableWidgetItem(SI_format(ω / (2*π), 'Hz', freq_sigfigs)))
            self.table.setItem(0, 1, QtWidgets.QTableWidgetItem(SI_format(A, 'V')))
            self.table.setItem(0, 2, QtWidgets.QTableWidgetItem(f'({ϕ:.3f} rad)'))
            self.table.setItem(0, 3, QtWidgets.QTableWidgetItem(f'({ϕ * 180/π:.1f}°)'))
            self.table.setItem(0, 4, QtWidgets.QTableWidgetItem(f'({SI_format(ϕ/ω, "s")})'))
            self.ref_delay = ϕ/ω

            for n in range(1, self.num_harmonics+1):
                ω, A, ϕ = [self.harmonics[f'{l}{n}'] for l in ("ω", "A", "ϕ")]
                ϕ = (-ϕ) % (2*π)
                if n == 1:
                    self.fund_delay = ϕ/ω
                self.table.setItem(n, 0, QtWidgets.QTableWidgetItem(SI_format(ω / (2*π), 'Hz', freq_sigfigs)))
                self.table.setItem(n, 1, QtWidgets.QTableWidgetItem(SI_format(A, 'V')))
                self.table.setItem(n, 2, QtWidgets.QTableWidgetItem(f'{ϕ:.3f} rad'))
                self.table.setItem(n, 3, QtWidgets.QTableWidgetItem(f'{ϕ * 180/π:.1f}°'))
                item = QtWidgets.QTableWidgetItem(SI_format(ϕ/ω, "s"))
                self.table.setItem(n, 4, item)
                if n == 1:
                    item.setForeground(QtGui.QBrush(QtCore.Qt.red))

            note = QtWidgets.QLabel("Note: reference delay mesaured relative to trigger (t=0); other delays mesaured relative to reference signal peak!")
            note.setWordWrap(True)
            self.layout.addWidget(note)

        self.draw_plot()

    def save_csv(self, fn):
        args = [fn, self.data]
        if hasattr(self, 'harmonics'):
            args += [[self.ref_fit, self.sig_fit], self.harmonics]
        save_csv(*args)

    def plot_detail(self):
        self.detail_plot = True
        self.draw_plot()

    def plot_wide(self):
        self.detail_plot = False
        self.draw_plot()

    def draw_plot(self):
        self.fig.clear()
        # self.axes = self.fig.add_subplot(111)
        self.axes = self.fig.add_axes([0.15, 0.2, 0.8, 0.75])

        if getattr(self, 'detail_plot', False):
            self.t_prefix, self.t_div = get_prefix(self.period)
            if self.t_prefix is None:
                self.t_prefix = ""

            self.axes.set_xlabel(f'time ({self.t_prefix}s)')
            self.t = self.data[0] / self.t_div

            # self.axes.plot(self.t, self.ref_fit)
            # self.axes.plot(self.t, self.sig_fit)

            self.t_prefix, self.t_div = get_prefix(self.period)
            if self.t_prefix is None:
                self.t_prefix = ""
            self.t = self.data[0] / self.t_div

            t1 = self.ref_delay / self.t_div
            self.t -= t1
            t2 = self.fund_delay / self.t_div

            t0 = -2.5*self.period / self.t_div


            if t0 < self.t[0]:
                t0 = self.t[0]



            # self.axes.plot(self.t, self.data[1], '.')

            self.axes.plot(self.t, self.data[2], '.', color='C1')
            # self.axes.plot(self.t, self.ref_fit)
            self.axes.plot(self.t, self.sig_fit, 'k--')

            yl = self.axes.get_ylim()
            self.axes.plot([0, 0], yl, 'k:', zorder=-1)
            self.axes.plot([t2, t2], yl, 'r-', zorder=-1)
            self.axes.plot(self.t, (self.ref_fit1 * (yl[1] - yl[0])) + yl[0], color='C0', alpha=0.5, zorder=-1)


            self.axes.set_ylim(*yl)
            self.axes.set_xlim(t0, t0 + 5*self.period/self.t_div)
            self.axes.set_xlabel(f'delay time, relative to reference ({self.t_prefix}s)')
            self.axes.set_ylabel(f'voltage (V)')

        else:
            self.t_prefix, self.t_div = get_prefix(self.data[0].max() - self.data[0].min())
            if self.t_prefix is None:
                self.t_prefix = ""

            self.axes.set_xlabel(f'time ({self.t_prefix}s)')
            self.t = self.data[0] / self.t_div
            self.axes.set_ylabel(f'voltage (V)')

            for i in range(1, len(self.data)):
                label = {1: "reference", 2:"signal"}.get(i, None)
                self.axes.plot(self.t, self.data[i], '.', label=label)

            if hasattr(self, 'ref_fit'):
                self.axes.plot(self.t, self.ref_fit, 'k-', 'fit')
                self.axes.plot(self.t, self.sig_fit, 'k-')

                self.axes.legend()

        self.fig_canvas.draw()


def error_popup(e, ok=False):
    mb = QtWidgets.QMessageBox
    if isinstance(e, str):
        title = "error"
        text = e
        detail = none
    else:
        ec = e.__class__.__name__
        title = str(ec)
        text = str(ec) + ": " + str(e)
        detail = traceback.format_exc()

    msg = mb()
    msg.setIcon(mb.Critical)
    msg.setWindowTitle(title)
    msg.setText(text)
    if detail:
        msg.setDetailedText(detail)
    msg.setStyleSheet("QTextEdit {font-family: Courier; min-width: 600px;}")
    if ok:
        msg.setStandardButtons(mb.Cancel | mb.Ok)
    else:
        msg.setStandardButtons(mb.Cancel)
    return msg.exec_() == mb.Ok

class MainWindow(QtWidgets.QMainWindow):

    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)

        self.tabs = Tabs(self)
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("&File")

        open_action = QtWidgets.QAction('&Open', self)
        open_action.setShortcut('Ctrl+O')
        # openAction.setStatusTip('Open document')
        open_action.triggered.connect(self.open_file)
        self.file_menu.addAction(open_action)

        save_action = QtWidgets.QAction('&Save CSV', self)
        save_action.setShortcut('Ctrl+S')
        # openAction.setStatusTip('Open document')
        save_action.triggered.connect(self.save_file)
        self.file_menu.addAction(save_action)

        if HAS_VXI11:
            self.eth_menu = self.menu.addMenu('Ethernet')
            self.ETH_IP = False

            setup_action = QtWidgets.QAction("&Ethernet Setup", self)
            setup_action.setShortcut('Ctrl+E')
            setup_action.triggered.connect(self.ethernet_setup)
            self.eth_menu.addAction(setup_action)

            eth_action = QtWidgets.QAction("&Acquire", self)
            eth_action.setShortcut('Ctrl+A')
            eth_action.triggered.connect(self.ethernet_acquire)
            self.eth_menu.addAction(eth_action)

        self.setCentralWidget(self.tabs)

        # self.load_file("NewFile1.csv")
        # self.open_file()

    def ethernet_setup(self):
        while True:
            ip, ok = QtWidgets.QInputDialog.getText(self, 'Ethernet Setup',
                'Enter the IP address:', text = self.ETH_IP if self.ETH_IP else "")
            if ok:
                try:
                    idn = idn_eth(ip)
                    print(f'Scope at {ip} returned IDN:\n "{idn}"')
                except Exception as e:
                    self.ETH_IP = False
                    if not error_popup(e, True):
                        break
                else:
                    self.ETH_IP = ip
                    break
            else:
                break

    def ethernet_acquire(self):
        if not self.ETH_IP:
            self.ethernet_setup()

        if not self.ETH_IP:
            return

        try:
            data = load_eth(self.ETH_IP)
        except Exception as e:
            error_popup(e)
        else:
            if (not len(data)) or (len(data[0]) < 10):
                error_popup("Oscilloscope returned null data...")
            else:
                display = DataDisplay(self, data)
                self.tabs.add_tab(display, time.strftime('Eth: %H:%M:%S'))


    def open_file(self):
        fn, ext = QtWidgets.QFileDialog.getOpenFileName(self, 'Open Data',
            os.getcwd(), "CSV (*.csv)")
        if fn:
            self.load_file(fn)

    def load_file(self, fn):
        try:
            data = load_osc_csv(fn)
        except Exception as e:
            error_popup(e)
        else:
            display = DataDisplay(self, data)
            self.tabs.add_tab(display, os.path.split(fn)[1])

    def save_file(self):
        fn, ext = QtWidgets.QFileDialog.getSaveFileName(self, 'Save CSV Data',
            os.getcwd(), "CSV (*.csv)")
        if fn:
            self.tabs.current_tab().save_csv(fn)


def wavefit_qt_app():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    return app.exec_()


if __name__ == "__main__":
    wavefit_qt_app()
