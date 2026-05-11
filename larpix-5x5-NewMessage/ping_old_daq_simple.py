#!/usr/bin/env python3
import larpix
import larpix.io

c = larpix.Controller()
c.io = larpix.io.PACMAN_IO(relaxed=True, config_filepath='io/pacman.json')

# 1) High-level ping using old DAQ API
print(f"High-level ping using old DAQ API")
status = c.io.ping(io_group=5)
print(f"ping iog5: {status}")
