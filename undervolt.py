#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool for undervolting Intel CPUs under Linux
"""

import argparse
import logging
import os
import time
from itertools import cycle
from glob import glob
from struct import pack, unpack
from subprocess import check_output

PLANES = {
    'core': 0,
    'gpu': 1,
    'cache': 2,
    'uncore': 3,
    'analogio': 4,
    # 'digitalio': 5, # not working?
}
OPENSSL_COLS = ['16 bytes', '64 bytes', '256 bytes', '1024 bytes', '8192 bytes']


def write_msr(val, msr=0x150):
    """
    Use /dev/cpu/*/msr interface provided by msr module to read/write
    values from register 0x150.
    Writes to all msr node on all CPUs available.
    """
    n = glob('/dev/cpu/[0-9]*/msr')
    for c in n:
        logging.info("Writing {val} to {msr}".format(
            val=hex(val), msr=c))
        f = os.open(c, os.O_WRONLY)
        os.lseek(f, msr, os.SEEK_SET)
        os.write(f, pack('Q', val))
        os.close(f)
    if not n:
        raise OSError("msr module not loaded (run modprobe msr)")


def _read_msr(msr=0x150, cpu=0):
    """
    Read a value from single msr node on given CPU (defaults to first)
    Mailbox won't contain response until we write read command
    """
    n = '/dev/cpu/%d/msr' % (cpu,)
    f = os.open(n, os.O_RDONLY)
    os.lseek(f, msr, os.SEEK_SET)
    val = unpack('Q', os.read(f, 8))[0]
    logging.info("Read {val} from {n}".format(val=hex(val), n=n))
    os.close(f)
    return val


def read_msr(plane):
    """
    Write the 'read' value to mailbox, then re-read.
    """
    msg = pack_offset(plane)
    write_msr(msg)
    return _read_msr()


def convert_offset(mV):
    """
    Calculate offset part of MSR value
    :param mV: voltage offset
    :return hex string

    >>> from undervolt import convert_offset
    >>> convert_offset(-50)
    'f9a00000'

    """
    rounded_offset = int(round(mV*1.024))
    return format(convert_rounded_offset(rounded_offset), '08x')


def unconvert_offset(y):
    """ For a given offset, return a value in mV that could have resulted in
        that offset.

        Inverts y to give the input value x closest to zero for values x in
        [-1000, 1000]

    # Test that inverted values give the same output when re-converted.
    # NOTE: domain is [-1000, 1000] - other function, but scaled down by 1.024.
    >>> from undervolt import convert_offset, unconvert_offset
    >>> domain = [ 1000 - x for x in range(0, 2000) ]
    >>> result = True
    >>> for x in domain:
    ...     y  = int(convert_offset(x), 16)
    ...     x2 = round(unconvert_offset(y))
    ...     y2 = int(convert_offset(x2), 16)
    ...     if y != y2 or x != x2:
    ...         result = (x, y, x2, y2)
    ...         break
    >>> result
    True
    >>> unconvert_offset(0xf0000000)
    -125.0
    >>> unconvert_offset(0xf9a00000)
    -49.8046875
    """
    return unconvert_rounded_offset(y) / 1.024


def convert_rounded_offset(x):
    return 0xFFE00000 & ((x & 0xFFF) << 21)


def unconvert_rounded_offset(y):
    """
    >>> from undervolt import convert_offset, unconvert_offset
    >>> domain = [ 1024 - x for x in range(0, 2048) ]
    >>> all(x == \
          unconvert_rounded_offset(convert_rounded_offset(x)) for x in domain)
    True
    """
    x = y >> 21
    return x if x <= 1024 else - (2048 - x)


def pack_offset(plane, offset='0'*8):
    """
    Get MSR value that writes (or read) offset to given plane
    :param plane: voltage plane as string (e.g. 'core', 'gpu')
    :param offset: voltage offset as hex string (omit for read)
    :return value as long int ready to write to register

    # Write
    >>> from undervolt import pack_offset
    >>> format(pack_offset('core', 'ecc00000'), 'x')
    '80000011ecc00000'
    >>> format(pack_offset('gpu', 'f0000000'), 'x')
    '80000111f0000000'

    # Read
    >>> format(pack_offset('core'), 'x')
    '8000001000000000'
    >>> format(pack_offset('gpu'), 'x')
    '8000011000000000'

    """
    return int("0x80000{plane}1{write}{offset}".format(
        plane=PLANES[plane],
        write=int(offset is not '0'*8),
        offset=offset,
    ), 0)


def get_offset(plane):
    """
    Gets the voltage offset for given plane
    """
    msr_value = read_msr(plane)
    return unconvert_offset(msr_value)


