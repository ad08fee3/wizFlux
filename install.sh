#!/bin/bash
if [[ $EUID -ne 0 ]]; then
    echo "This script should be run using sudo."
    exit 1
fi

echo "Installing pywizlight..."
pip3 install pywizlight
ret=$?
if [[ $ret -ne 0 ]]; then
    echo "Please make sure pip3 is installed:"
    echo "    sudo apt install python3-pip"
    exit 1
fi

echo "Linking wizFlux service files..."

ln -s $PWD/wizFlux.service /lib/systemd/system/wizFlux.service
ln -s $PWD/wizFlux.py /usr/bin/wizFlux.py

echo "Registering service..."
systemctl daemon-reload
systemctl enable wizFlux.service

echo "Starting service..."
systemctl start wizFlux.service

echo "Installation complete!"

