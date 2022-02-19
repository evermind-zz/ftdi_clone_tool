#!/usr/bin/env python2
# FTDI Clone Tool v0.2 by @marcan42
# Licensed under the terms of the 2-clause BSD license, which follow:
#
# Copyright (c) 2014 Hector Martin <hector@marcansoft.com>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys, struct
try:
    import usb
except ImportError:
    print("Error: please install PyUSB. The package is called python-usb in Ubuntu.")
    sys.exit(1)

def find_device():
    busses = usb.busses()
    found = 0
    for bus in busses:
        devices = bus.devices
        for dev in devices:
            if (dev.idVendor == 0x0403
                and dev.idProduct in (0x6001, 0x0000)
                and dev.deviceVersion.split(".")[0] == "06"):
                print("Found FTDI FT232R device (%04x:%04x)" % (dev.idVendor, dev.idProduct))
                found_dev = dev
                found += 1

    if found == 0:
        print("No devices found")
        sys.exit(1)
    if found > 1:
        print("More than one device found. Please connect only one FTDI device.")
        sys.exit(1)
    return found_dev

class FTDIDevice(object):
    def __init__(self, usbdev):
        self.handle = usbdev.open()
        self.timeout = 100

    def unlock_eeprom(self):
        self.handle.controlMsg(requestType=0x40,
                               request=0x09,
                               value=0x77,
                               index=1,
                               buffer="",
                               timeout=self.timeout)

    def read_eeprom(self, addr):
        data = self.handle.controlMsg(requestType=0xc0,
                                      request=0x90,
                                      value=0,
                                      index=addr,
                                      buffer=2,
                                      timeout=self.timeout)
        assert len(data) == 2
        return data[0] | (data[1] << 8)

    def write_eeprom(self, addr, data):
        self.handle.controlMsg(requestType=0x40,
                               request=0x91,
                               value=data,
                               index=addr,
                               buffer="",
                               timeout=self.timeout)

    def calc_checksum(self, eeprom):
        check = 0xaaaa
        for i in eeprom[:0x3f]:
            check = check ^ i
            check = ((check << 1) | (check >> 15)) & 0xffff
        return check

    def forge_checksum(self, eeprom):
        check = 0xaaaa
        for i in eeprom[:0x3e]:
            check = check ^ i
            check = ((check << 1) | (check >> 15)) & 0xffff
        check ^= ((eeprom[0x3f] >> 1) | (eeprom[0x3f] << 15)) & 0xffff
        return check

