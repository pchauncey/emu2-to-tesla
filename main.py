#!/usr/bin/env python3

import asyncio
import aioserial
import json
import re
import teslapy
from time import sleep


# load json config file
def get_config(key):
    with open('config.json', 'r') as file:
        data = json.load(file)
    file.close()
    return data[key]


# get car status data
def get_data(self):
    return self.get_vehicle_data()


# start charging
def start_charge(self):
    self.command('START_CHARGE')
    return


# stop charging
def stop_charge(self):
    self.command('STOP_CHARGE')
    return


# set charge rate limit in amps
def charging_amps(self, amps):
    self.command('CHARGING_AMPS', charging_amps=amps)
    return


# read current smart meter data
async def emu_serial_read():
    rf_xml_block = ''
    rf_enabled_write = 0

    try:
        aioserial_instance: aioserial.AioSerial = aioserial.AioSerial(
            port="/dev/ttyACM0",
            baudrate=115200,
            write_timeout=0)
        await aioserial_instance.write_async(
            b'<Command><Name>get_instantaneous_demand</Name>[<Refresh>Y</Refresh>]</Command>\n')
    except (OSError, IOError) as e:
        print("Serial port error:", e)
        return

    while True:
        try:
            line: bytes = await aioserial_instance.readline_async()
        except (OSError, IOError) as e:
            print("Serial port error:", e)
            return

        # once the first line detected, we start recording all following lines
        if b'<InstantaneousDemand>\r\n' in line:
            rf_enabled_write = 1

        if rf_enabled_write:
            rf_xml_block = rf_xml_block + str(line, 'utf-8').rstrip('\r\n')
        # once the last line detected, we stop recording the lines and return the XML block
        if b'</InstantaneousDemand>\r\n' in line:
            return (rf_xml_block)


# return signed integer from unsiged hex
def s16(value):
    return -(value & 0x8000) | (value & 0x7fff)


# main routine
async def main():


    # instantiate tesla object
    print("Starting tesla API object... ", end="")
    tesla = teslapy.Tesla(get_config("account"))
    print("done.")

    # main loop
    while True:
        volts = get_config("volts")
        loop_seconds = get_config("loop_seconds")

        if not tesla.authorized:
            print('Use browser to login. Page Not Found will be shown at success.')
            print('Open this URL: ' + tesla.authorization_url())
            tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))

        # loop through vehicles
        for vehicle in tesla.vehicle_list():
            print("Getting vehicle data... ", end="")
            car_state = get_data(vehicle)
            print("done.")

            # only do all stuff at home:
            try:
                home_lat = get_config("home_lat")
                home_long = get_config("home_long")
                if not str(home_lat) in str(car_state['drive_state']['latitude']) and not str(home_long) in str(car_state['drive_state']['longitude']):
                    print("car isn't here")
                    sleep(loop_seconds)
                    continue
            except:
                print("except")

            # set charge state:
            if car_state['charge_state']['charging_state'] == "Charging":
                charge_amps = int(car_state['charge_state']['charge_current_request'])
                print("api says: currently charging at " + str(charge_amps) + " amps.")
                state = True
            else:
                charge_amps = 0
                print("api says: not currently charging at " + str(charge_amps) + " amps.")
                state = False

            # pull energy info from smart meter
            try:
                emu = await emu_serial_read()
                findhex = re.findall('<Demand>(.*)</Demand>', emu)[0]
                cur_watts = s16(int(findhex, 16))
            except ValueError:
                sleep(10)
                continue
            except IndexError:
                sleep(10)
                continue

            if cur_watts <= 0:
                excess_amps = abs(int(round(cur_watts/volts, 0)))
            else:
                excess_amps = -(abs(int(round(cur_watts/volts, 0))))

            print("excess amps: " + str(excess_amps) + " current state: " + str(state))

            # car is fully charged
            if car_state['charge_state']['charging_state'] == "Complete":
                print("car is already full")
                state = False
                charge_amps = 0
                charging_amps(vehicle, charge_amps)
                stop_charge(vehicle)
                sleep(loop_seconds)
                continue
            # car isn't plugged in
            elif car_state['charge_state']['charging_state'] == "Disconnected":
                print("car not plugged in")
                sleep(loop_seconds)
                continue
            elif car_state['charge_state']['charging_state'] == "Charging":
                state = True


            # we have extra energy
            if excess_amps > 0:
                max = get_config("max_amps")

                # we have energy to add to existing charge:
                if state is True and excess_amps > 0:
                    charge_amps += excess_amps
                    if charge_amps > max:
                        print("setting to max amps: " + str(max))
                        charge_amps = max
                    else:
                        print("adding " + str(excess_amps) + " amps. charge set to " + str(charge_amps))
                    charging_amps(vehicle, charge_amps)

                # more power!
                if state is not True and excess_amps > 0:
                    print("starting charge at " + str(excess_amps) + " amps")
                    charge_amps = excess_amps
                    if charge_amps > max:
                        print("setting to max amps: " + str(max))
                        charge_amps = max
                    charging_amps(vehicle, charge_amps)
                    start_charge(vehicle)
                    # need to hit api twice below 5 amps
                    if charge_amps < 5:
                        sleep(2)
                        charging_amps(vehicle, charge_amps)
                    state = True
                sleep(loop_seconds)
                continue

            else:

                # we're charging and drawing more than we're producing
                if state is True and excess_amps < 0:
                    charge_amps += excess_amps
                    if (charge_amps) < 1:
                        # we're out of excess power
                        print("stopping charge")
                        charging_amps(vehicle, 0)
                        charge_amps = 0
                        state = False
                        stop_charge(vehicle)
                    else:
                        # ratchet down:
                        print("reducing by " + str(abs(excess_amps)) + " amps")
                        charging_amps(vehicle, charge_amps)
                        # need to hit api twice below 5 amps
                        if charge_amps < 5:
                            sleep(2)
                            charging_amps(vehicle, charge_amps)

            sleep(loop_seconds)
            continue


if __name__ == "__main__":
    asyncio.run(main())
