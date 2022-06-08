from . import *
import matplotlib
matplotlib.use('Qt5Agg')

from PyQt5 import QtCore, QtWidgets, QtGui
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure


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
            print(freq_precision)
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
        self.setCentralWidget(self.tabs)

        # self.load_file("NewFile1.csv")
        self.open_file()


    def open_file(self):
        fn, ext = QtWidgets.QFileDialog.getOpenFileName(self, 'Open Data',
            os.getcwd(), "CSV (*.csv)")
        if fn:
            self.load_file(fn)

    def load_file(self, fn):
        try:
            data = load_osc_csv(fn)
        except Exception as e:
            ec = e.__class__.__name__
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle(str(ec))
            msg.setText(str(ec) + ": " + str(e))
            msg.setDetailedText(traceback.format_exc())
            msg.setStyleSheet("QTextEdit {font-family: Courier; min-width: 600px;}")
            msg.setStandardButtons(QMessageBox.Cancel)
            msg.exec_()
        else:
            display = DataDisplay(self, data)
            self.tabs.add_tab(display, os.path.split(fn)[1])


def wavefit_qt_app():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    w = MainWindow()
    w.show()
    return app.exec_()
