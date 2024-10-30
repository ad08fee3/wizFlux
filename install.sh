#!/bin/bash
if [[ $EUID -ne 0 ]]; then
    echo "This script should be run using sudo."
    exit 1
fi

echo "Before continuing, insert the IP addresses of your lights within wizFlux.py."

echo "Also: Within wizFlux.service replace /usr/bin/python3 with this path instead:"
echo "    $PWD/.venv/wixFlux/bin/python3"

echo "Checking prerequisites:"
prerequisites_installed=true

# Check pip3
echo "...pip3"
which pip3 1>/dev/null
ret=$?
if [[ $ret -ne 0 ]]; then
    echo "This script requires pip3 to be installed. Try running:"
	echo "    sudo apt install python3-pip"
	prerequisites_installed=false
fi


# Check venv
echo "...venv"
apt show python3-venv 1>/dev/null 2>/dev/null
ret=$?
if [[ $ret -ne 0 ]]; then
    echo "This script requires python3-venv to be installed. Try running:"
	echo "    sudo apt install python3-venv"
	prerequisites_installed=false
fi


# Bail if we need stuff to be installed before continuing.
if [ "$prerequisites_installed" = false ] ; then
    exit 1
fi

# Time to install!
echo "The script will run the following commands. Would you like to continue?"
echo "    python3 -m venv .venv/wizFlux"
echo "    source .venv/wizFlux/bin/activate"
echo "    pip install pywizlight"
read -p "[y/N] " input_var
if [[ "$input_var" != "y" && "$input_var" != "Y" ]]; then
    exit 1
fi

echo "Creating wizFlux .venv..."
python3 -m venv .venv/wizFlux
source .venv/wizFlux/bin/activate

echo "Installing pywizlight..."
pip3 install pywizlight
ret=$?
if [[ $ret -ne 0 ]]; then
    echo "There was an error installing pywizlight. Try running:"
    echo "    pip3 install pywizlight"
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

echo "Checking status..."
sleep 1
systemctl status wizFlux.service --no-pager
ret=$?
if [[ $ret -ne 0 ]]; then
    echo "There was an error starting WizFlux! Check the above errors or run"
    echo "    sudo journalctl -fu wizFluxpywizlight"
	echo "for more information."
    exit 1
fi

echo "Installation complete!"

