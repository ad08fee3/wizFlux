import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
# Using https://github.com/sbidy/pywizlight
from pywizlight import wizlight, PilotBuilder, discovery, exceptions
from random import sample

# TODO: Add typing
# TODO: How to see logs for the pywizlight library
# TODO: Logging is now non-ideal. Look into proper logging methods.
# TODO: Installation is a bit borked. A few too many manual steps. And it's probably not best practice.

# Highest possible color temp is 6500k
# Lowest possible color temp is 2200k
# But using some RGB trickery, we can go lower! Unfortunately, things get confusing close to
# the low end. For ease of programming, I am saying 0k is 100% red LED and nothing else.
# Now you can set a custom color and it will hold! Just turn off the lights for 10 secs or set the lights
# to the custom "magic" scene color listed below and it will resume normal operations.

L1_IP = "192.168.69.101"
L2_IP = "192.168.69.102"
L3_IP = "192.168.69.103"
LIGHT_IPS = [L1_IP, L2_IP, L3_IP]
L1 = wizlight(L1_IP)  # Overhead light 1
L2 = wizlight(L2_IP)  # Overhead light 2
L3 = wizlight(L3_IP)  # Overhead light 3
LIGHTS = [L1, L2, L3]

SCHEDULE = [
    ('01:00', 1400),
    ('04:00', 1400),
    ('05:00', 2200),
    ('06:00', 6000),
    ('09:30', 5400),
    ('11:00', 4600),
    ('18:00', 4600),
    ('22:00', 3000),
    ('23:00', 2200),
]

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.StreamHandler(sys.stdout))

# CHANGE LOG LEVEL HERE:
LOG.setLevel(logging.INFO)

# These should match the index of the values in the schedule
TIME_INDEX = 0
TEMP_INDEX = 1
SCHEDULE_TIME_FORMAT = '%H:%M'

SECS_BETWEEN_LIGHT_UPDATES = 60

# LIGHT STATES:
STATE_LIGHT_OFF = 1
STATE_ON = 2
STATE_CUSTOM_COLOR = 3

# Some globals
prev_temp_time = '00:01'
prev_temp = 0
next_temp_time = '00:02'
next_temp = 0
START_STATE = STATE_LIGHT_OFF
curr_state = START_STATE
prev_state = 0
last_temp = 0
in_rgb_mode = False
last_temp_update_time = datetime.now() - timedelta(days=1)  # Start with some old value
current_color_temp = 0

# Used to "reset" from a custom color back to WizFlux
MAGIC_RED = 0
MAGIC_GREEN = 47
MAGIC_BLUE = 9

async def state_machine_run():
    global curr_state
    global prev_state
    global last_temp
    if prev_state != curr_state:
        LOG.info("State changing, from {} to {}".format(prev_state, curr_state))
        prev_state = curr_state

    if curr_state == STATE_LIGHT_OFF:
        """
        During this state, ping a randomly-selected light to see if it's online yet.
        Transitions to STATE_ON if the light comes back online.
        """
        LOG.info("Light is off...")
        # TODO: Come up with a way to listen for the device connecting to Wifi, somehow.
        #       Something more efficient than pinging, at least...
        # TODO: See if the bulbs can support RGBCW commands... Modify the library

        # Ping a random light and see if we get a response.
        pinged = ping_light(sample(LIGHT_IPS, 1)[0])
        if pinged:
            LOG.info("Light is back; immediately setting color temp")
            curr_state = STATE_ON
            temp_to_set = get_new_color_temp()
            await set_brightness_level(255)
            await set_color_temp(temp_to_set, immediately=True)
            last_temp = 0
        else:
            await asyncio.sleep(2)  # Sleep and ping again.

    elif curr_state == STATE_ON:
        """
        Using the target color temp, this state determines how quickly the lights must change.
        Every minute the light color is updated with the new value.
        Changes to state_light_off if the lights stop responding to updates.
        """
        LOG.debug("Adjusting color temp!")
        temp_to_set = get_new_color_temp()

        # First, check if the current light temp is the one we set it to.
        # If it's not, jump to STATE_CUSTOM_COLOR
        red, green, blue, reported_color_temp = await get_color_from_light()
        if red == None and green == None and blue == None and reported_color_temp == None:
            # We must have gotten no response from the light. Assume we are off!
            curr_state = STATE_LIGHT_OFF
            last_temp = 0
            return
        # Does the light say we are in RGB mode?
        reported_in_rgb_mode = (red == 255 and green == 0 and blue == 0 and reported_color_temp == None)
        global in_rgb_mode
        correctly_in_rgb_mode = (in_rgb_mode and reported_in_rgb_mode)
        LOG.debug("Reported temp {}, last-set temp {}, correctly using rgb mode? {}".format(reported_color_temp, last_temp, correctly_in_rgb_mode))
        if reported_color_temp != last_temp and last_temp != 0 and not correctly_in_rgb_mode:
            LOG.debug("Lights were changed manually. Pausing Flux..")
            LOG.debug("red {}, green {}, blue {}".format(red,green,blue))
            curr_state = STATE_CUSTOM_COLOR
            return

        if last_temp == temp_to_set:
            LOG.debug("Not changing light color!")
        else:
            LOG.info("Setting temp of Wiz Lights: {}".format(temp_to_set))
            success = await set_color_temp(temp_to_set)
            if success:
                last_temp = temp_to_set
            else:
                LOG.info("LIGHTS TURNED OFF!")
                curr_state = STATE_LIGHT_OFF
                last_temp = 0
                return # Break out immediately; don't sleep
        await asyncio.sleep(SECS_BETWEEN_LIGHT_UPDATES)

    elif curr_state == STATE_CUSTOM_COLOR:
        LOG.debug("Lights are set to a custom color. Flux is paused.")
        red, green, blue, reported_color_temp = await get_color_from_light()
        if red == MAGIC_RED and green == MAGIC_GREEN and blue == MAGIC_BLUE:
            LOG.debug("Magic 'reset' color used; resetting to normal runtime mode")
            await set_brightness_level(255)
            curr_state = STATE_ON
            last_temp = 0
        else:
            pinged_successfully = ping_light(sample(LIGHT_IPS, 1)[0])
            if pinged_successfully:
                await asyncio.sleep(5)  # Sleep and run through the state machine agauin.
            else:
                LOG.debug("Lights have been turned off. Resuming normal operations!")
                curr_state = STATE_LIGHT_OFF

    else:
        """
        Undefined state machine state. Abort service.
        """
        LOG.critical("SYSTEM IN BAD STATE, ABORTING")
        quit()

    # End of state machine.
    pass


