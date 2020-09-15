# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import re

from flask import jsonify
from octoprint.events import Events
from time import sleep
import RPi.GPIO as GPIO
import flask


class SimplyFilamentSensorPlugin(octoprint.plugin.StartupPlugin,
                                 octoprint.plugin.EventHandlerPlugin,
                                 octoprint.plugin.TemplatePlugin,
                                 octoprint.plugin.SettingsPlugin,
                                 octoprint.plugin.SimpleApiPlugin,
                                 octoprint.plugin.AssetPlugin,
                                 octoprint.plugin.BlueprintPlugin):

    def initialize(self):
        self._logger.info("Running RPi.GPIO version '{0}'".format(GPIO.VERSION))
        if GPIO.VERSION < "0.6":  # Need at least 0.6 for edge detection
            raise Exception("RPi.GPIO must be greater than 0.6")
        GPIO.setwarnings(True)  # Disable GPIO warnings

    @octoprint.plugin.BlueprintPlugin.route("/status", methods=["GET"])
    def check_status(self):
        status = "-1"
        if self.sensor_enabled():
            status = "0" if self.no_filament() else "1"
        return jsonify(status=status)

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
    def no_filament_gcode(self):
        return str(self._settings.get(["no_filament_gcode"])).splitlines()

    @property
    def send_gcode_only_once(self):
        return self._settings.get_boolean(["send_gcode_only_once"])

    def _setup_sensor(self):
        if self.sensor_enabled():
            self._logger.info("Setting up sensor.")

            GPIO.setmode(GPIO.BCM)
            self._logger.info("Filament Sensor active on GPIO Pin [%s]" % self.pin)

            if self.pud_type is 0:
                GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            else:
                GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        else:
            self._logger.info("Pin not configured, won't work unless configured!")

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
            switch=True,  # Normally Open
            type=0,
            mode=0,  # Board Mode
            no_filament_gcode="",
            sleep=5,
            send_gcode_only_once=False,  # Default set to False for backward compatibility
        )

    def on_settings_save(self, data):
        if data.get("pin") is not None:
            pin_to_save = int(data.get("pin"))

            # check if pin is not power/ground pin or out of range but allow -1
            if pin_to_save is not -1:
                try:
                    # before saving check if pin not used by others
                    usage = GPIO.gpio_function(pin_to_save)
                    self._logger.debug("usage on pin %s is %s" % (pin_to_save, usage))
                    if usage is not 1:
                        self._logger.info(
                            "You are trying to save pin %s which is already used by others" % (pin_to_save))
                        self._plugin_manager.send_plugin_message(self._identifier, dict(type="error", autoClose=True,
                                                                                        msg="Settings not saved, you are trying to save pin which is already used by others"))
                        return
                    GPIO.setup(pin_to_save, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
                    GPIO.input(pin_to_save)
                    GPIO.cleanup(pin_to_save)
                except ValueError:
                    self._logger.info(
                        "You are trying to save pin %s which is ground/power pin or out of range" % (pin_to_save))
                    self._plugin_manager.send_plugin_message(self._identifier, dict(type="error", autoClose=True,
                                                                                    msg="Settings not saved, you are trying to save pin which is ground/power pin or out of range"))
                    return
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._setup_sensor()

    def sensor_triggered(self):
        return self.triggered

    def sensor_enabled(self):
        return self.pin != -1

    def no_filament(self, pin_value=None, pud_type=None):
        if pin_value is None:
            pin_value = GPIO.input(self.pin)

        if pud_type is None:
            pud_type = self.pud_type

        # if is reverse
        if self.switch:
            # is reverse
            line = str(pin_value) + " is " + str(pud_type)
            the_bool = pin_value is pud_type
        else:
            # is not reverse
            line = str(pin_value) + " is NOT " + str(pud_type)
            the_bool = pin_value is not pud_type

        msg = "CHECKING FOR NO FILAMENT; pin value [" + str(pin_value) + "], pud type [" + str(
            pud_type) + "], the return [" + str(the_bool) + "], switched = " + str(
            self.switch) + "\nSo the line is; " + str(line)

        self._logger.info(msg)
        self._logger.debug(msg)

        return the_bool

    def on_event(self, event, payload):
        # Early abort in case of out ot filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED and self.no_filament():
            self._logger.info("Printing aborted: no filament detected!")
            self._printer.cancel_print()
            self._send_ui_popup("Printing aborted: no filament detected!")

        # Enable sensor
        if event in (
                Events.PRINT_STARTED,
                Events.PRINT_RESUMED
        ):
            self._logger.info("%s: Enabling filament sensor." % (event))
            if self.sensor_enabled():
                self.triggered = 0  # reset triggered state
                GPIO.remove_event_detect(self.pin)

                if self.pud_type is 0:
                    the_type = GPIO.RISING
                else:
                    the_type = GPIO.FALLING

                GPIO.add_event_detect(
                    self.pin, the_type,
                    callback=self.sensor_callback,
                    bouncetime=self.bounce
                )
        # Disable sensor
        elif event in (
                Events.PRINT_DONE,
                Events.PRINT_FAILED,
                Events.PRINT_CANCELLED,
                Events.ERROR
        ):
            self._logger.info("%s: Disabling filament sensor." % (event))
            GPIO.remove_event_detect(self.pin)

    def sensor_callback(self, _):
        sleep(self.sleeptime)

        # If we have previously triggered a state change we are still out
        # of filament. Log it and wait on a print resume or a new print job.
        if self.sensor_triggered():
            self._logger.info("Sensor callback but no trigger state change.")
            return

        # Set the triggered flag to check next callback
        self.triggered = 1

        if self.no_filament():
            self._logger.info("Out of filament!")

            self.show_printer_runout_popup()

            if self.send_gcode_only_once:
                self._logger.info("Sending GCODE only once...")
            else:
                # Need to resend GCODE (old default) so reset trigger
                self.triggered = 0

                self._logger.info("Pausing print.")
                self._printer.pause_print()

            if self.no_filament_gcode:
                self._logger.info("Sending out of filament GCODE")
                self._printer.commands(self.no_filament_gcode)
        else:
            self._logger.info("Filament detected - false positive!")

    def show_printer_runout_popup(self):
        self._send_ui_popup("Printer ran out of filament!")

    def _send_ui_popup(self, message, type="info"):
        self._plugin_manager.send_plugin_message(self._identifier,
                                                 dict(type=type, autoClose=False, msg=message))

    # simpleApiPlugin
    @staticmethod
    def get_api_commands():
        return dict(testSensor=["pin", "power"])

    # Test check via. settings
    def on_api_command(self, command, data):
        try:
            selected_power = int(data.get("power"))
            selected_pin = int(data.get("pin"))
            GPIO.cleanup()
            GPIO.setmode(GPIO.BCM)

            # first check pins not in use already
            usage = GPIO.gpio_function(selected_pin)
            self._logger.debug("usage on pin %s is %s" % (selected_pin, usage))
            # 1 = input
            if usage is not 1:
                # 555 is not http specific so I chose it
                return "", 555

            # before read don't let the pin float
            if selected_power is 0:
                GPIO.setup(selected_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            else:
                GPIO.setup(selected_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

            pin_value = GPIO.input(selected_pin)
            # reset input to pull down after read
            triggered_bool = not self.no_filament(pin_value, selected_power)
            GPIO.cleanup()
            self._setup_sensor()
            return flask.jsonify(triggered=triggered_bool)
        except ValueError:
            # ValueError occurs when reading from power or ground pins
            self._logger.debug("Failed filament sensor check API call")
            GPIO.cleanup()
            self._setup_sensor()
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
        # self._event_bus.fire(Events.PLUGIN_SIMPLYFILAMENTSENSOR_FILAMENT_RUNOUT)

        return [
            "no_filament_print_on_print_start",
            "filament_runout"
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
