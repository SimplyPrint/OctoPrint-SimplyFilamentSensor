# coding=utf-8
from __future__ import absolute_import
import faulthandler
import octoprint.plugin
import re

from flask import jsonify
from octoprint.events import Events
from time import sleep
import RPi.GPIO as GPIO
import flask

faulthandler.enable()


class SimplyFilamentSensorPlugin(octoprint.plugin.StartupPlugin,
                                 octoprint.plugin.EventHandlerPlugin,
                                 octoprint.plugin.TemplatePlugin,
                                 octoprint.plugin.SettingsPlugin,
                                 octoprint.plugin.SimpleApiPlugin,
                                 octoprint.plugin.AssetPlugin):
    last_pin_state = None

    def __init__(self):
        self._check_in_progress = False
        self._is_testing = False
        self._test_pending = False
        self._last_setup = {
            "pin": -1,
            "pud": -1,
            "sleep": -1,
            "bounce": -1,
        }

    def initialize(self):
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":  # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setwarnings(True)  # Disable GPIO warnings

    @property
    def pin(self):
        return int(self._settings.get(["pin"]))

    @property
    def bounce(self):
        return int(self._settings.get(["bounce"]))

    @property
    def switch(self):
        return int(self._settings.get(["switch"]))

    @property
    def mode(self):
        return int(self._settings.get(["mode"]))

    @property
    def pud_type(self):
        return int(self._settings.get(["type"]))

    @property
    def sleeptime(self):
        return int(self._settings.get(["sleep"]))

    @property
    def action_on_faulty_start(self):
        return int(self._settings.get(["action_on_faulty_start"]))

    @property
    def no_filament_gcode(self):
        return str(self._settings.get(["no_filament_gcode"])).splitlines()

    # Set up GPIO for sensor
    def _setup_sensor(self):
        if self.sensor_enabled():
            self._logger.info("Setting up sensor.")

            if GPIO.getmode() == -1 or GPIO.getmode() == 10:
                GPIO.setmode(GPIO.BCM)
            self._logger.info("Filament Sensor active on GPIO Pin [%s]" % self.pin)

            if self.pud_type is 0:
                if self._last_setup["pud"] != 0:
                    GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            else:
                if self._last_setup["pud"] != 1:
                    GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            self.setup_pin_listener()
        else:
            self._send_ui_popup("Filament sensor pin not configured")

    # set up the GPIO pin listener (event detection)
    def setup_pin_listener(self):
        if self.sensor_enabled():
            GPIO.remove_event_detect(self.pin)

            if self.pud_type is 0:
                the_type = GPIO.RISING
            else:
                the_type = GPIO.FALLING

            if self._last_setup["pin"] != self.pin or self._last_setup["pud"] != the_type:
                self._last_setup["pin"] = self.pin
                self._last_setup["pud"] = the_type

                GPIO.add_event_detect(
                    self.pin, the_type,
                    callback=self.sensor_callback,
                    bouncetime=self.bounce
                )
        else:
            self._send_ui_popup("Filament sensor is not set up", "warning")

    def on_after_startup(self):
        self._logger.info("SimplyFilamentSensor started")
        self._setup_sensor()

    # AssetPlugin hook
    def get_assets(self):
        return dict(js=["js/simplyfilamentsensor.js"], css=["css/simplyfilamentsensor.css"])

    # Template hooks
    def get_template_configs(self):
        return [dict(type="settings", custom_bindings=True)]

    # Settings hook
    def get_settings_defaults(self):
        return dict(
            pin=-1,  # Default is no pin
            bounce=250,  # Debounce 250ms
            switch=False,  # Normally Open
            type="0",
            mode="0",  # Board Mode
            no_filament_gcode="",
            action_on_faulty_start="0",
            sleep=250,
        )

    def _try_clean_pin(self, pin):
        if pin > 0:
            try:
                GPIO.cleanup(pin)
            except:
                pass

    def on_settings_save(self, data):
        if data.get("pin") is not None:
            pin_to_save = int(data.get("pin"))

            # check if pin is not power/ground pin or out of range but allow -1
            if pin_to_save is not -1:
                try:
                    # before saving check if pin not used by others
                    if GPIO.getmode() == -1 or GPIO.getmode() == 10:
                        GPIO.setmode(GPIO.BCM)  # Has to be there - otherwise; crash

                    usage = GPIO.gpio_function(pin_to_save)
                    self._logger.debug("usage on pin %s is %s" % (pin_to_save, usage))
                    if usage is not 1:
                        self._logger.info(
                            "You are trying to save pin %s which is already used by others" % (pin_to_save))
                        self._plugin_manager.send_plugin_message(self._identifier, dict(type="error", autoClose=True,
                                                                                        msg="Settings not saved, you are trying to save pin which is already used by others"))
                        return

                    self._try_clean_pin(self._last_setup["pin"])
                    self._last_setup = {
                        "pin": -1,
                        "pud": -1,
                        "sleep": -1,
                        "bounce": -1,
                    }
                    self._is_testing = False

                    '''if self._last_setup["pin"] != pin_to_save:
                        GPIO.setup(pin_to_save, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                        GPIO.input(pin_to_save)
                        GPIO.cleanup(pin_to_save)'''
                except ValueError:
                    self._logger.info("An error occurred while trying to save")
                    self._plugin_manager.send_plugin_message(self._identifier, dict(type="error", autoClose=True,
                                                                                    msg="An error occurred while trying to save"))
                    return

        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._setup_sensor()

    def last_sensor_state(self):
        return self.last_pin_state

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self, pin_value=None, pud_type=None, reverse=None):
        if self.sensor_enabled():
            if pin_value is None:
                pin_value = GPIO.input(self.pin)

            if pud_type is None:
                pud_type = self.pud_type

            if reverse is None:
                reverse = self.switch

            # if is reverse
            if reverse:
                # is reverse
                the_bool = pin_value is pud_type
            else:
                # is not reverse
                the_bool = pin_value is not pud_type

            return the_bool
        else:
            # Filament sensor is not set up - just act as if there is filament
            return False

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        action = self.action_on_faulty_start

        if action > 0:
            if event is Events.PRINT_STARTED and self.sensor_enabled() and self.no_filament():
                if action == 1:
                    self._event_bus.fire(Events.PLUGIN_SIMPLYFILAMENTSENSOR_NO_FILAMENT_ON_PRINT_START_PAUSED)
                    self._printer.pause_print()
                    self._send_ui_popup("Print paused: no filament detected!")
                elif action == 2:
                    self._event_bus.fire(Events.PLUGIN_SIMPLYFILAMENTSENSOR_NO_FILAMENT_ON_PRINT_START_CANCELLED)
                    self._printer.cancel_print()
                    self._send_ui_popup("Print aborted: no filament detected!")

    def sensor_callback(self, _):
        if self._is_testing:
            self._logger.info("Is testing the pin")
            return

        if self._check_in_progress:
            self._logger.info("A check is already in progress")
            return

        self._check_in_progress = True

        if self.sleeptime > 0:
            sleep(self.sleeptime / 1000)

        this_state = self.no_filament()

        if this_state is not self.last_sensor_state():
            self.last_pin_state = this_state

            if this_state:
                # Has no filament
                self._event_bus.fire(Events.PLUGIN_SIMPLYFILAMENTSENSOR_FILAMENT_RUNOUT)

                if self._printer.is_printing():
                    # Printer is currently printing - pause it
                    self.show_printer_runout_popup()
                    self._printer.pause_print()

                    if len(self.no_filament_gcode):
                        self._printer.commands(self.no_filament_gcode)
                else:
                    self._send_ui_popup("Printer ran out of filament (not while printing)", "info", True)
            else:
                # Has filament
                self._event_bus.fire(Events.PLUGIN_SIMPLYFILAMENTSENSOR_FILAMENT_LOADED)
                self._send_ui_popup("Printer filament loaded", "info", True)

        self._check_in_progress = False

    def show_printer_runout_popup(self):
        self._send_ui_popup("Printer ran out of filament!")

    def _send_ui_popup(self, message, type="info", autoclose=False):
        self._plugin_manager.send_plugin_message(self._identifier,
                                                 dict(type=type, autoClose=autoclose, msg=message))

    # simpleApiPlugin
    def get_api_commands(self):
        return dict(getState=[], testSensor=["pin", "power", "bouncetime", "reverse"])

    # Test check via. settings
    def on_api_command(self, command, data):
        if command == "getState":
            has_filament = not self.no_filament()
            return jsonify(has_filament=has_filament)

        self._is_testing = True

        try:
            selected_power = int(data.get("power"))
            selected_pin = int(data.get("pin"))
            reverse = bool(data.get("reverse"))

            if self._last_setup["pin"] != selected_pin:
                GPIO.remove_event_detect(self.pin)
                self._try_clean_pin(self._last_setup["pin"])
                self._try_clean_pin(selected_pin)
                if GPIO.getmode() == -1 or GPIO.getmode() == 10:
                    GPIO.setmode(GPIO.BCM)

            # first check pins not in use already
            usage = GPIO.gpio_function(selected_pin)
            self._logger.debug("usage on pin %s is %s" % (selected_pin, usage))
            # 1 = input
            if usage is not 1:
                # 555 is not http specific so I chose it
                return "", 555

            # before read don't let the pin float
            if self._last_setup["pud"] != selected_power:
                if selected_power is 0:
                    GPIO.setup(selected_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                else:
                    GPIO.setup(selected_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            pin_value = GPIO.input(selected_pin)
            # reset input to pull down after read
            triggered_bool = not self.no_filament(pin_value, selected_power, reverse)
            # GPIO.cleanup()

            # Set up with saved settings again
            self._last_setup = {
                "pin": -1,
                "pud": -1,
                "sleep": -1,
                "bounce": -1,
            }
            self._setup_sensor()
            self._is_testing = False
            return flask.jsonify(triggered=triggered_bool)
        except ValueError:
            # ValueError occurs when reading from power or ground pins
            self._logger.debug("Failed filament sensor check API call")
            # GPIO.cleanup()
            self._last_setup = {
                "pin": -1,
                "pud": -1,
                "sleep": -1,
                "bounce": -1,
            }
            self._setup_sensor()
            self._is_testing = False
            return "", 556

    def get_update_information(self):
        return dict(
            simplyfilamentsensor=dict(
                displayName="SimplyFilamentSensor",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="SimplyPrint",
                repo="OctoPrint-SimplyFilamentSensor",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/SimplyPrint/OctoPrint-SimplyFilamentSensor/archive/{target_version}.zip"
            )
        )

    def register_custom_events(*args, **kwargs):
        return [
            "no_filament_on_print_start_paused",
            "no_filament_on_print_start_cancelled",
            "filament_runout",
            "filament_loaded"
        ]


__plugin_pythoncompat__ = ">=2.7,<4"  # python 2 and 3


def __plugin_check__():
    try:
        import RPi.GPIO as GPIO
        if GPIO.VERSION < "0.6":  # Need at least 0.6 for edge detection
            return False
    except ImportError:
        return False
    return True


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = SimplyFilamentSensorPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
        "octoprint.events.register_custom_events": __plugin_implementation__.register_custom_events,
    }