def main():
    print("Detecting device...")
    dev = FTDIDevice(find_device())
    dev.unlock_eeprom()
    print("Reading EEPROM...")
    eeprom = [dev.read_eeprom(i) for i in range(0x40)]
    print("EEPROM contents:")
    for i in range(0, 0x40, 8):
        print("  " + " ".join("%04x" % j for j in eeprom[i:i+8]))
    check = dev.calc_checksum(eeprom)
    checksum_correct = check == eeprom[0x3f]
    if checksum_correct:
        print("  EEPROM checksum: %04x (correct)" % eeprom[0x3f])
    else:
        print("  EEPROM checksum: %04x (incorrect, expected %04x)" % (eeprom[0x3f], check))

    print("Detecting clone chip...")
    old_value = eeprom[0x3e]
    print("  Current EEPROM value at 0x3e: %04x" % old_value)
    new_value = (old_value + 1) & 0xffff
    print("  Writing value: %04x" % new_value)
    dev.write_eeprom(0x3e, new_value)
    read_value = dev.read_eeprom(0x3e)
    print("  New EEPROM value at 0x3e: %04x" % read_value)
    if read_value != old_value:
        print("  Reverting value: %04x" % old_value)
        dev.write_eeprom(0x3e, old_value)

    if read_value == old_value:
        print("Chip is GENUINE or a more accurate clone. EEPROM write failed.")
        print("Nothing else to do.")
        return 0

    print('====================================================================')
    print('Chip is a CLONE or not an FT232RL. EEPROM write succeeded.')

    if checksum_correct:
        if eeprom[2] == 0:
            print('====================================================================')
            print("Your device has a Product ID of 0, which likely means that it")
            print("has been bricked by FTDI's malicious Windows driver.")
            print
            print("Do you want to fix this?")
            print(" - Type YES (all caps) to continue.")
            print(" - Type anything else (or just press enter) to exit.")
            ret = raw_input("> ")
            if ret != "YES":
                print("No changes made.")
                return 0
            # Try to undo what the FTDI driver did. If it corrupted the value at
            # 0x3e (if it wasn't unused), this should fix it, assuming the
            # checksum at 0x3f is correct for the right value.
            eeprom[0x02] = 0x6001
            eeprom[0x3e] = dev.forge_checksum(eeprom)
            dev.write_eeprom(0x02, eeprom[0x02])
            dev.write_eeprom(0x3e, eeprom[0x3e])

            if eeprom[0x3e] == 0:
                print("Product ID restored to 0x6001. All changes made by FTDI's driver")
                print("have been reverted.")
            else:
                print("Product ID restored to 0x6001. However, the value at 0x3e has not")
                print("been set to zero. Reasons why this may have happened:")
                print(" - The PID was set to 0 by other means, not FTDI's driver.")
                print(" - The original PID was not 0x6001")
                print(" - The PID was set to 0 by FTDI's driver, then fixed with")
                print("   another tool, then set to 0 again by FTDI's driver.")
                print(" - Your device has very long vendor/product/serial number strings,")
                print("   and FTDI's driver may have accidentally corrupted the last")
                print("   character. If this is the case, it has been restored.")
                print(" - You or your software have used the EEPROM's free/user area and")
                print("   FTDI's driver has corrupted the last word. If this is the case,")
                print("   it has been restored.")
                print(" - For some other reason the free area of your EEPROM was not")
                print("   filled with zeros.")
                print("This is probably harmless, but you may want to take note.")

            print("Press enter to continue.")
            raw_input()

        print("====================================================================")
        print("Deliberately corrupting the checksum of your device\'s EEPROM will")
        print("protect it from being bricked by the malicious FTDI Windows driver,")
        print("while still functioning with said driver. However, if you do this,")
        print("ALL SETTINGS WILL REVERT TO DEFAULTS AND THE DEVICE SERIAL NUMBER")
        print("WILL NO LONGER BE VISIBLE. Most devices that use the FT232 as a")
        print("standard USB-serial converter will function with default settings,")
        print("though the LEDs on some converters might be inverted. Specialty")
        print("devices, devices which use bitbang mode, and devices which use")
        print("GPIOs or nonstandard control signal configurations may cease to")
        print("work properly. If you are NOT 100% certain that this is what you")
        print("want, please do not do this. YOU HAVE BEEN WARNED. You can revert")
        print("this change by using this tool again.")
        print
        print(" - Type CORRUPTME (all caps) to set an invalid EEPROM checksum.")
        print(" - Type anything else (or just press enter) to exit.")
        ret = raw_input("> ")
        if ret != "CORRUPTME":
            print("EEPROM checksum left unchanged.")
            return 0

        if eeprom[0x3f] == 0xdead:
            # Bad luck!
            dev.write_eeprom(0x3f, 0xbeef)
        else:
            dev.write_eeprom(0x3f, 0xdead)

        print("EEPROM checksum corrupted. Run this tool again to revert the change.")
        print("Disconnect and reconnect your device for the changes to take effect.")
        print("Press enter to exit.")
        raw_input()
        return 0
    else:
        print("====================================================================")
        print("Your device has an incorrect EEPROM checksum, probably because you")
        print("ran this tool to do so, with the intent of protecting your device")
        print("from the malicious Windows driver.")
        print
        print(" - Type FIXME (all caps) to restore your EEPROM checksum.")
        print(" - Type anything else (or just press enter) to exit.")
        ret = raw_input("> ")
        if ret != "FIXME":
            print("EEPROM checksum left unchanged.")
            return 0

        dev.write_eeprom(0x3f, check)
        print("EEPROM checksum corrected. Disconnect and reconnect your device for")
        print("the changes to take effect. Press enter to exit.")
        raw_input()

if __name__ == "__main__":
    sys.exit(main())