async def main():
    LOG.info("Starting WizLightControl")
    while(True):
        await state_machine_run()
        LOG.debug("---------------------------------")
    LOG.critical("Quitting WizLightControl unexpectedly")
    quit()


def get_new_color_temp():
    """ Calculate the color temp that the lights should currently display.
    If the color temp was calculated in the last 60 seconds, return that same value back.
    """
    global prev_temp_time
    global prev_temp
    global next_temp_time
    global next_temp
    global last_temp_update_time
    global current_color_temp

    now = datetime.now()
    if now < last_temp_update_time + timedelta(seconds=60):
        LOG.debug("Calculated temp recently. Re-using the old temp.")
        return current_color_temp
    LOG.debug("Calculating new color temp.")
    update_temp_targets()
    time_since_last_point = (now - prev_temp_time).total_seconds()
    time_to_next_point = (next_temp_time - now).total_seconds()
    LOG.debug("time_since_last_point {}".format(time_since_last_point))
    LOG.debug("time_to_next_point {}".format(time_to_next_point))
    percent_transitioned = time_since_last_point / (time_to_next_point + time_since_last_point)
    LOG.debug("percent_transitioned {}".format(percent_transitioned))
    color_temp_delta = prev_temp - next_temp
    current_color_temp = round(prev_temp - (color_temp_delta * percent_transitioned))
    LOG.debug("Prev checkpoint: {} {}".format(prev_temp_time, prev_temp))
    LOG.debug("current_color_temp {}".format(current_color_temp))
    LOG.debug("Next checkpoint: {} {}".format(next_temp_time, next_temp))
    last_temp_update_time = now
    return current_color_temp


def update_temp_targets():
    """
    Determines what the color temperatures in the schedule should be transitioned to next.
    """
    now = datetime.now()
    current_time = now.strftime(SCHEDULE_TIME_FORMAT)
    for i in range(len(SCHEDULE)):
        if SCHEDULE[i][TIME_INDEX] > current_time:
            # Found the right range!
            # Populate the targets using the previous and next values.
            populate_targets(i-1, i)
            return
    # At this point, we will have returned *UNLESS* the next transition is tomorrow morning.
    populate_targets(len(SCHEDULE)-1, 0)


def populate_targets(index_of_prev, index_of_next):
    """
    Update the prev/next time/temp variables using the index of the prev/next values in the schedule.
    """
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
    """
    Used to determine if the lights are online or not.
    """
    LOG.debug("Pinging {}".format(light_ip))
    response = os.system("ping -c 1 " + light_ip)
    return (response == 0)


