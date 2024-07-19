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

import vxi11
import re
import numpy as np

def convert_raw(raw, dtype='u1'):
    if raw[0:1] != b'#':
        raise ValueError(f'First byte of raw data should be #, found {chr(dat[0])}')
    N_head = int(raw[1:2])
    N_points = int(raw[2:2+N_head])

    return np.frombuffer(raw[2+N_head:2+N_head+N_points], dtype=dtype)


class TBS2000B:
    def __init__(self, inst):
        self.inst = inst

        self.error_byte(False) # Clear error bits
        inst.write('WFMO:ENC BIN')
        self.error_byte()

    def error_byte(self, raise_err=True):
        err = int(self.inst.ask('*ESR?'))
        if err and raise_err:
            raise RuntimeError(f'Oscilloscope returned error byte: {err}')
        return err

    def run(self):
        self.inst.write('ACQ:STATE RUN')

    def is_running(self):
        return self.inst.ask('ACQ:STATE?').startswith('1')

    def stop(self):
        self.inst.write('ACQ:STATE STOP')

    def read_channel(self, channel=1):
        if isinstance(channel, int):
            channel = f'CH{channel}'

        self.inst.write('DATA INIT')
        self.inst.write('DATA:SOU ' + channel)

        fmt = self.inst.ask('WFMO?').split(';')
        dtype = ('i' if fmt[3] == 'RI' else 'u') + fmt[0]        
        t_inc = float(fmt[9])
        t_off = float(fmt[10])
        V_inc = float(fmt[13])
        V_off = float(fmt[14])
        self.inst.write('CURV?')
        raw = self.inst.read_raw()
        self.error_byte()

        V = (convert_raw(raw, dtype) - V_off) * V_inc
        t = np.arange(len(V)) * t_inc + t_off

        return t, V
    
    def read_channels(self, channels):
        running = self.is_running()

        if running:
            self.stop()

        output = []

        for channel in channels:
            t, V = self.read_channel(channel)
            
            if not output:
                output.append(t)
            
            output.append(V)

        if running:
            self.run()

        return tuple(output)
    
    def __bool__(self):
        return True

def get_oscope(inst):
    if not isinstance(inst, vxi11.vxi11.Instrument):
        inst = vxi11.Instrument(inst)
        inst.timeout = 1

    idn = inst.ask('*IDN?')

    if re.match('TEKTRONIX,TBS(2\d\d2)B', idn):
        return TBS2000B(inst)
    else:
        raise ValueError(f"Unkonwn Oscilloscope ID: '{idn}'")

    return idn
