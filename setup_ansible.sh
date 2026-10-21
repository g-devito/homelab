#!/bin/bash

# 1. Installa ansible-core su Fedora
echo "--- Installazione di ansible-core ---"
sudo dnf install -y ansible-core
sudo dnf install python3-passlib

# 2. Installa le collezioni definite nel file requirements.yml
if [ -f "requirements.yml" ]; then
    echo "--- Installazione delle collezioni Ansible ---"
    ansible-galaxy collection install -r requirements.yml
else
    echo "Errore: File requirements.yml non trovato!"
    exit 1
fi

echo "--- Setup completato con successo! ---"
