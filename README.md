# SimplyFilamentSensor
### The new filament sensor plugin that actually works, is up to date, and offers a setup fit for everyone.

This plugin reacts to short lever microswitch output like [this](https://chinadaier.en.made-in-china.com/product/ABVJkvyMAqcT/China-1A-125VAC-on-off-Kw10-Mini-Micro-Mouse-Switch.html).

### Features:
* Automatically pauses the print when filament runs out
* Works with [SimplyPrint](http://simplyprint.dk/)
* Alerts you before starting a print, if filament has run out
* Pop-up notifications in OctoPrint when printer runs out of filament
  * Push, SMS and email notifications for SimplyPrint users
* Test-button so you can easily see if the setup is correct
* Filament check _before_ starting your print after a pause
* Custom GCODE upon pausing
* Pin validation so you don't accidentally save wrong pin number
* Runs on OctoPrint 1.3.0 and higher
* Python 2 & 3 compatible

**NOTE: this plugin only works when printing through SimplyPrint or OctoPrint. When printing through SD card _(also when starting a print via. OctoPrint from your SD card)_, this plugin won't work**

## Setup

Install via the ~~bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)~~ _(COMING SOON!)_
or manually using this URL:

    https://github.com/SimplyPrint/OctoPrint-SimplyFilamentSensor/archive/master.zip

## Configuration

Configuration couldn't be simpler, all you need is to configure listening board pin (board mode) and if the second switch terminal is connected to ground or 3.3V.

Default pin is -1 (not configured) and ground (as it is safer, read below).

**WARNING! Never connect the switch input to 5V as it could fry the GPIO section of your Raspberry!**

**WARNING! When using test button on input pin used by other application it will reset internal pull up/down resistor**

#### Advice

You might experience the same problem as I experienced - the sensor was randomly triggered. Turns out that if running sensor wires along motor wires, it was enough to interfere with sensor reading.

To solve this connect a shielded wire to your sensor and ground the shielding, ideally on both ends.

If you are unsure about your sensor being triggered, check [OctoPrint logs](https://community.octoprint.org/t/where-can-i-find-octoprints-and-octopis-log-files/299)

## Screenshots
_coming soon!_
