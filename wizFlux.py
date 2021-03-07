import asyncio
import logging
import os
from datetime import datetime, timedelta
# Using https://github.com/sbidy/pywizlight
from pywizlight import wizlight, PilotBuilder, discovery, exceptions
from random import sample
from systemd.journal import JournalHandler

# Lowest possible color temp is 2200k
# Highest possible color temp is 6500k

L1_IP = "192.168.1.115"
L2_IP = "192.168.1.116"
L3_IP = "192.168.1.145"
L1 = wizlight(L1_IP)  # Overhead light 1
L2 = wizlight(L2_IP)  # Overhead light 2
L3 = wizlight(L3_IP)  # Overhead light 3
LIGHTS = [L1_IP, L2_IP, L3_IP]

SCHEDULE = [
    ('05:00', 2200),
    ('06:00', 4600),
    ('18:00', 4600),
    ('22:00', 3000),
    ('23:30', 2200),
]

LOG = logging.getLogger(__name__)
LOG.addHandler(JournalHandler())
LOG.setLevel(logging.DEBUG)

# These should match the index of the values in the schedule
TIME_INDEX = 0
TEMP_INDEX = 1
SCHEDULE_TIME_FORMAT = '%H:%M'

SECS_BETWEEN_LIGHT_UPDATES = 60

# STATES:
STATE_LIGHT_OFF = 1
STATE_INFLECTION = 2  # TODO: Inflection shouldn't be a point. Make a "calcTemp() function"
STATE_TRANSITION = 3

# Some globals
prev_temp_time = '00:01'
prev_temp = 0
next_temp_time = '00:02'
next_temp = 0

curr_state = STATE_INFLECTION
prev_state = 0
last_temp = 0

async def state_machine_run():
    global curr_state
    global prev_state
    global last_temp
    if prev_state != curr_state:
        LOG.info("State changing, from {} to {}".format(prev_state, curr_state))
        prev_state = curr_state

    if curr_state == STATE_LIGHT_OFF:
        LOG.info("Light is off...")
        # TODO: Come up with a way to listen for the device connecting to Wifi, somehow.
        #       Something more efficient than pinging, at least...
        # TODO: See if the bulbs can support RGBCW commands... Modify the library

        # Ping a random light and see if we get a response.
        pinged = ping_light(sample(LIGHTS, 1)[0])
        if pinged:
            curr_state = STATE_INFLECTION  # We're back baybee!
        else:
            await asyncio.sleep(1)  # Sleep and ping again.

    elif curr_state == STATE_INFLECTION:
        LOG.debug("Calculating new values!")
        update_temp_targets()
        LOG.debug("Prev checkpoint: {} {}".format(prev_temp_time, prev_temp))
        LOG.debug("Next checkpoint: {} {}".format(next_temp_time, next_temp))
        curr_state = STATE_TRANSITION
        await asyncio.sleep(1)

    elif curr_state == STATE_TRANSITION:
        LOG.debug("Adjusting color temp!")

        now = datetime.now()
        time_since_last_point = (now - prev_temp_time).total_seconds()
        time_to_next_point = (next_temp_time - now).total_seconds()
        if time_to_next_point <= 0:
            curr_state = STATE_INFLECTION  # After we update the next time, change states
        LOG.debug("time_since_last_point {}".format(time_since_last_point))
        LOG.debug("time_to_next_point {}".format(time_to_next_point))
        percent_transitioned = time_since_last_point / (time_to_next_point + time_since_last_point)
        LOG.debug("percent_transitioned {}".format(percent_transitioned))
        color_temp_delta = prev_temp - next_temp
        current_color_temp = prev_temp - (color_temp_delta * percent_transitioned)
        LOG.debug("current_color_temp {}".format(current_color_temp))
        temp_to_set = round(current_color_temp)
        if False: # last_temp == temp_to_set:
            # TODO: We should get the color temp of the light instead of not doing anything.
            #       If lights are not the right color, then send the update.
            LOG.debug("Not changing light color!")
        else:
            LOG.info("Setting temp {}".format(temp_to_set))
            success = await set_color_temp(temp_to_set)
            if success:
                last_temp = temp_to_set
            else:
                LOG.info("LIGHTS TURNED OFF!")
                curr_state = STATE_LIGHT_OFF
                last_temp = 0
                return # Break out immediately; don't sleep
        await asyncio.sleep(SECS_BETWEEN_LIGHT_UPDATES)

    else: # Undefined state machine state
        LOG.critical("SYSTEM IN BAD STATE, ABORTING")
        quit()


async def main():
    LOG.info("Starting WizLightControl")
    while(True):
        await state_machine_run()
        LOG.debug("---------------------------------")
    LOG.critical("Quitting")
    quit()


def update_temp_targets():
    now = datetime.now()
    current_time = now.strftime(SCHEDULE_TIME_FORMAT)
    for i in range(len(SCHEDULE)):
        if SCHEDULE[i][TIME_INDEX] > current_time:
            # Found the right range!
            populate_targets(i-1, i)
            return
    # At this point, we will have returned *UNLESS* the next transition is tomorrow morning.
    populate_targets(len(SCHEDULE)-1, 0)


def populate_targets(index_of_prev, index_of_next):
    global prev_temp_time
    global prev_temp
    global next_temp_time
    global next_temp
    prev_temp_time = parse_time_from_schedule(SCHEDULE[index_of_prev][TIME_INDEX], False)
    prev_temp = SCHEDULE[index_of_prev][TEMP_INDEX]
    next_temp_time = parse_time_from_schedule(SCHEDULE[index_of_next][TIME_INDEX], True)
    next_temp = SCHEDULE[index_of_next][TEMP_INDEX]


def parse_time_from_schedule(str_time, parsed_time_is_future):
    """
    Given a string time in the format of SCHEDULE_TIME_FORMAT = '%H:%M'
    and a boolean value stating if that time is in the future or not, convert
    that string into a datetime object.
    Some examples, assuming it is 17:00 on March 2:
    16:00, False ==> 16:00 March 2
    16:00, True  ==> 16:00 March 3
    18:00, True  ==> 18:00 March 2
    18:00, False ==> 18:00 March 1
    """
    now = datetime.now()
    time_obj = datetime.strptime(str_time, SCHEDULE_TIME_FORMAT)
    parsed_time = now.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
    if now < parsed_time and not parsed_time_is_future:
        parsed_time = parsed_time - timedelta(days=1)
    if now > parsed_time and parsed_time_is_future:
        parsed_time = parsed_time + timedelta(days=1)
    return parsed_time


def ping_light(light_ip):
    LOG.debug("Pinging {}".format(light_ip))
    response = os.system("ping -c 1 " + light_ip)
    # and then check the response...
    return (response == 0)


async def set_color_temp(temp):
    try:
        await asyncio.gather(
        L1.turn_on(PilotBuilder(colortemp = temp)),
        L2.turn_on(PilotBuilder(colortemp = temp)),
        L3.turn_on(PilotBuilder(colortemp = temp)))
        return True
    except exceptions.WizLightTimeOutError:
        LOG.debug("Bulb connection errors! Are they turned off?")
    return False


loop = asyncio.get_event_loop()
loop.run_until_complete(main())
