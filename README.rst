*Warning!*

*This program is untested (apart from by myself) and it may damage your hardware! Use at your own risk.*

==================
undervolt |travis|
==================

.. |travis| image:: https://travis-ci.org/georgewhewell/undervolt.svg
    :target: https://travis-ci.org/georgewhewell/undervolt
    :alt: Build Status

*undervolt* is a program for undervolting Intel CPUs under Linux. It works in
a similar manner to the Windows program *ThrottleStop* (i.e, `MSR 0x150`). You
can apply a fixed voltage offset to one of 5 voltage planes.

For more information, read
`here <https://github.com/mihic/linux-intel-undervolt>`_.

Installing
----------

From PyPi::

    $ pip install undervolt

From source::

    $ git clone https://github.com/georgewhewell/undervolt.git

Examples
--------

Read current offsets::

    $ undervolt get
    core: 0.0 mV
    gpu: -19.53 mV
    cache: -30.27 mV
    uncore: -29.3 mV
    analogio: -70.31 mV

Apply -100mV offset to CPU Core and Cache::

    $ undervolt set --core -100 --cache -100

Apply -75mV offset to GPU, -100mV to all other planes::

    $ undervolt set --gpu -75 --core -100 --cache -100 --uncore -100 --analogio -100

Usage
-----

.. code-block:: bash

    $ undervolt -h
    usage: undervolt.py [-h] [-v] [-f] [--core CORE] [--cache CACHE]
                        [--analogio ANALOGIO] [--uncore UNCORE] [--gpu GPU]
                        {get,set}
    positional arguments:
      {get,set}            command
    optional arguments:
      -h, --help           show this help message and exit
      -v, --verbose        print debug info
      -f, --force          allow setting positive offsets
      --core CORE          offset (mV)
      --cache CACHE        offset (mV)
      --analogio ANALOGIO  offset (mV)
      --uncore UNCORE      offset (mV)
      --gpu GPU            offset (mV)

Hardware support
----------------

Undervolting should work on any CPU later then Haswell.

===================== ========= ==========
      System             CPU     Working?
===================== ========= ==========
Lenovo X1 Yoga Gen 2  i7-7600U  Yes
Dell Xps 15 9550      i7-6700HQ Yes
===================== ========= ==========

Credit
------
This project is trivial wrapper around the work of others from the following resources:

- https://github.com/mihic/linux-intel-undervolt
- http://forum.notebookreview.com/threads/undervolting-e-g-skylake-in-linux.807953
- https://forums.anandtech.com/threads/what-controls-turbo-core-in-xeons.2496647

Many thanks to all who contributed.
