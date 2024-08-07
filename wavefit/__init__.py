#!/usr/bin/python3
# -*- coding: utf-8 -*-#
#
# Copyright 2024 Dustin Kleckner
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
    from .oscope import get_oscope


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
        raise RuntimeError("VXI11 not installed; can't load data over ethernet!\n(to install, run: pip install python-vxi11)")

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