def set_offset(plane, mV):
    """"
    Set given voltage plane to offset mV
    Raises SystemExit if re-reading value returns something different
    """
    logging.info('Setting {plane} offset to {mV}mV'.format(
        plane=plane, mV=mV))
    target = convert_offset(mV)
    write_value = pack_offset(plane, target)
    write_msr(write_value)
    # now check value set correctly
    read = format(read_msr(plane), '08x')
    if read != target:
        logging.error("Failed to set {p}: expected {t}, read {r}".format(
            p=plane, t=target, r=format(read, '08x')))
        raise SystemExit(1)


def set_offsets(settings):
    """Map set_offset over {plane: offset} dict"""
    for plane, voltage in settings.items():
        set_offset(plane, voltage)


def get_offsets(planes=PLANES.keys()):
    """Map get_offset over list of planes"""
    return {plane: get_offset(plane) for plane in planes}


def running_stats():
    """
    Calculate running mean and deviation
    >>> from undervolt import running_stats
    >>> stats = running_stats()
    >>> stats.next()
    >>> stats.send(1)
    (1.0, 0.0)
    >>> stats.send(10)
    (5.5, 20.25)
    >>> stats.send(100)
    (37.0, 1998.0)
    >>> stats.next()
    (37.0, 1998.0)
    """
    v = yield
    s = m = n = 0.0
    while True:
        n = n + 1
        m_prev = m
        m = m + ((v - m) / n)
        s = s + (v - m) * (v - m_prev)
        v = yield (m, s / n)


def compare(output):
    """
    Parse the output of openssl bench and calculate mean
    Input should be alternating lines to compare
    >>> from undervolt import compare
    >>> data = os.linesep.join([ \
    '325407.75k,341788.78k,345426.86k,349811.03k,342887.08k', \
    '296018.49k,308396.16k,306790.66k,307006.81k,309996.20k', \
    '318500.87k,346368.28k,338557.95k,343658.84k,342239.91k', \
    '271927.80k,298474.60k,302083.16k,300563.80k,287926.95k', \
    ])
    >>> compare(data)
    """
    stats_a = [running_stats() for _ in range(len(OPENSSL_COLS))]
    stats_b = [running_stats() for _ in range(len(OPENSSL_COLS))]
    map(next, stats_a + stats_b)
    for row, stat_gens in zip(output.splitlines(), cycle((stats_a, stats_b))):
        results = [float(s.strip('k')) for s in row.split(',')[2:]]
        _results = [gen.send(r) for r, gen in zip(results, stat_gens)]

    for (col, ((m_a, v_a), (m_b, v_b))) in zip(OPENSSL_COLS, stats_a, stats_b):
        percentage = (m_a / m_b) * 100
        print('{}: {:.2d}% (+-{})'.format(
            col, percentage, v_b
        ))


def benchmark(settings, iterations, cooldown, multi):
    """
    Repeatedly run benchmark while applying and removing settings.
    Outputs CSV table of offsets and benchmark results.
    """
    command = [ 'openssl', 'speed', 'aes-128-cbc' ] + \
                (['-multi', multi ] if multi else [])
    null_settings = dict((p, 0) for p in settings)
    print(",".join(settings.keys() + OPENSSL_COLS))
    for offsets in (settings, null_settings) * iterations:
        logging.info("Setting offsets: {}".format(offsets))
        set_offsets(offsets)
        output = check_output(command)
        stats = summary(output)
        results = output.splitlines()[-1].split()[2:]
        voltages = [str(v) for v in offsets.values()]
        print(','.join(voltages + results))
        time.sleep(cooldown)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', help='command',
                        choices=('get', 'set', 'benchmark'))
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="print debug info")
    parser.add_argument('-f', '--force', action='store_true',
                        help="allow setting positive offsets")

    # benchmark options
    parser.add_argument('-i', '--iterations', type=int, default=10,
                        help="number of benchmark iterations to run")
    parser.add_argument('-c', '--cooldown', type=int, default=30,
                        help="number of seconds cooldown between tests")
    parser.add_argument('-m', '--multicore', type=int, default=1,
                        help="argument for openssl -multi")

    for plane in PLANES:
        parser.add_argument('--{}'.format(plane), type=int, help="offset (mV)")

    # parse args
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    voltage_settings = {plane: getattr(args, plane)
                        for plane in PLANES
                        if getattr(args, plane, None) is not None}

    if any(o > 0 for o in voltage_settings.values()) and not args.force:
        raise ValueError("Use --force to set positive offset")

    if args.command == 'get':
        for plane, voltage in get_offsets().items():
            print('{}: {:.2f} mV'.format(plane, voltage))

    if args.command == 'set':
        set_offsets(voltage_settings)

    if args.command == 'benchmark':
        benchmark(voltage_settings, args.iterations, args.cooldown, str(args.multicore))

if __name__ == '__main__':
    main()
