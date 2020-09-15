$(function () {
    function simplyfilamentsensorViewModel(parameters) {
        var self = this;
        self.settingsViewModel = parameters[0];
        self.testSensorResult = ko.observable(null);

        $("#simplyfilamentsensor_settings [data-toggle='tooltip']").tooltip();

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin === "simplyfilamentsensor" && typeof data.msg === "string" && data.msg.length) {
                new PNotify({
                    title: "SimplyFilamentSensor",
                    text: data.msg,
                    type: data.type,
                    hide: data.autoClose
                });
            }
        }

        self.testSensor = function () {
            $.ajax({
                    url: "/api/plugin/simplyfilamentsensor",
                    type: "post",
                    dataType: "json",
                    contentType: "application/json",
                    headers: {"X-Api-Key": UI_API_KEY},
                    data: JSON.stringify({
                        "command": "testSensor",
                        "pin": $("#sfsPinInput").val(),
                        "power": $("#sfsPowerInput").val(),
                        "bouncetime": $("#sfsBouncetime").val(),
                        "reverse": $("#sfsReverse").is(":checked"),
                    }),
                    statusCode: {
                        500: function () {
                            $("#sensor-test-result-text").css("color", "red");
                            self.testSensorResult("OctoPrint experienced issue. Check octoprint.log for further info");
                        },
                        555: function () {
                            $("#sensor-test-result-text").css("color", "red");
                            self.testSensorResult("This pin is in use, please choose another pin");
                        },
                        556: function () {
                            $("#sensor-test-result-text").css("color", "red");
                            self.testSensorResult("This pin is either power, ground or out of range. Please choose another pin");
                        }
                    },
                    error: function () {
                        $("#sensor-test-result-text").css("color", "red");
                        self.testSensorResult("There was an error during the test. Please try again.");
                    },
                    success: function (result) {
                        if (result.triggered === true) {
                            $("#sensor-test-result-text").css("color", "green");
                            self.testSensorResult("OK! Sensor detected filament.");
                        } else {
                            $("#sensor-test-result-text").css("color", "red");
                            self.testSensorResult("Fail! Sensor open (triggered).")
                        }
                    }
                }
            );
        }

        self.onSettingsShown = function () {
            self.testSensorResult("");
        }
    }

    // This is how our plugin registers itself with the application, by adding some configuration
    // information to the global variable OCTOPRINT_VIEWMODELS
    ADDITIONAL_VIEWMODELS.push({
        construct: simplyfilamentsensorViewModel,
        dependencies: ["settingsViewModel"],
        elements: ["#settings_plugin_simplyfilamentsensor"]
    })
})
