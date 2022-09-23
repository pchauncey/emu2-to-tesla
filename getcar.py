#!/usr/bin/env python3

# prints out json config for cars in your tesla account

import json
import teslapy


# load json config file
def get_config(key):
    with open('config.json', 'r') as file:
        data = json.load(file)
    file.close()
    return data[key]


# get car status data
def get_data(self):
    return self.get_vehicle_data()

# main routine
def main():
        # instantiate tesla object
        tesla = teslapy.Tesla(get_config("account"))
        if not tesla.authorized:
            print('Use browser to login. Page Not Found will be shown at success.')
            print('Open this URL: ' + tesla.authorization_url())
            tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))

        # loop through vehicles
        for vehicle in tesla.vehicle_list():
            car_state = get_data(vehicle)
            print(car_state)


if __name__ == "__main__":
    main()