async def set_color_rgbcw(red, green, blue, cold, warm):
    """
    Sends the color change command to the lights with RGB, cold white and warm white.
    Returns True if successful, False if the lights likely turned off.
    """
    if cold == 0:
        cold = None
    if warm == 0:
        warm = None
    try:
        await asyncio.gather(
        L1.turn_on(PilotBuilder(rgb = (red, green, blue), warm_white = warm, cold_white = cold)),
        L2.turn_on(PilotBuilder(rgb = (red, green, blue), warm_white = warm, cold_white = cold)),
        L3.turn_on(PilotBuilder(rgb = (red, green, blue), warm_white = warm, cold_white = cold)))
        return True
    except exceptions.WizLightConnectionError:
        LOG.debug("Bulb connection errors! Are they turned off?")
    return False


async def transition_to_rgb_mode():
    """
    Changes the colors of the lights to these values, one at a time, so it's not
    noticable. R=255 and ww=200 is the closest I could get to "2200k" so this transition
    is not really noticable at all.
    """
    LOG.debug("Transitioning from color temp mode to RGB mode...")
    try:
        await L1.turn_on(PilotBuilder(rgb = (255, 0, 0), warm_white = 200))
        await asyncio.sleep(3)
        await L2.turn_on(PilotBuilder(rgb = (255, 0, 0), warm_white = 200))
        await asyncio.sleep(3)
        await L3.turn_on(PilotBuilder(rgb = (255, 0, 0), warm_white = 200))
        await asyncio.sleep(3)
    except exceptions.WizLightConnectionError:
        LOG.debug("Bulb connection errors! Are they turned off?")


async def get_color_from_light():
    """ Get the current color values from the first bulb.
    """
    color_received = False
    retries = 0
    while not color_received and retries < 3:
        light_to_query = sample(LIGHTS, 1)[0]
        try:
            state = await light_to_query.updateState()
            color_received = True
        except exceptions.WizLightConnectionError:
            LOG.debug("Light did not respond to the get_color query")
            color_received = False
            retries = retries + 1
    if not color_received:
        LOG.debug("Failed to get color from any light.")
        return None, None, None, None
    color_temp = state.get_colortemp()
    red, green, blue = state.get_rgb()
    return red, green, blue, color_temp


def calculate_warm_val_from_temp(temp):
    """
    This is used to convert a color temp into the value that the warm LED
    should display. This formula is based on a line of best fit from some
    testing I did with a light meter.
    """
    return round((0.0000000325 * pow(temp, 3)) - (0.00005 * pow(temp, 2)) + (0.0426 * (temp)))


async def set_color_temp(temp, immediately=False):
    """
    Sends the color temperature change command to the lights.
    Returns True if successful, False if the lights likely turned off.
    If arg "immediately" is true, don't wait to transition smoothly; just jump to the color.
    """
    global in_rgb_mode
    if temp < 2200:
        if in_rgb_mode == False and not immediately:
            await transition_to_rgb_mode()
        in_rgb_mode = True
        warm_value = calculate_warm_val_from_temp(temp)
        LOG.debug("Calculated warm LED color of {}".format(warm_value))
        return await set_color_rgbcw(255, 0, 0, 0, warm_value)
    else:
        in_rgb_mode = False
        try:
            await asyncio.gather(
            L1.turn_on(PilotBuilder(colortemp = temp)),
            L2.turn_on(PilotBuilder(colortemp = temp)),
            L3.turn_on(PilotBuilder(colortemp = temp)))
            return True
        except exceptions.WizLightConnectionError:
            LOG.debug("Bulb connection errors! Are they turned off?")
        return False


async def set_brightness_level(brightness_level, retry=True):
    """
    Given a brightness level (0-255), set the brightness.
    """
    if brightness_level < 0:
        brightness_level = 0
    elif brightness_level > 255:
        brightness_level = 255
    LOG.debug(f"Setting brightness to {brightness_level}")
    try:
        await asyncio.gather(
        L1.turn_on(PilotBuilder(brightness = brightness_level)),
        L2.turn_on(PilotBuilder(brightness = brightness_level)),
        L3.turn_on(PilotBuilder(brightness = brightness_level)))
    except exceptions.WizLightConnectionError:
        LOG.debug("Failed to set brightness level due to WizLightConnectionError.")
        if retry:
            LOG.debug("Trying to set brightness one more time...")
            set_brightness_level(brightness_level, retry=False)


async def set_magic_reset_color():
    """
    This is here just so you can call it manually if need be.
    This should only need called if something gets messed up and you need to re-set the scene in the Wiz app.
    """
    return await set_color_rgbcw(MAGIC_RED, MAGIC_GREEN, MAGIC_BLUE, 0, 0)


loop = asyncio.get_event_loop()
loop.run_until_complete(main())

