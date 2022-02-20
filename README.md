From https://www.eevblog.com/forum/reviews/ftdi-driver-kills-fake-ftdi-ft232/msg537012/#msg537012

Ftdi ft232

What does this tool?:
* Tell you if you have a clone chip
* Fix bricked clones (by undoing exactly what the FTDI driver did, restoring the PID to 6001 but also reverting the value at 0x3e - this might fix string data corruption if your strings area was full when the FTDI driver did its dirty work, or if user data was in use)
* NEW: immunize clone chips against the evil driver by deliberately breaking the EEPROM checksum. This reverts all settings to defaults (and loses the serial number), but if those work for you, then FTDI's driver will not brick your device and will happily work with it. You can also revert this change.

Tested on both real devices (where it refuses to do anything) and on clones (where all of the above works; I tested it against FTDI's driver too).
