# wizFlux
A python service that slowly changes the color of Wiz Lights over the course of the day.
Shout out to https://github.com/sbidy/pywizlight

# Installation
Run the install.sh script with sudo.

This should set up soft links to the right directories and register wizFlux as a systemd service.

# Running
It should run at boot as part of systemd. The install script will *not* work on systems using SysV init. The python script will have to be run manually.  
You can control the service with

```
sudo systemctl stop wizFlux.service
sudo systemctl start wizFlux.service
sudo systemctl restart wizFlux.service
```

# Logging
You can see logs using

```
sudo journalctl -fu wizFlux
```
